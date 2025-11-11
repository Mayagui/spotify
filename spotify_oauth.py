import base64
import time
import urllib.parse
from typing import Dict, Optional

import requests

from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI


AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_ME = "https://api.spotify.com/v1/me"


def get_auth_url(state: str, scopes: str) -> str:
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": scopes,
        "state": state,
        "show_dialog": "false",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def _basic_auth_header() -> str:
    token = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode("utf-8")
    return base64.b64encode(token).decode("utf-8")


def exchange_code_for_token(code: str) -> Dict[str, str]:
    headers = {
        "Authorization": f"Basic {_basic_auth_header()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }
    resp = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    now = int(time.time())
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "token_type": payload.get("token_type", "Bearer"),
        "expires_at": str(now + int(payload.get("expires_in", 3600))),
    }


def refresh_access_token(refresh_token: str) -> Dict[str, str]:
    headers = {
        "Authorization": f"Basic {_basic_auth_header()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    resp = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    now = int(time.time())
    result = {
        "access_token": payload["access_token"],
        "token_type": payload.get("token_type", "Bearer"),
        "expires_at": str(now + int(payload.get("expires_in", 3600))),
    }
    if payload.get("refresh_token"):
        result["refresh_token"] = payload["refresh_token"]
    return result


def get_current_user_profile(access_token: str) -> Dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(API_ME, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_valid_access_token(tokens: Dict[str, str]) -> Optional[str]:
    try:
        expires_at = int(tokens.get("expires_at", "0"))
    except ValueError:
        expires_at = 0
    now = int(time.time())
    if now < (expires_at - 30):
        return tokens.get("access_token")
    if not tokens.get("refresh_token"):
        return None
    refreshed = refresh_access_token(tokens["refresh_token"])
    tokens.update(refreshed)
    return tokens.get("access_token")

