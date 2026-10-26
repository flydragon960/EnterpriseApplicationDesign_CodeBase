# Listing 7.2 -- service.py (v3): one use case, three concurrency disciplines.
# reserve_unsafe is Chapter 6's load-check-save, kept as the control.
# reserve_pessimistic holds the row lock across the whole span.
# reserve_optimistic writes conditionally and retries on conflict.
# In the two safe disciplines, the idempotency record commits in the SAME
# transaction as the booking, so a retry can never book twice.
import hashlib
import random
import time
import uuid
from domain import DomainError
from storage import ConflictError, DuplicateRequest

# One home for the error-code -> HTTP-status mapping (used by app and race).
HTTP_STATUS = {"not_found": 404, "sold_out": 409, "idempotency_key_reuse": 422,
               "idempotency_key_required": 422,
               "conflict_retries_exhausted": 503}

class Outcome:
    def __init__(self, ok, value, code=None, replayed=False, retries=0):
        self.ok, self.value, self.code = ok, value, code
        self.replayed, self.retries = replayed, retries

    def stored(self):                        # what the idempotency record keeps
        return {"ok": self.ok, "code": self.code, "value": self.value}

    @property
    def http_status(self):
        return 201 if self.ok else HTTP_STATUS[self.code]

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
        """Chapter 6's path: load a copy, check the copy, save the copy.
        The idempotency record is a separate transaction too -- one more
        way this path is unsafe."""
        rhash = self._fingerprint(event_id, body)

        def attempt():
            event = self.events.get(event_id)                    # (1) load
            if event is None:
                return self._record_alone(key, rhash,
                                          Outcome(False, None, code="not_found"))
            try:
                r = event.reserve(self._new_id())                # (2) check+mutate
                if demo_delay:
                    time.sleep(demo_delay)
                self.events.save_unsafe(event)                   # (3) save
                outcome = Outcome(True, self._reservation_dto(r))
            except DomainError as err:
                outcome = Outcome(False, None, code=err.code)
            return self._record_alone(key, rhash, outcome)       # (4) separately
        return self._idempotent(key, rhash, attempt)

    def reserve_pessimistic(self, event_id, key, body=b"", demo_delay=0.0):
        """One transaction owns the row from load to commit. Rivals wait.
        The booking and its idempotency record commit together."""
        rhash = self._fingerprint(event_id, body)

        def attempt():
            with self.events.unit_of_work() as uow:
                event = uow.get_event(event_id, lock=True)       # FOR UPDATE
                if event is None:
                    outcome = Outcome(False, None, code="not_found")
                else:
                    try:
                        r = event.reserve(self._new_id())
                        if demo_delay:
                            time.sleep(demo_delay)  # we HOLD the lock through this
                        uow.save(event)
                        outcome = Outcome(True, self._reservation_dto(r))
                    except DomainError as err:
                        outcome = Outcome(False, None, code=err.code)
                uow.record_outcome(key, rhash, outcome.stored())  # same transaction
                return outcome                                    # COMMIT on exit
        return self._idempotent(key, rhash, attempt)

    def reserve_optimistic(self, event_id, key, body=b"", demo_delay=0.0,
                           max_attempts=8):
        """Write only if the premise still holds; on conflict, reload and
        re-decide -- the whole load-check-save, not just the save."""
        rhash = self._fingerprint(event_id, body)

        def attempt():
            for n in range(max_attempts):
                event, version = self.events.get_versioned(event_id)
                if event is None:
                    return self._record_alone(
                        key, rhash, Outcome(False, None, code="not_found"))
                try:
                    r = event.reserve(self._new_id())
                except DomainError as err:
                    return self._record_alone(
                        key, rhash, Outcome(False, None, code=err.code, retries=n))
                if demo_delay:
                    time.sleep(demo_delay)       # widen the race window
                outcome = Outcome(True, self._reservation_dto(r), retries=n)
                try:
                    self.events.save_versioned(
                        event, version, idem=(key, rhash, outcome.stored()))
                    return outcome
                except ConflictError:
                    time.sleep(random.uniform(0, 0.05 * (2 ** n)))  # jittered backoff
            # Transient failure: NOT recorded, so a retry with the same key
            # gets a fresh chance instead of a replayed 503.
            return Outcome(False, None, code="conflict_retries_exhausted",
                           retries=max_attempts)
        return self._idempotent(key, rhash, attempt)

    # ---------- shared machinery ----------
    def _idempotent(self, key, rhash, attempt):
        seen = self.idempotency.get(key)              # fast path: seen before?
        if seen is None:
            try:
                return attempt()                      # attempt records its outcome
            except DuplicateRequest:                  # a twin committed first:
                seen = self.idempotency.get(key)      #   our work was rolled back
        stored_hash, o = seen
        if stored_hash != rhash:
            return Outcome(False, None, code="idempotency_key_reuse")
        return Outcome(o["ok"], o["value"], o["code"], replayed=True)

    def _record_alone(self, key, rhash, outcome):
        """Record an outcome in its own transaction (no aggregate write)."""
        self.idempotency.record(key, rhash, outcome.stored())
        return outcome

    def _fingerprint(self, event_id, body):
        """Bind the key to WHAT was requested: the operation, the event,
        and the body. The same key sent to another event is a reuse."""
        target = f"POST /events/{event_id}/reservations\n".encode()
        return hashlib.sha256(target + (body or b"")).hexdigest()

    def _new_id(self):
        return f"res_{uuid.uuid4().hex[:8]}"

    def _event_dto(self, e):
        return {"id": e.id, "title": e.title, "seatsLeft": e.seats_left}

    def _reservation_dto(self, r):
        return {"id": r.id, "eventId": r.event_id,
                "status": r.status, "createdAt": r.created_at}
