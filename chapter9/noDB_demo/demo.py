# demo.py (classroom version) -- drive the reserve-hold-charge-confirm flow
# through every branch of Chapter 9. No database, nothing to install.
#
#   python3 demo.py              run every branch in order
#   python3 demo.py list         show the branch names
#   python3 demo.py timeout      run one branch (or several: happy decline)
#
# The payment provider is started automatically on :4000 if it is not
# already running. State lives in encore_state.json, next to this file.
import atexit
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from domain import _now
from storage import make_store, Repository
from worker import run_once, PROVIDER

HERE = os.path.dirname(os.path.abspath(__file__))
store = make_store()
repo = Repository(store)


# ---- the provider: a separate process, as the chapter insists -----------
def _provider_up():
    try:
        urllib.request.urlopen(f"{PROVIDER}/charges/ping", timeout=1)
    except urllib.error.HTTPError:
        return True                      # it answered (404): it is up
    except OSError:
        return False
    return True


def ensure_provider():
    if _provider_up():
        return
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "payment_provider.py")],
                            stdout=subprocess.DEVNULL)
    atexit.register(proc.terminate)
    for _ in range(50):
        if _provider_up():
            return
        time.sleep(0.1)
    sys.exit("could not start payment_provider.py on :4000")


# ---- helpers -------------------------------------------------------------
def reset(capacity=2):
    with store.transaction() as state:
        state["events"] = {"ev_103": {"title": "Film Society", "capacity": capacity}}
        state["reservations"], state["outbox"] = {}, []
        state["next_outbox_id"] = 1


def seats():
    return repo.get("ev_103").seats_left()


def reserve(hold_seconds=900):
    """Step 1: lock event, create hold, enqueue charge -- ONE transaction."""
    rid = f"res_{uuid.uuid4().hex[:6]}"
    with repo.unit_of_work() as uow:
        event = uow.get_event("ev_103", lock=True)
        r = event.hold(rid, hold_seconds=hold_seconds)
        uow.save_event(event)
        uow.enqueue("charge", rid, amount=1500)     # $15.00
    return rid


def status(rid):
    """(reservation status, outbox entry status)"""
    state = store.snapshot()
    rr = state["reservations"].get(rid)
    ob = next((o for o in state["outbox"] if o["reservation_id"] == rid), None)
    return (rr["status"] if rr else None), (ob["status"] if ob else None)


def pending():
    return [o for o in store.snapshot()["outbox"] if o["status"] == "pending"]


def expire_hold(rid):
    with store.transaction() as state:
        state["reservations"][rid]["hold_expires_at"] = (
            _now() - datetime.timedelta(seconds=1)).isoformat()


def call_provider(path, body, key, fail=None):
    """A raw call, so the class can see status codes and replay headers."""
    headers = {"Content-Type": "application/json", "Idempotency-Key": key}
    if fail:
        headers["X-Demo-Fail"] = fail
    req = urllib.request.Request(PROVIDER + path, method="POST",
        data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.load(r), r.headers.get("Idempotency-Replayed")
    except urllib.error.HTTPError as e:
        return e.code, json.load(e), None


def branch(name, fail=None, hold_seconds=900, expire_before_worker=False):
    print(f"\n=== {name} ===")
    reset()
    print(f"  seats before: {seats()}")
    rid = reserve(hold_seconds=hold_seconds)
    print(f"  after hold:   seats {seats()}, reservation {status(rid)}")
    if expire_before_worker:
        expire_hold(rid)                 # force the hold to expire first
        print("  (hold expired before worker ran)")
    for msg in run_once(store, fail=fail):
        print("  worker:", msg)
    print(f"  final:        seats {seats()}, reservation {status(rid)}")
    return rid


# ---- the branches --------------------------------------------------------
def happy():
    branch("HAPPY PATH: charge succeeds")


def decline():
    branch("DECLINE: card refused -> hold released, seat freed", fail="decline")


def expiry():
    branch("EXPIRY: hold dies before charge confirms -> needs refund",
           expire_before_worker=True)


def rollback():
    """Section 9.2: the hold and the intent commit together OR NOT AT ALL."""
    print("\n=== ROLLBACK: failure inside the transaction -> nothing is written ===")
    reset()
    try:
        with repo.unit_of_work() as uow:
            event = uow.get_event("ev_103", lock=True)
            event.hold("res_doomed")
            uow.save_event(event)
            uow.enqueue("charge", "res_doomed", amount=1500)
            raise RuntimeError("something broke before COMMIT")
    except RuntimeError as e:
        print(f"  transaction aborted: {e}")
    print(f"  seats {seats()}, pending outbox entries: {len(pending())}"
          "  (no hold, no intent)")


def crash():
    """Section 9.2: a REAL process crash between the hold and the charge."""
    print("\n=== CRASH: app dies after the hold commits, before the worker runs ===")
    reset()
    # A child process reserves a seat and is then killed without cleanup.
    child = subprocess.run([sys.executable, os.path.abspath(__file__), "_reserve_and_die"])
    print(f"held + intent committed. The app process CRASHED "
          f"(exit code {child.returncode}; worker never ran).")
    print(f"after 'restart': {len(pending())} pending outbox entry survived the crash")
    rid = pending()[0]["reservation_id"]
    for msg in run_once(store):
        print("  recovered worker:", msg)
    print(f"final reservation status: {status(rid)[0]}")


def _reserve_and_die():
    reserve()
    os._exit(1)                          # die instantly: no cleanup, no worker


def timeout():
    """Section 9.3: the provider takes the charge and loses the reply."""
    print("\n=== TIMEOUT: charge taken, reply lost -> ask, do not guess ===")
    reset()
    rid = reserve()
    print(f"  after hold:   seats {seats()}, reservation {status(rid)}")
    print("  (worker waits 2 seconds for a reply that never comes...)")
    for msg in run_once(store, fail="timeout", timeout=2):
        print("  worker:", msg)
    print(f"  final:        seats {seats()}, reservation {status(rid)}")
    # Show the second safeguard directly: the same key cannot charge twice.
    code, body, replayed = call_provider("/charges", {"amount": 1500}, f"charge-{rid}")
    print(f"  same key sent again: ({code}, {body['id']}), "
          f"Idempotency-Replayed={replayed} -> no second charge")


def refund():
    """Section 9.6: the compensation is itself a call that can fail."""
    rid = branch("REFUND: compensation can fail too", expire_before_worker=True)
    entry = next(o for o in store.snapshot()["outbox"] if o["reservation_id"] == rid)
    key, body = f"refund-{rid}", {"charge_id": entry["charge_id"]}
    code, resp, _ = call_provider("/refunds", body, key, fail="refund")
    print(f"refund attempt (provider failing): ({code}, {resp.get('error')})")
    code, resp, _ = call_provider("/refunds", body, key)
    print(f"refund retry  (provider healthy):  ({code}, {resp.get('status')})")
    print("  (Exercise 9.6: make the refund a real outbox entry the worker performs.)")


BRANCHES = {"happy": happy, "decline": decline, "expiry": expiry,
            "rollback": rollback, "crash": crash, "timeout": timeout,
            "refund": refund}

if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["_reserve_and_die"]:
        _reserve_and_die()
    if args == ["list"]:
        print("branches:", ", ".join(BRANCHES))
        sys.exit(0)
    unknown = [a for a in args if a not in BRANCHES]
    if unknown:
        sys.exit(f"unknown branch {unknown}; try: {', '.join(BRANCHES)}")
    ensure_provider()
    for name in (args or BRANCHES):
        BRANCHES[name]()
