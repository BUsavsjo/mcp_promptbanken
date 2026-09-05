from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from connect_service.auth import SupabaseJwtVerifier


@pytest.fixture
def signing_key():
    return generate_private_key(public_exponent=65537, key_size=2048)


def _verifier(monkeypatch: pytest.MonkeyPatch, signing_key) -> SupabaseJwtVerifier:
    monkeypatch.setattr(
        "connect_service.auth.PyJWKClient",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=signing_key.public_key())
        ),
    )
    return SupabaseJwtVerifier(
        issuer="https://example.supabase.co/auth/v1",
        audience="promptbanken-connect",
        jwks_url="https://example.supabase.co/auth/v1/.well-known/jwks.json",
    )


def test_verifier_accepts_token_for_expected_issuer_and_audience(monkeypatch, signing_key) -> None:
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "iss": "https://example.supabase.co/auth/v1",
            "aud": "promptbanken-connect",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        signing_key,
        algorithm="RS256",
    )

    assert _verifier(monkeypatch, signing_key).verify(token)["sub"] == (
        "00000000-0000-0000-0000-000000000001"
    )


def test_verifier_rejects_token_for_another_audience(monkeypatch, signing_key) -> None:
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "iss": "https://example.supabase.co/auth/v1",
            "aud": "another-service",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        signing_key,
        algorithm="RS256",
    )

    with pytest.raises(ValueError, match="Ogiltig åtkomsttoken"):
        _verifier(monkeypatch, signing_key).verify(token)


def test_verifier_converts_a_jwks_lookup_failure_to_an_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "connect_service.auth.PyJWKClient",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: (_ for _ in ()).throw(jwt.PyJWKClientError("saknar nyckel"))
        ),
    )
    verifier = SupabaseJwtVerifier(
        issuer="https://example.supabase.co/auth/v1",
        audience="authenticated",
        jwks_url="https://example.supabase.co/auth/v1/.well-known/jwks.json",
    )

    with pytest.raises(ValueError, match="Ogiltig åtkomsttoken"):
        verifier.verify("not-a-valid-token")
