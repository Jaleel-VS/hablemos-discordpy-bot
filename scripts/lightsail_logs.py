"""Pull AWS Lightsail container logs into your terminal so they can be grepped/queried.

Uses the Lightsail ``GetContainerLog`` API (the same call the log forwarder in
``logforwarder/`` uses to ship logs to Axiom). It resolves a service's running
container automatically, fetches recent log events, and prints them as text
(default) or JSON (``--json``).

Lightsail keeps only ~3 days of container-log retention and has no native log
drain, so for *persistent* searchable history use the Axiom pipeline
(``logforwarder/``). This script is for quick, on-demand pulls.

Setup
-----
Authenticate with AWS first (the repo uses the ``Jaleel`` profile, e.g.
``jda`` to refresh Isengard creds). Then::

    # last 200 log lines from the bot service
    python scripts/lightsail_logs.py

    # a different service, only errors, as JSON for jq/grep
    python scripts/lightsail_logs.py --service hablemos-activity \\
        --filter ERROR --json

    # grep for the settlement crash
    python scripts/lightsail_logs.py --limit 1000 | grep "poll failed"

    # list the services and their containers, then exit
    python scripts/lightsail_logs.py --discover

Config via flags or env: ``--service`` / ``LIGHTSAIL_SERVICE`` (default
``hablemos-discordpy-bot``), ``--profile`` / ``AWS_PROFILE`` (default
``Jaleel``). ``--region`` defaults to ``us-east-1`` (where the services live)
and is deliberately **not** read from ``AWS_REGION`` — an ambient region can
point elsewhere and silently return no services.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta

import boto3

_DEFAULT_SERVICE = "hablemos-discordpy-bot"
_DEFAULT_REGION = "us-east-1"
_DEFAULT_PROFILE = "Jaleel"


def _client(region: str, profile: str | None):
    """Build a Lightsail client, honouring an explicit profile when given."""
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.client("lightsail", region_name=region)


def _running_containers(client, service: str) -> list[str]:
    """Return the container names of a service's current deployment."""
    resp = client.get_container_services(serviceName=service)
    services = resp.get("containerServices", [])
    if not services:
        return []
    current = services[0].get("currentDeployment") or {}
    return list((current.get("containers") or {}).keys())


def discover(client, region: str) -> None:
    """List every container service and its running containers, then return."""
    resp = client.get_container_services()
    services = resp.get("containerServices", [])
    if not services:
        print(
            f"No Lightsail container services found in {region}. "
            "Check --region (services live in us-east-1).",
            file=sys.stderr,
        )
        return
    for svc in services:
        name = svc.get("containerServiceName", "?")
        state = svc.get("state", "?")
        current = svc.get("currentDeployment") or {}
        containers = list((current.get("containers") or {}).keys())
        print(f"{name}  [{state}]  containers: {', '.join(containers) or '(none)'}")


def fetch_logs(
    client,
    service: str,
    container: str,
    *,
    limit: int,
    hours: float,
    log_filter: str | None,
) -> list[dict]:
    """Fetch up to ``limit`` recent log events for one container (paginated)."""
    start = datetime.now(UTC) - timedelta(hours=hours)
    kwargs: dict = {
        "serviceName": service,
        "containerName": container,
        "startTime": start,
        "endTime": datetime.now(UTC),
    }
    if log_filter:
        kwargs["filterPattern"] = log_filter

    events: list[dict] = []
    while True:
        resp = client.get_container_log(**kwargs)
        events.extend(resp.get("logEvents", []))
        token = resp.get("nextPageToken")
        if not token:
            break
        kwargs["pageToken"] = token

    # Newest events are most useful; keep the last `limit` in chronological order.
    events.sort(key=lambda e: e.get("createdAt") or datetime.min.replace(tzinfo=UTC))
    return events[-limit:]


def main() -> int:
    p = argparse.ArgumentParser(
        description="Fetch AWS Lightsail container logs for grep/query."
    )
    p.add_argument(
        "--service",
        default=os.getenv("LIGHTSAIL_SERVICE", _DEFAULT_SERVICE),
        help=f"Lightsail container service (default {_DEFAULT_SERVICE}).",
    )
    p.add_argument(
        "--container",
        default=None,
        help="Container name (defaults to the service's sole running container).",
    )
    p.add_argument(
        "--region",
        default=_DEFAULT_REGION,
        help=(
            f"AWS region (default {_DEFAULT_REGION} — where the services live). "
            "Not read from AWS_REGION, which may point elsewhere."
        ),
    )
    p.add_argument(
        "--profile",
        default=os.getenv("AWS_PROFILE", _DEFAULT_PROFILE),
        help=f"AWS profile (default {_DEFAULT_PROFILE}).",
    )
    p.add_argument("--limit", type=int, default=200, help="Max log lines (default 200).")
    p.add_argument(
        "--hours", type=float, default=24.0,
        help="How far back to look, in hours (default 24; Lightsail retains ~3 days).",
    )
    p.add_argument(
        "--filter", default=None,
        help='Lightsail filter pattern, e.g. "ERROR" or "asyncpg".',
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text lines.")
    p.add_argument(
        "--discover", action="store_true",
        help="List services and their containers with state, then exit.",
    )
    args = p.parse_args()

    client = _client(args.region, args.profile)

    if args.discover:
        discover(client, args.region)
        return 0

    container = args.container
    if not container:
        containers = _running_containers(client, args.service)
        if not containers:
            print(
                f"No running containers found for service {args.service!r}. "
                "Use --discover to list services.",
                file=sys.stderr,
            )
            return 1
        container = containers[0]

    events = fetch_logs(
        client,
        args.service,
        container,
        limit=args.limit,
        hours=args.hours,
        log_filter=args.filter,
    )

    if args.json:
        print(json.dumps(
            [
                {
                    "createdAt": (
                        e["createdAt"].isoformat() if e.get("createdAt") else None
                    ),
                    "message": e.get("message", ""),
                }
                for e in events
            ],
            indent=2,
        ))
    else:
        for e in events:
            ts = e["createdAt"].isoformat() if e.get("createdAt") else ""
            print(f"{ts} {e.get('message', '')}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
