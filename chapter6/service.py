# Listing 6.3 -- service.py (v2): the same use cases, now against interfaces.
# Diff against Chapter 5's version and notice what changed: the state's
# ADDRESS (constructor-injected repositories) -- and what did not: every
# rule, every promise. The domain layer is byte-identical to Chapter 5's.
import hashlib
import time
from domain import DomainError

class Outcome:
    def __init__(self, ok, value, code=None, replayed=False):
        self.ok, self.value, self.code, self.replayed = ok, value, code, replayed

class EncoreService:
    def __init__(self, events, idempotency, ids):
        self.events = events              # EventRepository
        self.idempotency = idempotency    # IdempotencyStore
        self.ids = ids                    # IdSequence

    # ---- queries ----
    def list_events(self, bookable=False):
        summaries = self.events.list_summaries()
        if bookable:
            summaries = [e for e in summaries if e["seatsLeft"] > 0]
        return summaries

    def get_event(self, event_id):
        e = self.events.get(event_id)
        return self._event_dto(e) if e else None

    def get_reservation(self, res_id):
        for e in self.events.list():
            if res_id in e.reservations:
                return self._reservation_dto(e.reservations[res_id])
        return None

    # ---- commands ----
    def reserve(self, event_id, idempotency_key, request_body=b"",
                demo_delay=0.0):
        rhash = hashlib.sha256(request_body).hexdigest()
        seen = self.idempotency.get(idempotency_key)
        if seen is not None:
            stored_hash, o = seen
            if stored_hash != rhash:
                return Outcome(False, None, code="idempotency_key_reuse")
            return Outcome(o["ok"], o["value"], o["code"], replayed=True)

        event = self.events.get(event_id)          # (1) load a copy
        if event is None:
            outcome = Outcome(False, None, code="not_found")
        else:
            try:
                r = event.reserve(self.ids.next("res"))   # (2) check + mutate
                if demo_delay:
                    time.sleep(demo_delay)   # widen the gap, for Chapter 7's demo
                self.events.save(event)                   # (3) write back
                outcome = Outcome(True, self._reservation_dto(r))
            except DomainError as err:
                outcome = Outcome(False, None, code=err.code)

        self.idempotency.put(idempotency_key, rhash,
                             {"ok": outcome.ok, "code": outcome.code,
                              "value": outcome.value})
        return outcome

    def cancel(self, event_id, reservation_id):
        event = self.events.get(event_id)
        if event is None:
            return Outcome(False, None, code="not_found")
        try:
            r = event.cancel(reservation_id)
            self.events.save(event)
            return Outcome(True, self._reservation_dto(r))
        except DomainError as err:
            return Outcome(False, None, code=err.code)

    # ---- DTOs ----
    def _event_dto(self, e):
        return {"id": e.id, "title": e.title, "seatsLeft": e.seats_left}

    def _reservation_dto(self, r):
        return {"id": r.id, "eventId": r.event_id,
                "status": r.status, "createdAt": r.created_at}
