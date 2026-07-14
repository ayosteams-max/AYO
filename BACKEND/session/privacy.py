from hashlib import sha256


def hash_sensitive_identifier(value: bytes) -> bytes:
    """Return a non-reversible lookup key; callers must supply high-entropy input."""

    if len(value) < 16:
        raise ValueError("Sensitive identifier input is too short")
    return sha256(value).digest()
