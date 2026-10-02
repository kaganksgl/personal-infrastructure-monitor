"""FastAPI dependencies for database access and authentication."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rate_limit import RateLimiter
from app.auth.tokens import hash_token, tokens_match
from app.config import Settings
from app.models import Agent, User, UserSession

SESSION_COOKIE = "iw_session"
CSRF_HEADER = "X-Requested-With"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessionmaker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def client_ip(request: Request) -> str:
    # Uvicorn rewrites request.client from X-Forwarded-For only for trusted
    # proxies (--forwarded-allow-ips), so this cannot be spoofed by clients.
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(limiter: RateLimiter, key: str) -> None:
    if not limiter.hit(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests",
            headers={"Retry-After": str(limiter.retry_after(key))},
        )


def require_csrf_header(request: Request) -> None:
    """CSRF defence-in-depth for cookie-authenticated, state-changing requests.

    The session cookie is already ``SameSite=Strict``. Additionally requiring a
    custom header means a cross-site form or <img> cannot forge a request: a
    browser only sends custom headers cross-origin after a CORS preflight, which
    our CORS policy refuses.
    """
    if request.method not in _SAFE_METHODS and CSRF_HEADER not in request.headers:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing CSRF header")


async def resolve_session_user(db: AsyncSession, token: str | None) -> User | None:
    if not token:
        return None
    row = await db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    return row.scalar_one_or_none()


async def current_user(request: Request, db: DbSession) -> User:
    require_csrf_header(request)
    user = await resolve_session_user(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]

_AGENT_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Invalid agent credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def authenticated_agent(request: Request, db: DbSession) -> Agent:
    """Authenticate an agent by ``X-Agent-ID`` + ``Authorization: Bearer <key>``.

    Unknown agent and wrong key produce the same response, so the endpoint
    cannot be used to enumerate registered agent IDs.
    """
    agent_id = request.headers.get("X-Agent-ID", "")
    scheme, _, key = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not key or not agent_id:
        raise _AGENT_UNAUTHORIZED

    enforce_rate_limit(request.app.state.ingest_limiter, f"agent:{agent_id}")

    agent = (await db.execute(select(Agent).where(Agent.agent_id == agent_id))).scalar_one_or_none()
    expected = agent.api_key_hash if agent else "0" * 64
    if not tokens_match(key, expected) or agent is None:
        raise _AGENT_UNAUTHORIZED
    return agent


AuthenticatedAgent = Annotated[Agent, Depends(authenticated_agent)]
