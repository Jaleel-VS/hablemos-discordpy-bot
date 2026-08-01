#!/usr/bin/env python3
"""Poll Lightsail container logs for one or more services and ship them to Axiom.

Lightsail has no native log drain and only 3 days of retention, so we poll
`GetContainerLog` on an interval and forward new events to an Axiom dataset,
where they get 30-day retention, full-text query, charts, and alerts.

Dedup: Lightsail returns overlapping windows across polls, so we track the last
forwarded timestamp per (service, container) and only send strictly newer
events. Ties on the exact same millisecond are de-duplicated by a content hash
kept for the most recent timestamp.

Config via environment:
  AXIOM_TOKEN     Axiom API token (xaat-...)                     [required]
  AXIOM_DATASET   Axiom dataset name                             [default: hablemos]
  AXIOM_URL       Axiom ingest base URL                          [default: https://us-east-1.aws.edge.axiom.co]
  AWS_REGION      Lightsail region                               [default: us-east-1]
  SERVICES        Comma-separated service names to tail          [required]
  POLL_SECONDS    Seconds between polls                          [default: 20]
  LOOKBACK_SECONDS Initial window to pull on first poll          [default: 300]
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error

import boto3


AXIOM_TOKEN = os.environ["AXIOM_TOKEN"]
AXIOM_DATASET = os.environ.get("AXIOM_DATASET", "hablemos")
AXIOM_URL = os.environ.get("AXIOM_URL", "https://us-east-1.aws.edge.axiom.co").rstrip("/")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SERVICES = [s.strip() for s in os.environ["SERVICES"].split(",") if s.strip()]
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "20"))
LOOKBACK_SECONDS = int(os.environ.get("LOOKBACK_SECONDS", "300"))

INGEST_ENDPOINT = f"{AXIOM_URL}/v1/ingest/{AXIOM_DATASET}"

lightsail = boto3.client("lightsail", region_name=AWS_REGION)

# Per (service, container): last forwarded event datetime, and the set of
# content hashes already sent AT that exact timestamp (to dedupe ties).
_state = {}


def log(msg):
    print(f"[forwarder] {msg}", flush=True)


def list_containers(service):
    """Container names in the service's current deployment."""
    resp = lightsail.get_container_services(serviceName=service)
    svcs = resp.get("containerServices", [])
    if not svcs:
        return []
    cur = svcs[0].get("currentDeployment") or {}
    return list((cur.get("containers") or {}).keys())


def fetch_events(service, container, start_dt):
    """Return Lightsail log events for a container since start_dt (paginated)."""
    events = []
    kwargs = {
        "serviceName": service,
        "containerName": container,
        "startTime": start_dt,
    }
    while True:
        resp = lightsail.get_container_log(**kwargs)
        events.extend(resp.get("logEvents", []))
        token = resp.get("nextPageToken")
        if not token:
            break
        kwargs["pageToken"] = token
    return events


def ship(batch):
    """POST a batch of Axiom events. Returns number ingested."""
    if not batch:
        return 0
    body = json.dumps(batch).encode("utf-8")
    req = urllib.request.Request(
        INGEST_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {AXIOM_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8"))
            if resp.get("failed"):
                log(f"WARN: Axiom reported {resp['failed']} failed: {resp.get('failures')}")
            return resp.get("ingested", 0)
    except urllib.error.HTTPError as e:
        log(f"ERROR ingest HTTP {e.code}: {e.read().decode('utf-8')[:200]}")
        return 0
    except urllib.error.URLError as e:
        log(f"ERROR ingest network: {e}")
        return 0


def poll_once():
    total = 0
    for service in SERVICES:
        try:
            containers = list_containers(service)
        except Exception as e:
            log(f"WARN: could not list containers for {service}: {e}")
            continue
        for container in containers:
            key = (service, container)
            last_dt, last_hashes = _state.get(key, (None, set()))
            # boto3 wants a timezone-aware datetime; derive the start window.
            if last_dt is None:
                start_dt = _epoch_dt(time.time() - LOOKBACK_SECONDS)
            else:
                start_dt = last_dt
            try:
                events = fetch_events(service, container, start_dt)
            except Exception as e:
                log(f"WARN: get_container_log {service}/{container} failed: {e}")
                continue

            batch = []
            new_last_dt = last_dt
            new_hashes = set(last_hashes)
            for ev in events:
                ts = ev["createdAt"]  # tz-aware datetime from boto3
                msg = ev.get("message", "")
                h = hashlib.sha1(msg.encode("utf-8", "replace")).hexdigest()
                # Skip anything older than our high-water mark, or an exact
                # dup at the same millisecond we've already shipped.
                if last_dt is not None:
                    if ts < last_dt:
                        continue
                    if ts == last_dt and h in last_hashes:
                        continue
                batch.append({
                    "time": ts.isoformat(),
                    "data": {
                        "service": service,
                        "container": container,
                        "message": msg,
                    },
                })
                if new_last_dt is None or ts > new_last_dt:
                    new_last_dt = ts
                    new_hashes = {h}
                elif ts == new_last_dt:
                    new_hashes.add(h)

            sent = ship(batch)
            total += sent
            if new_last_dt is not None:
                _state[key] = (new_last_dt, new_hashes)
            if sent:
                log(f"{service}/{container}: +{sent} events")
    return total


def _epoch_dt(epoch):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def main():
    log(f"starting: services={SERVICES} region={AWS_REGION} "
        f"dataset={AXIOM_DATASET} poll={POLL_SECONDS}s")
    # Fail fast if Axiom is unreachable/misconfigured.
    startup = ship([{"data": {"service": "forwarder", "container": "self",
                              "message": "forwarder started"}}])
    log(f"startup ingest check: {startup} event(s) accepted")
    while True:
        try:
            poll_once()
        except Exception as e:
            log(f"ERROR poll loop: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
