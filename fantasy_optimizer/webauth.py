"""Yahoo OAuth for the hosted web app.

The CLI uses yahoo_oauth's interactive terminal flow. A hosted app cannot
read from a terminal, so it does the standard browser redirect instead and
then hands yahoo_oauth a credentials file it can refresh on its own.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from urllib.parse import urlencode

import requests

AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


def authorize_url(client_id: str, redirect_uri: str) -> str:
    return AUTHORIZE_URL + "?" + urlencode(
        {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code"})


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    """Trade the ?code= Yahoo redirects back with for access/refresh tokens."""
    resp = requests.post(TOKEN_URL, auth=(client_id, client_secret), timeout=20, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})
    if resp.status_code != 200:
        raise RuntimeError(f"Yahoo rejected the login ({resp.status_code}): {resp.text[:200]}")
    return resp.json()


def write_oauth_file(client_id: str, client_secret: str, refresh_token: str,
                     redirect_uri: str = "oob", access_token: str = "",
                     token_time: float = 0.0, path: str | None = None) -> str:
    """Write a yahoo_oauth credentials file. A zero token_time forces a refresh."""
    path = path or os.path.join(tempfile.gettempdir(), "fantasy_oauth2.json")
    data = {
        "consumer_key": client_id, "consumer_secret": client_secret,
        "refresh_token": refresh_token, "access_token": access_token or "pending",
        "token_type": "bearer", "token_time": token_time or 0.0,
        "callback_uri": redirect_uri,
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    return path


def oauth_file_from_tokens(client_id, client_secret, redirect_uri, tokens: dict,
                           path: str | None = None) -> str:
    return write_oauth_file(client_id, client_secret, tokens["refresh_token"],
                            redirect_uri, tokens.get("access_token", ""), time.time(), path)
