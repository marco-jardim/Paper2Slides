"""
OAuth manager for ChatGPT Plus/Pro login (headless PKCE flow).

Flow:
  1. start_flow(port)  → returns auth_url (printed to terminal + sent to frontend)
  2. User opens URL in browser, authorizes on auth.openai.com
  3. OpenAI redirects to  http://localhost:{port}/auth/oauth/callback?code=…&state=…
  4. exchange_code(code, port)  → stores access_token + refresh_token
  5. Frontend polls /auth/oauth/status until authenticated=true
"""

import hashlib
import base64
import secrets
import json
import time
import logging
from typing import Optional, Tuple, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# ── OpenAI OAuth constants ──────────────────────────────────────────────────
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # Official OpenAI Codex CLI
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
SCOPE = "openid profile email offline_access"

# ChatGPT backend
CHATGPT_BASE_URL = "https://chatgpt.com/backend-api"
CODEX_RESPONSES = "/codex/responses"

# ── PKCE helpers ────────────────────────────────────────────────────────────


def _generate_pkce() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


# ── OAuthManager ────────────────────────────────────────────────────────────


class OAuthManager:
    """Singleton that manages the OAuth lifecycle for one user session."""

    def __init__(self):
        self._state: Optional[str] = None
        self._verifier: Optional[str] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._account_id: Optional[str] = None
        self._email: Optional[str] = None

    # ── flow start ──────────────────────────────────────────────────────────

    def start_flow(self, port: int) -> str:
        """
        Generate PKCE + state, return the full authorization URL.
        Also prints the URL to stdout so the headless CLI user can open it.
        """
        verifier, challenge = _generate_pkce()
        state = secrets.token_hex(16)

        self._state = state
        self._verifier = verifier

        redirect_uri = f"http://localhost:{port}/auth/oauth/callback"

        params = "&".join(
            [
                "response_type=code",
                f"client_id={CLIENT_ID}",
                f"redirect_uri={redirect_uri}",
                f"scope={SCOPE}",
                f"code_challenge={challenge}",
                "code_challenge_method=S256",
                f"state={state}",
                "id_token_add_organizations=true",
                "codex_cli_simplified_flow=true",
                "originator=codex_cli_rs",
            ]
        )
        auth_url = f"{AUTHORIZE_URL}?{params}"

        # ── headless print ──────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("  ChatGPT OAuth — open this URL in your browser:")
        print()
        print(f"  {auth_url}")
        print()
        print("  Waiting for callback on", redirect_uri, "…")
        print("=" * 70 + "\n")

        return auth_url

    # ── state validation ────────────────────────────────────────────────────

    def validate_state(self, state: str) -> bool:
        return bool(self._state and self._state == state)

    # ── code exchange ───────────────────────────────────────────────────────

    async def exchange_code(self, code: str, port: int) -> bool:
        """POST to TOKEN_URL to get access + refresh tokens."""
        redirect_uri = f"http://localhost:{port}/auth/oauth/callback"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    TOKEN_URL,
                    json={
                        "grant_type": "authorization_code",
                        "client_id": CLIENT_ID,
                        "code": code,
                        "code_verifier": self._verifier,
                        "redirect_uri": redirect_uri,
                    },
                )
            if resp.status_code != 200:
                logger.error(
                    "Token exchange failed: %s %s", resp.status_code, resp.text
                )
                return False
            data = resp.json()
            self._store_tokens(data)
            return True
        except Exception as e:
            logger.error("Token exchange error: %s", e)
            return False

    # ── token refresh ───────────────────────────────────────────────────────

    async def _refresh(self) -> bool:
        if not self._refresh_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    TOKEN_URL,
                    json={
                        "grant_type": "refresh_token",
                        "client_id": CLIENT_ID,
                        "refresh_token": self._refresh_token,
                    },
                )
            if resp.status_code != 200:
                logger.warning("Token refresh failed: %s", resp.status_code)
                return False
            self._store_tokens(resp.json())
            return True
        except Exception as e:
            logger.error("Token refresh error: %s", e)
            return False

    def _store_tokens(self, data: dict):
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._expires_at = time.time() + data.get("expires_in", 3600) - 60
        self._decode_jwt(self._access_token)
        logger.info("OAuth tokens stored for %s", self._email)

    # ── JWT decode ──────────────────────────────────────────────────────────

    def _decode_jwt(self, token: str):
        parts = token.split(".")
        if len(parts) < 2:
            return
        try:
            pad = 4 - len(parts[1]) % 4
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * pad))
            auth = payload.get("https://api.openai.com/auth", {})
            self._account_id = auth.get("chatgpt_account_id")
            self._email = payload.get("email")
        except Exception as e:
            logger.warning("JWT decode error: %s", e)

    # ── public helpers ──────────────────────────────────────────────────────

    def is_authenticated(self) -> bool:
        return bool(self._access_token)

    async def get_token(self) -> Optional[str]:
        """Return a valid access token, refreshing if expired."""
        if not self._access_token:
            return None
        if time.time() > self._expires_at:
            if not await self._refresh():
                return None
        return self._access_token

    def get_status(self) -> Dict[str, Any]:
        return {
            "authenticated": self.is_authenticated(),
            "email": self._email,
            "account_id": self._account_id,
        }

    def get_chatgpt_headers(self, token: str) -> dict:
        headers = {
            "Authorization": f"Bearer {token}",
            "originator": "codex_cli_rs",
            "OpenAI-Beta": "responses=experimental",
            "Content-Type": "application/json",
        }
        if self._account_id:
            headers["chatgpt-account-id"] = self._account_id
        return headers

    def logout(self):
        self._state = self._verifier = self._access_token = None
        self._refresh_token = None
        self._expires_at = 0.0
        self._account_id = self._email = None
        logger.info("OAuth session cleared")


# ── module-level singleton ───────────────────────────────────────────────────
oauth_manager = OAuthManager()
