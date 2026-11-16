# Listing 9.4 (classroom version) -- worker.py: the process that talks to
# the outside world. It reads pending outbox entries and performs them --
# charging the provider, then confirming or releasing the hold. Because the
# intent was durably recorded (Listing 9.3), a crash anywhere is recoverable:
# the entry is still pending, and the worker retries. This is the engine of
# "design for the absence of a shared transaction" (Chapter 7's cliff).
import datetime
import json
import time
import urllib.error
import urllib.request
from domain import _now
from storage import make_store

PROVIDER = "http://localhost:4000"


def _post(path, body, key, timeout=3, fail=None):
    headers = {"Content-Type": "application/json", "Idempotency-Key": key}
    if fail:
        headers["X-Demo-Fail"] = fail
    req = urllib.request.Request(PROVIDER + path, method="POST",
        data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.load(r)


def _get_charge(key, timeout=3):
    try:
        with urllib.request.urlopen(f"{PROVIDER}/charges/{key}", timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError:
        return None


def process_one(store, entry, fail=None, timeout=3):
    """Perform a single outbox entry. The idempotency key is DERIVED from
    the reservation id, so every retry of this entry uses the SAME key --
    the provider's Chapter 3 promise makes our retries safe across the
    boundary we don't own."""
    key = f"charge-{entry['reservation_id']}"
    charged, how = None, ""
    try:
        status, body = _post("/charges", {"amount": entry["amount"]}, key,
                             timeout=timeout, fail=fail)
        charged = body
    except urllib.error.HTTPError as e:
        if e.code == 402:                        # card declined: terminal
            _resolve(store, entry, release=True)
            return "declined -> hold released"
        raise
    except (urllib.error.URLError, TimeoutError):
        # Timeout: we DON'T KNOW if the charge happened. Ask.
        charged = _get_charge(key)
        if charged is None:
            _bump(store, entry["id"])            # still unknown; leave pending
            return "timeout, outcome unknown -> will retry"
        how = "TIMED OUT -> asked provider -> "

    if charged and charged.get("status") == "succeeded":
        confirmed = _resolve(store, entry, confirm=True, charge_id=charged["id"])
        if confirmed:
            return f"{how}charged {charged['id']} -> hold confirmed"
        return f"{how}charged {charged['id']} -> hold EXPIRED, refund owed"
    return "no-op"


def _resolve(store, entry, confirm=False, release=False, charge_id=None):
    """Apply the terminal result to BOTH the outbox and the reservation,
    in one transaction. Confirming may find the hold EXPIRED -- the one
    failure Chapter 7 said needs compensation across the boundary.
    Returns True only if the hold was actually confirmed."""
    confirmed = False
    with store.transaction() as state:
        ob = next(o for o in state["outbox"] if o["id"] == entry["id"])
        rr = state["reservations"][entry["reservation_id"]]
        if confirm:
            expires = datetime.datetime.fromisoformat(rr["hold_expires_at"])
            if rr["status"] == "held" and expires > _now():
                rr["status"] = "confirmed"
                ob["status"], ob["charge_id"] = "done", charge_id
                confirmed = True
            else:
                # Charged, but the hold expired first. Money taken, no seat.
                # Compensation: refund on THEIR side. It too can fail (9.6).
                ob["status"], ob["charge_id"] = "needs_refund", charge_id
        if release:
            if rr["status"] == "held":
                rr["status"] = "released"
            ob["status"] = "failed"
    return confirmed


def _bump(store, entry_id):
    with store.transaction() as state:
        ob = next(o for o in state["outbox"] if o["id"] == entry_id)
        ob["attempts"] += 1


def run_once(store, fail=None, timeout=3):
    """Read the pending entries, then process them one by one. (The
    PostgreSQL version used FOR UPDATE SKIP LOCKED so many workers could
    run at once; this classroom version assumes a single worker.)"""
    pending = [o for o in store.snapshot()["outbox"] if o["status"] == "pending"]
    return [process_one(store, e, fail=fail, timeout=timeout) for e in pending]


if __name__ == "__main__":
    store = make_store()
    print("worker running (Ctrl+C to stop)")
    try:
        while True:
            for msg in run_once(store):
                print("  worker:", msg)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
