# Listing 9.4 -- worker.py: the process that talks to the outside world.
# It reads pending outbox entries and performs them -- charging the
# provider, then confirming or releasing the hold. Because the intent was
# durably recorded (Listing 9.3), a crash anywhere is recoverable: the
# entry is still pending, and the worker retries. This is the engine of
# "design for the absence of a shared transaction" (Chapter 7's cliff).
import sys
import time
import urllib.request
import urllib.error
import json
from sqlalchemy import select, text
from storage import make_session_factory, OutboxRow, ReservationRow, EventRow
from domain import _now

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

def process_one(sf, entry, fail=None):
    """Perform a single outbox entry. The idempotency key is DERIVED from
    the reservation id, so every retry of this entry uses the SAME key --
    the provider's Chapter 3 promise makes our retries safe across the
    boundary we don't own."""
    key = f"charge-{entry.reservation_id}"
    charged = None
    try:
        status, body = _post("/charges", {"amount": entry.amount}, key, fail=fail)
        charged = body
    except (urllib.error.HTTPError,) as e:
        if e.code == 402:                        # card declined: terminal
            _resolve(sf, entry, outcome="failed", release=True)
            return "declined -> hold released"
        raise
    except (urllib.error.URLError, TimeoutError) as e:
        # Timeout: we DON'T KNOW if the charge happened. Ask.
        charged = _get_charge(key)
        if charged is None:
            entry_bump(sf, entry.id)             # still unknown; leave pending
            return "timeout, outcome unknown -> will retry"

    if charged and charged.get("status") == "succeeded":
        _resolve(sf, entry, outcome="done", confirm=True,
                 charge_id=charged["id"])
        return f"charged {charged['id']} -> hold confirmed"
    return "no-op"

def _resolve(sf, entry, outcome, confirm=False, release=False, charge_id=None):
    """Apply the terminal result to BOTH the outbox and the reservation,
    in one transaction. Confirming may find the hold EXPIRED -- the one
    failure Chapter 7 said needs compensation across the boundary."""
    with sf() as s:
        ob = s.get(OutboxRow, entry.id)
        rr = s.get(ReservationRow, entry.reservation_id)
        if confirm:
            if rr.status == "held" and rr.hold_expires_at > _now():
                rr.status = "confirmed"
                ob.status, ob.charge_id = "done", charge_id
            else:
                # Charged, but the hold expired first. Money taken, no seat.
                # Compensation: refund on THEIR side. It too can fail (9.6).
                ob.status, ob.charge_id = "needs_refund", charge_id
        if release:
            if rr.status == "held":
                rr.status = "released"
            ob.status = "failed"
        s.commit()

def entry_bump(sf, entry_id):
    with sf() as s:
        ob = s.get(OutboxRow, entry_id)
        ob.attempts += 1
        s.commit()

def run_once(sf, fail=None):
    """Claim pending entries and process them. FOR UPDATE SKIP LOCKED lets
    many workers run without stepping on each other."""
    results = []
    with sf() as s:
        rows = s.scalars(select(OutboxRow)
                         .where(OutboxRow.status == "pending")
                         .with_for_update(skip_locked=True)).all()
        entries = [type("E", (), {"id": r.id, "reservation_id": r.reservation_id,
                                  "amount": r.amount})() for r in rows]
        s.commit()
    for e in entries:
        results.append(process_one(sf, e, fail=fail))
    return results

if __name__ == "__main__":
    url = "postgresql+psycopg2://encore:encore@localhost/encore"
    sf, _ = make_session_factory(url)
    while True:
        for msg in run_once(sf):
            print("  worker:", msg)
        time.sleep(1)
