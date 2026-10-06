# Listing 5.3 -- service.py: Encore's use cases.
# The service layer is the application's API to itself: one method per
# thing the application can do, orchestrating domain objects. Every
# projection -- REST, GraphQL, gRPC, tools -- calls THESE methods.
# Idempotency lives here, not in the domain: "the same attempt answered
# once" is a promise about requests, not a rule about seats.
import hashlib
from domain import Event, DomainError, NotFound

class Outcome:
    """What a use case returns: a result or a coded failure, plus
    whether it was replayed. Interface layers translate this to their
    protocol; the service layer does not know what a status code is."""
    def __init__(self, ok, value, code=None, replayed=False):
        self.ok, self.value, self.code, self.replayed = ok, value, code, replayed

class EncoreService:
    def __init__(self):
        self.events = {
            "ev_101": Event("ev_101", "Jazz Ensemble: Fall Concert", 42),
            "ev_102": Event("ev_102", "Improv Night", 0),
            "ev_103": Event("ev_103", "Film Society: Friday Screening", 15),
        }
        self._idempotency = {}          # key -> (request_hash, Outcome)
        self._next = 1

    # ---- queries ----
    def list_events(self, bookable=False):
        evs = self.events.values()
        if bookable:
            evs = [e for e in evs if e.seats_left > 0]
        return [self._event_dto(e) for e in evs]

    def get_event(self, event_id):
        e = self.events.get(event_id)
        return self._event_dto(e) if e else None

    def get_reservation(self, res_id):
        for e in self.events.values():
            if res_id in e.reservations:
                return self._reservation_dto(e.reservations[res_id])
        return None

    # ---- commands ----
    def reserve(self, event_id, idempotency_key, request_body=b""):
        rhash = hashlib.sha256(request_body).hexdigest()
        seen = self._idempotency.get(idempotency_key)
        if seen is not None:
            stored_hash, outcome = seen
            if stored_hash != rhash:
                return Outcome(False, None, code="idempotency_key_reuse")
            return Outcome(outcome.ok, outcome.value, outcome.code, replayed=True)

        event = self.events.get(event_id)
        if event is None:
            outcome = Outcome(False, None, code="not_found")
        else:
            try:
                r = event.reserve(f"res_{self._next}")
                self._next += 1
                outcome = Outcome(True, self._reservation_dto(r))
            except DomainError as err:
                outcome = Outcome(False, None, code=err.code)

        self._idempotency[idempotency_key] = (rhash, outcome)
        return outcome

    def cancel(self, event_id, reservation_id):
        event = self.events.get(event_id)
        if event is None:
            return Outcome(False, None, code="not_found")
        try:
            r = event.cancel(reservation_id)
            return Outcome(True, self._reservation_dto(r))
        except DomainError as err:
            return Outcome(False, None, code=err.code)

    # ---- DTOs: the shapes the contracts promised ----
    def _event_dto(self, e):
        return {"id": e.id, "title": e.title, "seatsLeft": e.seats_left}

    def _reservation_dto(self, r):
        return {"id": r.id, "eventId": r.event_id,
                "status": r.status, "createdAt": r.created_at}
