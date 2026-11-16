# Listing 9.1 -- domain.py (v2): the reservation grows a lifecycle.
# Exercise 7.12 designed this: a seat is HELD while payment is attempted,
# then CONFIRMED on success -- and a hold that is never confirmed must
# EXPIRE, or sold-out counts lie forever. Still no imports beyond datetime.
import datetime

class DomainError(Exception):
    code = "domain_error"

class NotFound(DomainError):       code = "not_found"
class SoldOut(DomainError):        code = "sold_out"
class NotHeld(DomainError):        code = "not_held"

def _now():
    return datetime.datetime.now(datetime.timezone.utc)

class Reservation:
    def __init__(self, id, event_id, hold_seconds=900):
        self.id, self.event_id = id, event_id
        self.status = "held"               # held -> confirmed | released | expired
        self.created_at = _now().isoformat()
        self.hold_expires_at = _now() + datetime.timedelta(seconds=hold_seconds)

    def is_active_hold(self, now=None):
        now = now or _now()
        return self.status == "held" and now < self.hold_expires_at

class Event:
    def __init__(self, id, title, capacity):
        self.id, self.title, self.capacity = id, title, capacity
        self.reservations = {}

    def seats_left(self, now=None):
        """A seat is consumed by a CONFIRMED reservation or a live HOLD.
        Expired holds free their seat automatically -- the rule decides
        what a hold counts for (Exercise 6.3's read model must follow)."""
        now = now or _now()
        taken = sum(1 for r in self.reservations.values()
                    if r.status == "confirmed" or r.is_active_hold(now))
        return self.capacity - taken

    def hold(self, reservation_id, hold_seconds=900):
        if self.seats_left() <= 0:
            raise SoldOut()
        r = Reservation(reservation_id, self.id, hold_seconds)
        self.reservations[reservation_id] = r
        return r

    def confirm(self, reservation_id, now=None):
        r = self.reservations.get(reservation_id)
        if r is None:
            raise NotFound()
        if not r.is_active_hold(now):
            raise NotHeld()            # expired or already resolved
        r.status = "confirmed"
        return r

    def release(self, reservation_id):
        """Compensation: undo a hold. Idempotent."""
        r = self.reservations.get(reservation_id)
        if r is None:
            raise NotFound()
        if r.status == "held":
            r.status = "released"
        return r
