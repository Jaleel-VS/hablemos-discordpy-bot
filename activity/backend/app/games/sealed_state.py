"""Sealed game state — encrypted + authenticated tokens the client holds.

The engine is stateless: game state round-trips through the client between
guesses. But state contains the **answer**, so it must not be readable or
forgeable by the client. We seal it with Fernet (AES-128-CBC + HMAC), so the
client gets an opaque token it can echo back but cannot decrypt or tamper with.

The key derives from ``DISCORD_CLIENT_SECRET`` (already a server-only secret),
so no new secret to manage. If the secret rotates, in-flight games become
undecryptable and the client simply starts a new game — acceptable.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class StateSealError(Exception):
    """Raised when a sealed-state token is missing, corrupt, or forged."""


def _fernet(secret: str) -> Fernet:
    # Fernet needs a 32-byte urlsafe-base64 key; derive it deterministically
    # from the client secret so the same secret always yields the same key.
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(secret: str, state: dict[str, Any]) -> str:
    """Serialize + encrypt state into an opaque token string."""
    raw = json.dumps(state, separators=(",", ":")).encode("utf-8")
    return _fernet(secret).encrypt(raw).decode("ascii")


def unseal(secret: str, token: str) -> dict[str, Any]:
    """Decrypt + deserialize a token back into state.

    Raises :class:`StateSealError` on any tampering/corruption so the route
    layer can return a clean 400 instead of leaking a stack trace.
    """
    if not isinstance(token, str) or not token:
        raise StateSealError("Missing game state")
    try:
        raw = _fernet(secret).decrypt(token.encode("ascii"))
    except (InvalidToken, ValueError) as exc:
        raise StateSealError("Invalid or tampered game state") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateSealError("Corrupt game state") from exc
    if not isinstance(data, dict):
        raise StateSealError("Corrupt game state")
    return data
