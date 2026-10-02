from datetime import datetime

from pydantic import Field

from app.schemas.common import ApiModel, WireModel


class Credentials(WireModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    # Upper bound stops multi-megabyte "passwords" from burning hashing CPU.
    password: str = Field(min_length=10, max_length=256)


class UserOut(ApiModel):
    id: int
    username: str
    role: str
    created_at: datetime
    last_login_at: datetime | None


class AuthStatus(ApiModel):
    registration_open: bool
    has_users: bool
