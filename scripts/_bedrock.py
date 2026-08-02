"""Shared Amazon Bedrock helpers for the offline content scripts.

Both the cloze **generator** (``generate_cloze_sentences.py``) and the cloze
**reviewer** (``review_cloze_sentences.py``) talk to Bedrock the same way: via
the AWS CLI using the author's ``bedrock-how`` profile (the same path the shell
``how``/``howdo`` helpers use). This module is the single place that knows how
to authenticate, send a ``converse`` request, and pull a JSON array out of the
model's raw text — so the two scripts can't drift apart.

Nothing here runs at Activity runtime; these are dev/build-time utilities.
"""
from __future__ import annotations

import json
import re
import subprocess
import unicodedata

# ── AWS CLI configuration ────────────────────────────────────────────────────
# Mirrors the ~/.zshrc `_bedrock_ask` helper so behaviour matches the user's
# working setup. Region is fixed to the tested pairing; the model is per-call so
# the reviewer can use a *different* (stronger) model than the generator.
ACCOUNT = "195950944512"
ROLE = "Jaleel"
PROVIDER = "isengard"
PROFILE = "bedrock-how"
REGION = "us-east-1"

#: Default generation model (Claude Haiku 4.5) — fast + cheap for bulk content.
MODEL_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
#: A stronger model for the review pass, so verification isn't the same model
#: grading its own homework. Opus 4.8 catches subtler grammar/semantic errors.
MODEL_OPUS = "us.anthropic.claude-opus-4-8"


def bedrock_auth() -> None:
    """Refresh the bedrock-how credential profile (best-effort, silent)."""
    subprocess.run(
        [
            "ada", "credentials", "update",
            "--account", ACCOUNT, "--role", ROLE,
            "--provider", PROVIDER, "--profile", PROFILE, "--once",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def bedrock_converse(
    prompt: str, *, model: str, max_tokens: int = 4096, temperature: float | None = 0.4,
) -> str:
    """Send one prompt to Bedrock via the AWS CLI, returning the model text.

    Passes the request body as ``--cli-input-json`` (a JSON string) rather than
    an inline ``--messages`` argument, so sentence text with quotes/newlines
    can't break shell/CLI parsing. Raises ``RuntimeError`` on any CLI failure.

    ``temperature`` is omitted from the request when ``None`` — some newer
    models (e.g. Opus 4.8) reject the deprecated ``temperature`` field and error
    if it's present.
    """
    inference: dict[str, object] = {"maxTokens": max_tokens}
    if temperature is not None:
        inference["temperature"] = temperature
    request = {
        "modelId": model,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": inference,
    }
    proc = subprocess.run(
        [
            "aws", "bedrock-runtime", "converse",
            "--region", REGION, "--profile", PROFILE,
            "--cli-input-json", json.dumps(request),
            "--query", "output.message.content[0].text",
            "--output", "text",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"bedrock converse failed (exit {proc.returncode}): "
            f"{proc.stderr.strip()[:400]}"
        )
    return proc.stdout


def extract_json_array(text: str) -> list:
    """Parse a JSON array out of the model's raw text.

    Tolerates stray markdown fences or leading/trailing prose by slicing from
    the first ``[`` to the last ``]``. Returns ``[]`` if nothing parses.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def norm(text: str) -> str:
    """Lowercase + NFC-normalize + collapse whitespace for comparison/dedup."""
    return " ".join(unicodedata.normalize("NFC", text).strip().lower().split())


# Private-use codepoint that shields ñ/Ñ from the combining-mark strip.
_ENYE_SENTINEL = "\uE000"


def accent_key(text: str) -> str:
    """Accent-stripped comparison key, preserving ñ as a letter.

    Mirrors ``app.games.conjugation.normalize._strip_accents`` so this key
    matches the runtime grader's notion of "equal ignoring accents" (its CLOSE
    tier). Used to reject a distractor that differs from the answer only by
    accents (which the grader would accept as correct).
    """
    normalized = unicodedata.normalize("NFC", text).strip().lower()
    shielded = normalized.replace("ñ", _ENYE_SENTINEL)
    decomposed = unicodedata.normalize("NFD", shielded)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.replace(_ENYE_SENTINEL, "ñ").split())
