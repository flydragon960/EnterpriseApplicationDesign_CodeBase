# Listing 12.4 -- statelessness.py: why Encore scales horizontally.
# The book has kept every instance STATELESS on purpose: no reservation,
# no idempotency record, no session lives in a process's memory -- it all
# lives in Postgres (Chapters 6-7), reachable by every instance equally.
# The payoff is cashed here: because instances hold nothing, ANY instance
# can serve ANY request, so you scale by ADDING INSTANCES, and a load
# balancer may route each request anywhere. This is the property Chapters
# 1 (headless), 6 (shared truth), and 11 (interchangeable instances) were
# quietly banking.
from sqlalchemy import text
from storage import make_session_factory, EventRepository, IdempotencyStore, EventRow
from service import EncoreService

URL = "postgresql+psycopg2://encore:encore@localhost/encore"

def make_instance(name):
    """Each 'instance' is a fresh service object with its OWN connections but
    the SAME database -- exactly like separate processes behind a load
    balancer. They share no memory."""
    sf, _ = make_session_factory(URL)
    return name, EncoreService(EventRepository(sf), IdempotencyStore(sf))

if __name__ == "__main__":
    # reset
    sf, _ = make_session_factory(URL)
    with sf() as s:
        for t in ("reservations", "idempotency", "events"):
            s.execute(text(f"DELETE FROM {t}"))
        s.add(EventRow(id="ev_1", title="Big Show", capacity=3, version=0))
        s.commit()

    # three interchangeable instances
    inst = dict([make_instance("web-1"), make_instance("web-2"),
                 make_instance("web-3")])

    # A load balancer sprays one logical user's requests across all three.
    # Because state is shared, the story stays coherent no matter who serves.
    print("one user, requests routed to whichever instance is free:\n")
    r1 = inst["web-1"].reserve_pessimistic("ev_1", key="kim-1")
    print(f"  web-1 reserve      -> {r1.value['id']} (seatsLeft now visible everywhere)")
    seen_by_2 = inst["web-2"].get_event("ev_1")["seatsLeft"]
    print(f"  web-2 sees seatsLeft-> {seen_by_2}  (it never handled the reserve)")

    # The retry of kim-1 lands on a THIRD instance -- idempotency still holds,
    # because the record is in the shared store, not web-1's memory.
    r_retry = inst["web-3"].reserve_pessimistic("ev_1", key="kim-1")
    print(f"  web-3 retry kim-1  -> {r_retry.value['id']} "
          f"(replayed={r_retry.replayed}) -- same reservation, different instance")

    # Scale out: a fourth instance added at peak needs NO state transfer.
    _, web4 = make_instance("web-4")
    print(f"\n  web-4 (just added) -> serves immediately, seatsLeft = "
          f"{web4.get_event('ev_1')['seatsLeft']}")
    print("  no warm-up, no state copy: it reads the same shared truth")

    print("\nStateless instances are the unit of horizontal scale --")
    print("add capacity by adding instances; the load balancer needs no")
    print("stickiness because no instance is special.")
