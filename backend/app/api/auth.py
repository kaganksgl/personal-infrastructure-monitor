from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.dependencies import (
    SESSION_COOKIE,
    AppSettings,
    CurrentUser,
    DbSession,
    client_ip,
    enforce_rate_limit,
    require_csrf_header,
)
from app.schemas.auth import AuthStatus, Credentials, UserOut
from app.services import audit, auth_service

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_csrf_header)])


def _set_session_cookie(response: Response, token: str, settings: AppSettings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,  # not readable from JavaScript -> immune to token theft via XSS
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api",
    )


@router.get("/status", response_model=AuthStatus)
async def auth_status(db: DbSession, settings: AppSettings) -> AuthStatus:
    has_users = await auth_service.user_count(db) > 0
    return AuthStatus(
        has_users=has_users, registration_open=not has_users or settings.allow_registration
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: Credentials, request: Request, db: DbSession, settings: AppSettings
) -> UserOut:
    ip = client_ip(request)
    enforce_rate_limit(request.app.state.login_limiter, f"register:{ip}")
    try:
        user = await auth_service.register_user(
            db, body.username, body.password, allow_registration=settings.allow_registration
        )
    except auth_service.RegistrationClosedError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is closed") from None
    except auth_service.UsernameTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken") from None
    audit.record(db, "user.registered", user=user, ip=ip, details={"role": user.role})
    await db.commit()
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
async def login(
    body: Credentials,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> UserOut:
    ip = client_ip(request)
    limiter = request.app.state.login_limiter
    enforce_rate_limit(limiter, f"login-ip:{ip}")
    enforce_rate_limit(limiter, f"login-user:{body.username.lower()}")

    user = await auth_service.authenticate(db, body.username, body.password)
    if user is None:
        audit.record(db, "user.login_failed", username=body.username[:64], ip=ip)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    token = await auth_service.create_session(
        db,
        user,
        ttl=timedelta(hours=settings.session_ttl_hours),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    audit.record(db, "user.login", user=user, ip=ip)
    await db.commit()
    _set_session_cookie(response, token, settings)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DbSession, user: CurrentUser) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await auth_service.revoke_session(db, token)
    audit.record(db, "user.logout", user=user, ip=client_ip(request))
    await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/api")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
