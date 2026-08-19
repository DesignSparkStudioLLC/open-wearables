"""Tests for encrypted raw-payload replay support."""

import sys

import pytest
from cryptography.fernet import Fernet

from scripts.replay_raw_payloads import decrypt_payload, load_decryptor, parse_args


def test_load_decryptor_supports_key_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    token = Fernet(old_key).encrypt(b"payload")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", f"{new_key.decode()},{old_key.decode()}")

    decryptor = load_decryptor()

    assert decryptor.decrypt(token) == b"payload"


def test_load_decryptor_rejects_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "invalid")

    with pytest.raises(ValueError, match="invalid Fernet key"):
        load_decryptor()


def test_legacy_plaintext_remains_readable_after_encryption_is_enabled() -> None:
    decryptor = Fernet(Fernet.generate_key())
    payload = b'{"legacy": true}'

    assert decrypt_payload(payload, {}, decryptor) == payload


def test_marked_payload_requires_the_matching_key() -> None:
    with pytest.raises(RuntimeError, match="set DATA_ENCRYPTION_KEY"):
        decrypt_payload(b"encrypted", {"encryption": "fernet"}, None)


def test_marked_payload_is_decrypted() -> None:
    decryptor = Fernet(Fernet.generate_key())
    token = decryptor.encrypt(b'{"encrypted": true}')

    assert decrypt_payload(token, {"encryption": "fernet"}, decryptor) == b'{"encrypted": true}'


def test_unknown_encryption_scheme_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="unsupported payload encryption scheme"):
        decrypt_payload(b"payload", {"encryption": "future-scheme"}, None)


def test_shared_s3_endpoint_is_used_as_replay_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAW_PAYLOAD_S3_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://seaweedfs:8333")
    monkeypatch.setenv("OPEN_WEARABLES_API_KEY", "test-api-key")
    monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(sys, "argv", ["replay_raw_payloads.py", "--user-id", "user-1"])

    args = parse_args()

    assert args.s3_endpoint_url == "http://seaweedfs:8333"
