"""Pull Railway logs into your terminal so they can be grepped/queried.

Uses Railway's public GraphQL API (the same one the dashboard uses). It
resolves the service's latest deployment automatically, then fetches its
runtime logs and prints them as text (default) or JSON (--json).

Setup
-----
1. Create an *account* token at https://railway.com/account/tokens
   (no workspace = broadest scope) and export it:

       export RAILWAY_TOKEN="..."

2. Find the service + environment IDs. Either run discovery:

       python scripts/railway_logs.py --discover

   or copy them from the dashboard (Cmd/Ctrl+K → "Copy Service ID" /
   "Copy Environment ID"). Then export them, or pass them as flags:

       export RAILWAY_SERVICE_ID="..."
       export RAILWAY_ENVIRONMENT_ID="..."

Examples
--------
    # last 200 runtime log lines
    python scripts/railway_logs.py

    # only errors, as JSON, piped to jq / grep
    python scripts/railway_logs.py --filter "@level:error" --json

    # grep for the settlement crash
    python scripts/railway_logs.py --limit 1000 | grep "poll failed"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://backboard.railway.com/graphql/v2"


def _gql(token: str, query: str, variables: dict | None = None) -> dict:
    """POST a GraphQL request; return the `data` object or raise."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "hablemos-bot-logs/1.0 (+https://github.com/Jaleel-VS/hablemos-discordpy-bot)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise SystemExit(f"Railway API HTTP {exc.code}: {detail}") from exc
    if payload.get("errors"):
        raise SystemExit("Railway API error: " + json.dumps(payload["errors"], indent=2))
    return payload["data"]


def discover(token: str) -> None:
    """Print every project → service → environment with their IDs.

    Doubles as a connectivity/token check.
    """
    query = """
    query {
      projects {
        edges {
          node {
            id
            name
            services { edges { node { id name } } }
            environments { edges { node { id name } } }
          }
        }
      }
    }
    """
    data = _gql(token, query)
    projects = data["projects"]["edges"]
    if not projects:
        print("No projects found for this token.")
        return
    for pe in projects:
        proj = pe["node"]
        print(f"\nProject: {proj['name']}  (id: {proj['id']})")
        print("  Services:")
        for se in proj["services"]["edges"]:
            s = se["node"]
            print(f"    - {s['name']:<24} {s['id']}")
        print("  Environments:")
        for ee in proj["environments"]["edges"]:
            e = ee["node"]
            print(f"    - {e['name']:<24} {e['id']}")


def latest_deployment_id(token: str, service_id: str, environment_id: str) -> str:
    """Return the most recent deployment id for a service in an environment."""
    query = """
    query($serviceId: String!, $environmentId: String!) {
      deployments(
        first: 1
        input: { serviceId: $serviceId, environmentId: $environmentId }
      ) {
        edges { node { id status createdAt } }
      }
    }
    """
    data = _gql(token, query, {"serviceId": service_id, "environmentId": environment_id})
    edges = data["deployments"]["edges"]
    if not edges:
        raise SystemExit("No deployments found for that service/environment.")
    node = edges[0]["node"]
    print(f"# latest deployment {node['id']} ({node['status']}, {node['createdAt']})", file=sys.stderr)
    return node["id"]


def fetch_logs(token: str, deployment_id: str, limit: int, log_filter: str | None) -> list[dict]:
    query = """
    query($deploymentId: String!, $limit: Int, $filter: String) {
      deploymentLogs(deploymentId: $deploymentId, limit: $limit, filter: $filter) {
        message
        severity
        timestamp
      }
    }
    """
    variables = {"deploymentId": deployment_id, "limit": limit, "filter": log_filter}
    data = _gql(token, query, variables)
    return data["deploymentLogs"]


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch Railway runtime logs via the public API.")
    p.add_argument("--service", default=os.getenv("RAILWAY_SERVICE_ID"),
                   help="Service ID (or set RAILWAY_SERVICE_ID).")
    p.add_argument("--environment", default=os.getenv("RAILWAY_ENVIRONMENT_ID"),
                   help="Environment ID (or set RAILWAY_ENVIRONMENT_ID).")
    p.add_argument("--deployment", default=os.getenv("RAILWAY_DEPLOYMENT_ID"),
                   help="Deployment ID (skips lookup; or set RAILWAY_DEPLOYMENT_ID).")
    p.add_argument("--discover", action="store_true",
                   help="List your projects/services/environments with IDs, then exit.")
    p.add_argument("--limit", type=int, default=200, help="Max log lines (default 200).")
    p.add_argument("--filter", default=None,
                   help='Railway log filter, e.g. "@level:error" or free text.')
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text lines.")
    args = p.parse_args()

    token = os.getenv("RAILWAY_TOKEN")
    if not token:
        raise SystemExit("Set RAILWAY_TOKEN (https://railway.com/account/tokens).")

    if args.discover:
        discover(token)
        return 0

    deployment_id = args.deployment
    if not deployment_id:
        if not (args.service and args.environment):
            raise SystemExit(
                "Provide --deployment, or --service and --environment "
                "(or the matching RAILWAY_* env vars)."
            )
        deployment_id = latest_deployment_id(token, args.service, args.environment)

    logs = fetch_logs(token, deployment_id, args.limit, args.filter)

    if args.json:
        print(json.dumps(logs, indent=2))
    else:
        for entry in logs:
            ts = entry.get("timestamp", "")
            sev = entry.get("severity") or ""
            sev_tag = f"[{sev}] " if sev else ""
            print(f"{ts} {sev_tag}{entry.get('message', '')}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
