"""Password hashing with Argon2id (winner of the Password Hashing Competition).

argon2-cffi's defaults follow the RFC 9106 recommendations; hashes embed their
own parameters, so they can be raised later and old hashes are upgraded on the
next successful login via ``needs_rehash``.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Verified against when a username does not exist, so the response time of a
# failed login does not reveal whether the account exists.
_DUMMY_HASH = _hasher.hash("infrawatch-timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
