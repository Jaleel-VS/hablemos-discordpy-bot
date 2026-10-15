"""Player-experience judging with TypeSafe's Jev model.

The simulator measures power; it can't tell whether a round would *feel*
good. ``judge_run`` sends each player's round diary (plain facts from
``runner._diaries``: ranks, raids suffered, losses, wins, evacuations,
alliance outcome) to Jev with four narrow questions and turns the typed
answers into run metrics:

- ``frustration`` (Score, 0 = having fun … 4 = miserable)
- ``quit_risk`` (Noul: would a casual player stop logging in?)
- ``unfair`` (Noul: did it look like bullying rather than competition?)
- ``proud`` (Noul: would they be proud of their round?)

The diary omits archetype and whether the agent quit, so ``quit_risk`` is
an independent guess; ``exp_quit_agreement`` compares it with the
simulator's own quit model. Jev's answers are calibrated judgments, not
ground truth — treat them as a second opinion to check against a beta.

Needs ``TYPESAFE_API_KEY``. Uses the HTTP API directly through ``httpx``
(already an Activity dependency) — see https://docs.typesafe.ai/api.md.
"""
import logging
import os
import statistics
from concurrent.futures import ThreadPoolExecutor

import httpx

from .runner import RunResult

logger = logging.getLogger(__name__)

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
API_KEY_ENV = "TYPESAFE_API_KEY"
CONCURRENCY = 8
TIMEOUT_S = 30.0

QUESTIONS: dict[str, dict] = {
    "frustration": {
        "type": "score",
        "instructions": (
            "This is one player's diary from a 4-week online strategy game "
            "played casually in a Discord community, a few short check-ins a "
            "day. How frustrated would a typical casual player be by the end "
            "of this round?"
        ),
        "criteria": [
            "Having fun: setbacks were rare or quickly recovered from",
            "Mildly annoyed: a few setbacks that didn't change their round",
            "Frustrated: repeated setbacks that noticeably slowed them down",
            "Very frustrated: kept losing progress to others and fell behind",
            "Miserable: felt helpless; the round was ruined for them",
        ],
    },
    "quit_risk": {
        "type": "noul",
        "instructions": (
            "Based on this diary from a casual 4-week online strategy game, "
            "would a typical casual player have stopped logging in before "
            "the round ended?"
        ),
        "criteria": {
            "true": "They would likely give up on this round early",
            "false": "They would likely keep playing to the end",
        },
    },
    "unfair": {
        "type": "noul",
        "instructions": (
            "Did this player suffer repeated attacks from others that a "
            "casual player would see as unfair bullying rather than fair "
            "competition?"
        ),
    },
    "proud": {
        "type": "noul",
        "instructions": (
            "Would this player feel proud of how their round went in this "
            "casual online strategy game?"
        ),
    },
}


class JudgeError(RuntimeError):
    """The experience judge couldn't run (missing key or API failure)."""


def _api_key() -> str:
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise JudgeError(f"set {API_KEY_ENV} to judge player experience")
    return key


def _ask(client: httpx.Client, diary: dict) -> dict[str, float]:
    response = client.post(
        API_URL,
        json={"state": diary, "model": MODEL, "questions": QUESTIONS},
    )
    if response.status_code != 200:
        raise JudgeError(
            f"TypeSafe returned {response.status_code}: {response.text[:200]}"
        )
    answers = response.json()["answers"]
    return {
        "frustration": float(answers["frustration"]["score"]),
        "quit_risk": float(answers["quit_risk"]["noul"]),
        "unfair": float(answers["unfair"]["noul"]),
        "proud": float(answers["proud"]["noul"]),
    }


def judge_run(
    result: RunResult,
    *,
    client: httpx.Client | None = None,
    concurrency: int = CONCURRENCY,
) -> RunResult:
    """Judge every player's diary; adds rows and ``exp_*`` metrics."""
    owned = client is None
    if client is None:
        client = httpx.Client(
            headers={"Authorization": f"Bearer {_api_key()}"},
            timeout=TIMEOUT_S,
        )
    pids = sorted(result.diaries)
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            answers = list(
                pool.map(lambda pid: _ask(client, result.diaries[pid]), pids)
            )
    except httpx.HTTPError as exc:
        raise JudgeError(f"TypeSafe request failed: {exc}") from exc
    finally:
        if owned:
            client.close()
    players = {p["player_id"]: p for p in result.players}
    rows = []
    for pid, ans in zip(pids, answers, strict=True):
        rows.append(
            {
                "player_id": pid,
                "archetype": players[pid]["archetype"],
                "quit_day": players[pid]["quit_day"],
                **ans,
            }
        )
    result.experience = rows
    result.metrics.update(experience_metrics(rows))
    return result


def experience_metrics(rows: list[dict]) -> dict[str, float]:
    """Aggregate judged rows into run metrics."""
    if not rows:
        return {}
    metrics = {
        "exp_frustration": statistics.mean(r["frustration"] for r in rows),
        "exp_quit_risk": statistics.mean(r["quit_risk"] for r in rows),
        "exp_unfair_share": statistics.mean(
            1.0 if r["unfair"] > 0.5 else 0.0 for r in rows
        ),
        "exp_proud": statistics.mean(r["proud"] for r in rows),
        "exp_quit_agreement": statistics.mean(
            1.0 if (r["quit_risk"] > 0.5) == (r["quit_day"] is not None) else 0.0
            for r in rows
        ),
    }
    by_arch: dict[str, list[dict]] = {}
    for r in rows:
        by_arch.setdefault(r["archetype"], []).append(r)
    for arch, group in by_arch.items():
        metrics[f"exp_frustration_{arch}"] = statistics.mean(
            r["frustration"] for r in group
        )
        metrics[f"exp_quit_risk_{arch}"] = statistics.mean(
            r["quit_risk"] for r in group
        )
    return metrics
