# Listing 7.2 -- service.py (v3): one use case, three concurrency disciplines.
# reserve_unsafe is Chapter 6's load-check-save, kept as the control.
# reserve_pessimistic holds the row lock across the whole span.
# reserve_optimistic writes conditionally and retries on conflict.
import hashlib
import random
import time
import uuid
from domain import DomainError
from storage import ConflictError

class Outcome:
    def __init__(self, ok, value, code=None, replayed=False, retries=0):
        self.ok, self.value, self.code = ok, value, code
        self.replayed, self.retries = replayed, retries

class EncoreService:
    def __init__(self, events, idempotency):
        self.events = events
        self.idempotency = idempotency

    def list_events(self, bookable=False):
        summaries = self.events.list_summaries()
        if bookable:
            summaries = [e for e in summaries if e["seatsLeft"] > 0]
        return summaries

    def get_event(self, event_id):
        e = self.events.get(event_id)
        return self._event_dto(e) if e else None

    # ---------- the three disciplines ----------
    def reserve_unsafe(self, event_id, key, body=b"", demo_delay=0.0):
        """Chapter 6's path: load a copy, check the copy, save the copy."""
        def attempt():
            event = self.events.get(event_id)                    # (1) load
            if event is None:
                return Outcome(False, None, code="not_found")
            try:
                r = event.reserve(self._new_id())                # (2) check+mutate
                if demo_delay:
                    time.sleep(demo_delay)
                self.events.save_unsafe(event)                   # (3) save
                return Outcome(True, self._reservation_dto(r))
            except DomainError as err:
                return Outcome(False, None, code=err.code)
        return self._idempotent(key, body, attempt)

    def reserve_pessimistic(self, event_id, key, body=b"", demo_delay=0.0):
        """One transaction owns the row from load to commit. Rivals wait."""
        def attempt():
            with self.events.unit_of_work() as uow:
                event = uow.get_event(event_id, lock=True)       # FOR UPDATE
                if event is None:
                    return Outcome(False, None, code="not_found")
                try:
                    r = event.reserve(self._new_id())
                    if demo_delay:
                        time.sleep(demo_delay)   # we HOLD the lock through this
                    uow.save(r and event)
                    return Outcome(True, self._reservation_dto(r))
                except DomainError as err:
                    return Outcome(False, None, code=err.code)
        return self._idempotent(key, body, attempt)

    def reserve_optimistic(self, event_id, key, body=b"", demo_delay=0.0,
                           max_attempts=8):
        """Write only if the premise still holds; on conflict, reload and
        re-decide -- the whole load-check-save, not just the save."""
        def attempt():
            for n in range(max_attempts):
                event, version = self.events.get_versioned(event_id)
                if event is None:
                    return Outcome(False, None, code="not_found")
                try:
                    r = event.reserve(self._new_id())
                except DomainError as err:
                    return Outcome(False, None, code=err.code, retries=n)
                if demo_delay:
                    time.sleep(demo_delay)       # widen the race window
                try:
                    self.events.save_versioned(event, version)
                    return Outcome(True, self._reservation_dto(r), retries=n)
                except ConflictError:
                    time.sleep(random.uniform(0, 0.05 * (2 ** n)))  # jittered backoff
            return Outcome(False, None, code="conflict_retries_exhausted",
                           retries=max_attempts)
        return self._idempotent(key, body, attempt)

    # ---------- shared machinery ----------
    def _idempotent(self, key, body, attempt):
        rhash = hashlib.sha256(body).hexdigest()
        seen = self.idempotency.get(key)
        if seen is not None:
            stored_hash, o = seen
            if stored_hash != rhash:
                return Outcome(False, None, code="idempotency_key_reuse")
            return Outcome(o["ok"], o["value"], o["code"], replayed=True)
        outcome = attempt()
        self.idempotency.put(key, rhash, {"ok": outcome.ok,
                                          "code": outcome.code,
                                          "value": outcome.value})
        return outcome

    def _new_id(self):
        return f"res_{uuid.uuid4().hex[:8]}"

    def _event_dto(self, e):
        return {"id": e.id, "title": e.title, "seatsLeft": e.seats_left}

    def _reservation_dto(self, r):
        return {"id": r.id, "eventId": r.event_id,
                "status": r.status, "createdAt": r.created_at}
