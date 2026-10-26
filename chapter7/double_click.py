# double_click.py -- one student, eight identical clicks, one booking.
# Eight threads send the SAME request with the SAME Idempotency-Key at once.
# Exactly one books a seat; the other seven replay its result, because the
# booking and its idempotency record commit in one transaction.
# Run: python3 double_click.py pessimistic | optimistic
import sys
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from storage import (make_session_factory, EventRepository, IdempotencyStore,
                     EventRow)
from service import EncoreService

URL = "postgresql+psycopg2://encore:encore@localhost/encore"
sf, _ = make_session_factory(URL)

def reset():
    with sf() as s:
        s.execute(text("DELETE FROM reservations"))
        s.execute(text("DELETE FROM idempotency"))
        s.execute(text("DELETE FROM events"))
        s.add(EventRow(id="ev_104", title="Poetry Slam", capacity=10,
                       version=0))
        s.commit()

def run(discipline):
    reset()
    service = EncoreService(EventRepository(sf), IdempotencyStore(sf))
    method = getattr(service, f"reserve_{discipline}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        outs = list(pool.map(
            lambda _: method("ev_104", key="kim-click", demo_delay=0.2),
            range(8)))
    for i, out in enumerate(outs, 1):
        tag = "replayed" if out.replayed else "booked"
        print(f"  click {i}: {out.http_status} {out.value['id']}  ({tag})")
    distinct = {o.value["id"] for o in outs if o.ok}
    seats = service.get_event("ev_104")["seatsLeft"]
    print(f"  8 clicks -> {len(distinct)} reservation(s), "
          f"seatsLeft {seats} of 10")

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "pessimistic")
