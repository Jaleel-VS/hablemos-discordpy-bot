"""Discord OAuth2 helpers for the Activity handshake.

The iframe SPA cannot hold the ``client_secret``, so the code→token exchange
happens here, server-side. We also expose a verification helper that resolves
the *real* Discord user from an access token via ``users/@me`` — the iframe is
tamperable, so a client-sent user id must never be trusted for anything that
posts to a channel.
"""
import asyncio
import logging
from time import perf_counter

import httpx

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api"
TOKEN_URL = f"{DISCORD_API_BASE}/oauth2/token"
USER_URL = f"{DISCORD_API_BASE}/users/@me"


class DiscordOAuthError(Exception):
    """Raised when a Discord OAuth call fails."""


async def _request_with_retry(
    method: str,
    url: str,
    *,
    retries: int = 3,
    **kwargs,
) -> httpx.Response:
    """Call the Discord API, honoring 429 rate limits (per the official SDK
    example's ``fetchAndRetry``): on 429, wait ``retry_after`` and retry; on a
    transport error, back off briefly and retry.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.request(method, url, **kwargs)
            except httpx.HTTPError:
                if attempt == retries:
                    raise
                await asyncio.sleep(1.0)
                continue
            if resp.status_code == httpx.codes.TOO_MANY_REQUESTS and attempt < retries:
                retry_after = resp.headers.get("retry-after")
                try:
                    wait = float(retry_after) if retry_after is not None else 1.0
                except ValueError:
                    wait = 1.0
                await asyncio.sleep(wait)
                continue
            return resp
    # Unreachable: the loop either returns a response or raises.
    raise DiscordOAuthError("Discord request failed after retries")


async def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
) -> str:
    """Exchange an OAuth2 authorization code for an access token.

    Returns the bearer access token. Raises :class:`DiscordOAuthError` on any
    non-2xx response so the caller can surface a friendly error and log the
    detail server-side.
    """
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
    }
    resp = await _request_with_retry(
        "POST",
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != httpx.codes.OK:
        # Never leak Discord's raw body to the user; log it, raise generic.
        logger.warning("Token exchange failed: %s %s", resp.status_code, resp.text)
        raise DiscordOAuthError("Failed to exchange authorization code")

    payload = resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        logger.warning("Token exchange succeeded but no access_token in payload")
        raise DiscordOAuthError("Discord returned no access token")
    return access_token


async def fetch_user(access_token: str) -> dict[str, str]:
    """Resolve the authenticated Discord user from an access token.

    Returns a dict with ``id``, ``username``, ``global_name`` (may be empty),
    and ``avatar`` (may be empty). This is the authoritative identity — the
    server trusts this, not anything the client claims.
    """
    # TEMP measurement (remove after the snappiness investigation): time the
    # users/@me round trip. This runs on every start/guess/stats, so if it's
    # large it explains the "less snappy" feel. See docs/playbook.md.
    _t0 = perf_counter()
    resp = await _request_with_retry(
        "GET",
        USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    logger.info("fetch_user users/@me round_trip_ms=%.1f", (perf_counter() - _t0) * 1000)
    if resp.status_code != httpx.codes.OK:
        logger.warning("users/@me failed: %s %s", resp.status_code, resp.text)
        raise DiscordOAuthError("Failed to fetch Discord user")

    user = resp.json()
    return {
        "id": str(user.get("id", "")),
        "username": str(user.get("username", "")),
        "global_name": str(user.get("global_name") or ""),
        "avatar": str(user.get("avatar") or ""),
    }
