"""argon2id password hashing (OWASP's first-choice KDF).

`argon2.PasswordHasher()` defaults are the library's tuned argon2id parameters;
the encoded hash carries them, so `verify` / `needs_rehash` keep working after a
parameter bump.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    """True iff `password` matches `hashed`. Never raises — a malformed stored
    hash is simply a non-match."""
    try:
        return _hasher.verify(hashed, password)
    except (
        VerifyMismatchError,
        VerificationError,
        InvalidHashError,
        HashingError,
    ):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when `hashed` was made with weaker-than-current parameters and
    should be replaced (do this on the next successful login)."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True
