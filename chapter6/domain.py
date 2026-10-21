# Listing 5.2 -- domain.py: Encore's rules, and nothing else.
# Note the imports: none. This module does not know HTTP, GraphQL, JSON,
# or Flask exist. It knows about events, seats, and reservations.
class DomainError(Exception):
    """Base for rule violations. Carries a stable machine-readable code."""
    code = "domain_error"

class NotFound(DomainError):        code = "not_found"
class SoldOut(DomainError):         code = "sold_out"

class Event:
    def __init__(self, id, title, capacity):
        self.id, self.title, self.capacity = id, title, capacity
        self.reservations = {}                      # id -> Reservation

    @property
    def seats_left(self):
        """THE rule, stated once: capacity minus confirmed reservations."""
        confirmed = sum(1 for r in self.reservations.values()
                        if r.status == "confirmed")
        return self.capacity - confirmed

    def reserve(self, reservation_id):
        """Enforces the invariant at the only door through which it could
        be violated: you cannot construct an over-booked Event."""
        if self.seats_left <= 0:
            raise SoldOut()
        r = Reservation(reservation_id, self.id)
        self.reservations[reservation_id] = r
        return r

    def cancel(self, reservation_id):
        """Idempotent by meaning: cancelling a cancelled reservation is
        the same end state (Chapter 3's DELETE promise, kept here)."""
        r = self.reservations.get(reservation_id)
        if r is None:
            raise NotFound()
        r.status = "cancelled"
        return r

class Reservation:
    def __init__(self, id, event_id):
        self.id, self.event_id = id, event_id
        self.status = "confirmed"
        self.created_at = "2026-09-12T19:00:00Z"
