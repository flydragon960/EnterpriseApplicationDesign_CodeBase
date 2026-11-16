# Listing 9.3 (classroom version) -- storage.py: reservations with a
# lifecycle, and an OUTBOX -- with no database server.
#
# The outbox is the chapter's key idea: an intention to call the outside
# world, written IN THE SAME TRANSACTION as the state change it follows
# from -- so "I decided to charge" and "I recorded the hold" commit
# together or not at all. A separate worker then performs the outbox entries.
#
# Here the "database" is ONE JSON FILE (encore_state.json). A transaction is:
#   1. read the whole file into memory,
#   2. change the in-memory copy,
#   3. COMMIT = write a temp file and atomically rename it over the old one,
#      ROLLBACK = throw the copy away.
# The rename is all-or-nothing, so the hold and its outbox entry still land
# together or not at all, and they survive a crash because they are on disk.
# You can open the file in an editor during class and watch it change.
#
# What this does NOT give you (and PostgreSQL did): row locks and many
# concurrent writers. One process-wide lock stands in for SELECT ... FOR UPDATE.
import datetime
import json
import os
import threading
from domain import Event, Reservation

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "encore_state.json")

_EMPTY = {"events": {}, "reservations": {}, "outbox": [], "next_outbox_id": 1}


class Store:
    """The whole 'database': one JSON file plus one lock."""
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self._lock = threading.RLock()
        if not os.path.exists(path):
            self._write(json.loads(json.dumps(_EMPTY)))

    def _read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, state):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)          # atomic: old file or new, never half

    def snapshot(self):
        """A read-only look at the committed state."""
        with self._lock:
            return self._read()

    def transaction(self):
        return _Transaction(self)


class _Transaction:
    """with store.transaction() as state: ...  -> commit on success,
    rollback (discard the copy) if the block raises."""
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        self.store._lock.acquire()
        self.state = self.store._read()
        return self.state

    def __exit__(self, exc_type, *a):
        try:
            if exc_type is None:
                self.store._write(self.state)        # COMMIT
            # else: ROLLBACK -- nothing was written
        finally:
            self.store._lock.release()
        return False


def make_store(path=DEFAULT_PATH):
    return Store(path)


def _to_domain(state, event_id):
    row = state["events"].get(event_id)
    if row is None:
        return None
    e = Event(event_id, row["title"], row["capacity"])
    for rid, r in state["reservations"].items():
        if r["event_id"] != event_id:
            continue
        dr = Reservation.__new__(Reservation)
        dr.id, dr.event_id, dr.status = rid, r["event_id"], r["status"]
        dr.created_at = r["created_at"]
        dr.hold_expires_at = datetime.datetime.fromisoformat(r["hold_expires_at"])
        e.reservations[rid] = dr
    return e


class Repository:
    def __init__(self, store):
        self.store = store

    def get(self, event_id):
        return _to_domain(self.store.snapshot(), event_id)

    def unit_of_work(self):
        return _UnitOfWork(self.store)


class _UnitOfWork:
    """One transaction spanning: lock the event, mutate the aggregate,
    AND enqueue the outbox entry -- all committed together."""
    def __init__(self, store):
        self.tx = store.transaction()

    def __enter__(self):
        self.state = self.tx.__enter__()
        return self

    def get_event(self, event_id, lock=False):
        # lock=True is kept for parity with the PostgreSQL version; the
        # transaction already holds the store's single lock.
        return _to_domain(self.state, event_id)

    def save_event(self, event):
        for r in event.reservations.values():
            self.state["reservations"][r.id] = {
                "event_id": r.event_id, "status": r.status,
                "created_at": r.created_at,
                "hold_expires_at": r.hold_expires_at.isoformat()}

    def enqueue(self, kind, reservation_id, amount=0, charge_id=None):
        self.state["outbox"].append({
            "id": self.state["next_outbox_id"], "kind": kind,   # "charge" | "refund"
            "reservation_id": reservation_id, "amount": amount,
            "charge_id": charge_id, "status": "pending", "attempts": 0})
        self.state["next_outbox_id"] += 1

    def __exit__(self, exc_type, *a):
        return self.tx.__exit__(exc_type, *a)
