# Listing 7.3 -- race.py: five students, two seats, three disciplines.
# Run: python3 race.py unsafe | pessimistic | optimistic
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from storage import (make_session_factory, EventRepository, IdempotencyStore,
                     EventRow)
from service import EncoreService

URL = "postgresql+psycopg2://encore:encore@localhost/encore"
sf, engine = make_session_factory(URL)

def reset():
    with sf() as s:
        s.execute(text("DELETE FROM reservations"))
        s.execute(text("DELETE FROM idempotency"))
        s.execute(text("DELETE FROM events"))
        s.add(EventRow(id="ev_103", title="Film Society: Friday Screening",
                       capacity=2, version=0))
        s.commit()

def run(discipline):
    reset()
    service = EncoreService(EventRepository(sf), IdempotencyStore(sf))
    method = getattr(service, f"reserve_{discipline}")
    students = ["kim", "ana", "raj", "lee", "mia"]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(
            lambda s: (s, method("ev_103", key=f"{s}-1", demo_delay=0.4)),
            students))
    elapsed = time.perf_counter() - t0

    for student, out in results:
        detail = out.value["id"] if out.ok else out.code
        retries = f"  (retries={out.retries})" if out.retries else ""
        print(f"  {student}: {'201' if out.ok else '409'} {detail}{retries}")
    seats = service.get_event("ev_103")["seatsLeft"]
    print(f"  capacity 2 -> confirmed {sum(1 for _, o in results if o.ok)}, "
          f"seatsLeft {seats}, elapsed {elapsed:.1f}s")

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "unsafe")
