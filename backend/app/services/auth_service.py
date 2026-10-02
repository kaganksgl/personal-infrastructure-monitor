"""User registration, login and session lifecycle."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.tokens import hash_token, new_token
from app.models import User, UserSession

# Arbitrary constant identifying the "first user registration" advisory lock.
_REGISTRATION_LOCK_ID = 7_351_001


class RegistrationClosedError(Exception):
    pass


class UsernameTakenError(Exception):
    pass


async def user_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(User))).scalar_one()


async def register_user(
    db: AsyncSession, username: str, password: str, *, allow_registration: bool
) -> User:
    """Create a user. The very first user becomes admin.

    A transaction-scoped advisory lock serialises registrations so two
    concurrent requests on an empty database cannot both become admin.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _REGISTRATION_LOCK_ID})
    existing = await user_count(db)
    if existing > 0 and not allow_registration:
        raise RegistrationClosedError
    taken = await db.execute(select(User.id).where(func.lower(User.username) == username.lower()))
    if taken.first() is not None:
        raise UsernameTakenError
    user = User(
        username=username,
        password_hash=hash_password(password),
        role="admin" if existing == 0 else "viewer",
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    user = (
        await db.execute(select(User).where(func.lower(User.username) == username.lower()))
    ).scalar_one_or_none()
    if not verify_password(user.password_hash if user else None, password) or user is None:
        return None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    return user


async def create_session(
    db: AsyncSession, user: User, *, ttl: timedelta, ip: str, user_agent: str | None
) -> str:
    token = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + ttl,
            ip_address=ip,
            user_agent=(user_agent or "")[:256],
        )
    )
    return token


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))


async def purge_expired_sessions(db: AsyncSession) -> int:
    result = await db.execute(
        delete(UserSession).where(UserSession.expires_at <= datetime.now(UTC))
    )
    return int(getattr(result, "rowcount", 0) or 0)
