# Listing 10.1 -- test_pyramid.py: three grains of test, three speeds,
# three things pinned. Run: python3 -m pytest test_pyramid.py -v
#
# The book has argued since Chapter 5 that tests belong at STABLE
# INTERFACES, never at private structure. Here are the three interfaces
# Encore exposes, each with its own tests:
#   domain   -- Event/Reservation rules      (microseconds, no I/O)
#   service  -- use cases via in-memory repos (fast, no network)
#   contract -- the HTTP boundary promise     (the refactoring safety net)
import pytest
from domain import Event, SoldOut, NotFound

# ---------- DOMAIN TESTS: the rules, in isolation ----------
# No database, no HTTP, no service layer. Just the invariant.
class TestDomain:
    def test_reserve_decrements_seats(self):
        e = Event("ev_1", "Show", capacity=2)
        e.reserve("res_1")
        assert e.seats_left == 1

    def test_cannot_overbook(self):
        e = Event("ev_1", "Show", capacity=1)
        e.reserve("res_1")
        with pytest.raises(SoldOut):        # the invariant, enforced at the door
            e.reserve("res_2")

    def test_cancel_frees_a_seat(self):
        e = Event("ev_1", "Show", capacity=1)
        e.reserve("res_1")
        e.cancel("res_1")
        assert e.seats_left == 1

    def test_cancel_is_idempotent(self):
        e = Event("ev_1", "Show", capacity=1)
        e.reserve("res_1")
        e.cancel("res_1"); e.cancel("res_1")   # twice == once
        assert e.seats_left == 1


# ---------- SERVICE TESTS: use cases over an IN-MEMORY double ----------
# The repositories are fakes (Chapter 6's promise: the in-memory version
# lives on as the test double). No Postgres, no Flask -- but the REAL
# service logic, including idempotency.
class FakeEventRepo:
    def __init__(self, events): self._e = {e.id: e for e in events}
    def get(self, event_id): return self._e.get(event_id)
    def list_summaries(self):
        return [{"id": e.id, "title": e.title, "seatsLeft": e.seats_left}
                for e in self._e.values()]
    def save_unsafe(self, event): pass          # already the live object
    def unit_of_work(self): return _FakeUoW(self)
    def get_versioned(self, event_id): return self.get(event_id), 0
    def save_versioned(self, event, v): pass

class _FakeUoW:
    def __init__(self, repo): self.repo = repo
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_event(self, event_id, lock=False): return self.repo.get(event_id)
    def save(self, event): pass

class FakeIdempotency:
    def __init__(self): self._d = {}
    def get(self, key): return self._d.get(key)
    def put(self, key, rhash, outcome): self._d[key] = (rhash, outcome)

@pytest.fixture
def service():
    from service import EncoreService
    repo = FakeEventRepo([Event("ev_1", "Show", capacity=2)])
    return EncoreService(repo, FakeIdempotency())

class TestService:
    def test_reserve_returns_reservation(self, service):
        out = service.reserve_unsafe("ev_1", key="k1")
        assert out.ok and out.value["status"] == "confirmed"

    def test_same_key_replays_not_rebooks(self, service):
        first = service.reserve_unsafe("ev_1", key="k1")
        replay = service.reserve_unsafe("ev_1", key="k1")
        assert replay.replayed
        assert replay.value["id"] == first.value["id"]   # same reservation
        assert service.get_event("ev_1")["seatsLeft"] == 1  # moved once

    def test_sold_out_is_a_coded_failure(self, service):
        service.reserve_unsafe("ev_1", key="k1")
        service.reserve_unsafe("ev_1", key="k2")
        out = service.reserve_unsafe("ev_1", key="k3")
        assert not out.ok and out.code == "sold_out"

    def test_unknown_event(self, service):
        out = service.reserve_unsafe("ev_404", key="k1")
        assert not out.ok and out.code == "not_found"
