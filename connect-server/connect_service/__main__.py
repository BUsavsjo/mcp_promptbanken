"""Lokal startpunkt för den fristående Connect-tjänsten."""

import os

import uvicorn

from .app import create_app
from .auth import SupabaseJwtVerifier
from .data import SupabaseConnectRepository


_DEFAULT_ISSUER = "https://cohyrgxeatqexkqihktu.supabase.co/auth/v1"


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Miljövariabeln {name} måste vara satt.")
    return value


def _configured(name: str, default: str) -> str:
    return os.environ.get(name) or default


app = create_app(
    resource_url=_required("CONNECT_RESOURCE_URL"),
    authorization_server=_configured("CONNECT_AUTHORIZATION_SERVER", _DEFAULT_ISSUER),
    token_verifier=SupabaseJwtVerifier(
        issuer=_configured("CONNECT_TOKEN_ISSUER", _DEFAULT_ISSUER),
        audience=_configured("CONNECT_TOKEN_AUDIENCE", "authenticated"),
        jwks_url=_configured("CONNECT_JWKS_URL", f"{_DEFAULT_ISSUER}/.well-known/jwks.json"),
    ),
    library=SupabaseConnectRepository(
        supabase_url=_configured("CONNECT_SUPABASE_URL", "https://cohyrgxeatqexkqihktu.supabase.co"),
        publishable_key=_required("CONNECT_SUPABASE_PUBLISHABLE_KEY"),
    ),
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
