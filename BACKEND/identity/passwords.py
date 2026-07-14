from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


class Argon2idPasswordVerifier:
    """Versioned memory-hard verifier; plaintext is never retained or logged."""

    scheme = "argon2id-v19"

    def __init__(self) -> None:
        self._hasher = PasswordHasher(memory_cost=65_536, time_cost=3, parallelism=4)

    def hash(self, password: str) -> str:
        if len(password) < 12 or len(password) > 1_024:
            raise ValueError("Password length is outside the accepted range")
        return self._hasher.hash(password)

    def verify(self, verifier: str, password: str) -> bool:
        try:
            return self._hasher.verify(verifier, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def needs_upgrade(self, verifier: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(verifier)
        except InvalidHashError:
            return True
