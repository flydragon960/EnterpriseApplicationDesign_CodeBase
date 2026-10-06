# demo.py -- drive the reserve-hold-charge-confirm flow through every branch.
import sys, time, uuid
from sqlalchemy import text
from storage import make_session_factory, Repository, EventRow, ReservationRow, OutboxRow
from worker import run_once
from domain import _now
import datetime

URL = "postgresql+psycopg2://encore:encore@localhost/encore"
sf, _ = make_session_factory(URL)
repo = Repository(sf)

def reset(capacity=2):
    with sf() as s:
        for t in ("outbox9", "reservations9", "events9"):
            s.execute(text(f"DELETE FROM {t}"))
        s.add(EventRow(id="ev_103", title="Film Society", capacity=capacity))
        s.commit()

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
    from sqlalchemy import select
    with sf() as s:
        rr = s.get(ReservationRow, rid)
        ob = s.scalars(select(OutboxRow)
                       .where(OutboxRow.reservation_id == rid)).first()
        return rr.status, (ob.status if ob else None)

def branch(name, fail=None, hold_seconds=900, expire_before_worker=False):
    print(f"\n=== {name} ===")
    reset()
    print(f"  seats before: {seats()}")
    rid = reserve(hold_seconds=hold_seconds)
    print(f"  after hold:   seats {seats()}, reservation {status(rid)}")
    if expire_before_worker:
        # force the hold to expire before the worker confirms
        with sf() as s:
            rr = s.get(ReservationRow, rid)
            rr.hold_expires_at = _now() - datetime.timedelta(seconds=1)
            s.commit()
        print("  (hold expired before worker ran)")
    for msg in run_once(sf, fail=fail):
        print("  worker:", msg)
    print(f"  final:        seats {seats()}, reservation {status(rid)}")

if __name__ == "__main__":
    branch("HAPPY PATH: charge succeeds")
    branch("DECLINE: card refused -> hold released, seat freed", fail="decline")
    branch("EXPIRY: hold dies before charge confirms -> needs refund",
           expire_before_worker=True)
