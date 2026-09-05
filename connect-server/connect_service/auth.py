"""JWT-verifiering för access tokens utfärdade av OAuth-auktoriseringsservern."""

from collections.abc import Mapping

import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError


class SupabaseJwtVerifier:
    """Verifierar endast asymmetriskt signerade access tokens mot JWKS."""

    def __init__(self, *, issuer: str, audience: str, jwks_url: str) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> Mapping[str, object]:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except (InvalidTokenError, PyJWKClientError) as error:
            raise ValueError("Ogiltig åtkomsttoken.") from error

        if not isinstance(claims.get("sub"), str):
            raise ValueError("Åtkomsttoken saknar användaridentitet.")
        return claims
