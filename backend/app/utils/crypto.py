"""Application-level encryption for health data written to object storage.

Backend-originated payloads (raw payloads, FIT files) are encrypted here before they
reach the storage backend, so the store only ever holds ciphertext this application can
decrypt. This is independent of, and complementary to, storage-side server-side
encryption (SSE): SSE protects everything at rest with a storage-managed key, while this
keeps an *application-held* key so the storage backend never sees plaintext at all.

Keys come from ``DATA_ENCRYPTION_KEY`` — a Fernet key, or a comma-separated list for
rotation (the first key encrypts; any key can decrypt). It is kept separate from
``MASTER_KEY`` (which decrypts config secrets) on purpose, so a compromise of one does
not expose the other. When no key is configured, encryption is disabled and callers
store plaintext (SSE, if configured, still applies at the storage layer).
"""

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet

from app.config import settings

# Marker recorded in object metadata so a stored object is self-describing and future
# tooling knows how it was encrypted.
ENCRYPTION_SCHEME = "fernet"


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet | None:
    """Build the cipher from settings, or ``None`` when no key is configured.

    Cached because the key does not change within a process; call :func:`reset_cache`
    after mutating the setting (tests, runtime key rotation).
    """
    secret = settings.data_encryption_key
    if secret is None:
        return None
    raw = secret.get_secret_value().strip()
    if not raw:
        return None

    try:
        parts = [part.strip() for part in raw.split(",")]
        if any(not part for part in parts):
            raise ValueError("empty key")
        keys = [Fernet(part.encode("utf-8")) for part in parts]
    except (ValueError, TypeError) as e:
        # Never silently fall back to plaintext when an operator explicitly configured
        # encryption. Settings validates this at startup; this guard also protects tests
        # and any runtime mutation of the settings object.
        raise ValueError("DATA_ENCRYPTION_KEY contains an invalid Fernet key") from e

    return MultiFernet(keys)


def is_enabled() -> bool:
    """True when a data-encryption key is configured and valid."""
    return _cipher() is not None


def encrypt(data: bytes) -> bytes:
    """Encrypt ``data``. Returns it unchanged when encryption is disabled."""
    cipher = _cipher()
    if cipher is None:
        return data
    return cipher.encrypt(data)


def decrypt(token: bytes) -> bytes:
    """Decrypt a token produced by :func:`encrypt`. Returns it unchanged when disabled."""
    cipher = _cipher()
    if cipher is None:
        return token
    return cipher.decrypt(token)


def reset_cache() -> None:
    """Clear the cached cipher (after changing the key at runtime, or in tests)."""
    _cipher.cache_clear()
