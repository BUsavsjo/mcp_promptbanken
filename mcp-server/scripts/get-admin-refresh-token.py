#!/usr/bin/env python3
"""One-time bootstrap: exchange the platform owner's Supabase email+password
for a refresh_token to store as SUPABASE_ADMIN_REFRESH_TOKEN on the VPS. Run
this locally once; never commit or log the printed output. See
docs/superpowers/specs/2026-07-28-admin-mcp-catalog-authoring-design.md."""
from __future__ import annotations

import getpass
import os
import sys

import httpx


def main() -> int:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    email = input("Platform owner email: ").strip()
    password = getpass.getpass("Password: ")

    response = httpx.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    print("\nSUPABASE_ADMIN_REFRESH_TOKEN=" + payload["refresh_token"])
    print("\nStore this as a secret on the VPS (.env, never git). It is only ever shown here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
