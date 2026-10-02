"""Opaque random tokens for sessions and agent API keys.

Both are 256-bit random values, so a single SHA-256 is the right storage
hash: brute-forcing a 2^256 preimage is infeasible, and unlike Argon2 it adds
no latency to every agent request. (Passwords are low-entropy and therefore
use Argon2id instead; see passwords.py.)
"""

import hashlib
import hmac
import secrets

API_KEY_PREFIX = "iwk_"
_DISPLAY_PREFIX_LEN = 12


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), expected_hash)


def new_api_key() -> tuple[str, str, str]:
    """Return ``(plaintext_key, stored_hash, display_prefix)``."""
    key = API_KEY_PREFIX + new_token()
    return key, hash_token(key), key[:_DISPLAY_PREFIX_LEN]
