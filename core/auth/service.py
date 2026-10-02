from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)


def hash_password(password: str) -> str:
    """Hash an owner password with the configured Argon2 parameters."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify an Argon2 password hash and return false for invalid or mismatched hashes."""
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False
