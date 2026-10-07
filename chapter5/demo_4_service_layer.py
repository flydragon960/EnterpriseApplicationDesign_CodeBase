"""
demo_4_service_layer.py  --  Encore, SERVICE LAYER pattern
====================================================================
SERVICE LAYER: sits ON TOP of a Domain Model. It does NOT re-implement the
rule -- it ORCHESTRATES: idempotency, ordering, side effects (notify) -- and
DELEGATES the actual rule to the domain object (event.reserve()).

So this demo has BOTH a domain model (Event, with the rule inside) AND a
service layer around it. The rule still lives in exactly one place (the Event);
the service only sequences and surrounds it. The service returns a protocol-
free Outcome; the interface layer turns a code into an HTTP status.

New vs demo 2: the service adds an idempotency key (a header), so a repeated
POST with the same key returns the SAME reservation -- an APPLICATION concern,
which is exactly what the service layer owns.

Storage is in-memory (same as the others).

Run:   pip install flask ;  python demo_4_service_layer.py
Port:  3000   (run ONE demo at a time)
Try the idempotency bit:
    curl -s -X POST localhost:3000/events/ev_101/reservations -H "Idempotency-Key: k1"
    curl -s -X POST localhost:3000/events/ev_101/reservations -H "Idempotency-Key: k1"
    # -> same reservation id both times, second one shows "replayed": true
"""
from flask import Flask, jsonify, request

app = Flask(__name__)


# ===== DOMAIN (rule lives here, exactly once) =====

class SoldOut(Exception):
    code = "sold_out"
class NotFound(Exception):
    code = "not_found"

class Reservation:
    def __init__(self, id, status="confirmed"):
        self.id, self.status = id, status

class Event:
    def __init__(self, id, title, capacity):
        self.id, self.title, self.capacity = id, title, capacity
        self.reservations = {}
    @property
    def seats_left(self):
        return self.capacity - sum(1 for r in self.reservations.values()
                                   if r.status == "confirmed")
    def reserve(self, res_id):
        if self.seats_left <= 0:              # <- the rule, in the domain
            raise SoldOut()
        self.reservations[res_id] = Reservation(res_id)
        return self.reservations[res_id]
    def cancel(self, res_id):
        r = self.reservations.get(res_id)
        if r is None:
            raise NotFound()
        r.status = "cancelled"
        return r


# ===== SERVICE LAYER: orchestrates; owns application concerns =====

class Outcome:
    def __init__(self, ok, value=None, code=None, replayed=False):
        self.ok, self.value, self.code, self.replayed = ok, value, code, replayed

class EncoreService:
    def __init__(self):
        self.events = {
            "ev_101": Event("ev_101", "Jazz Ensemble: Fall Concert", 3),
            "ev_102": Event("ev_102", "Improv Night", 1),
        }
        self._seen = {}        # idempotency-key -> Outcome   (application concern)
        self._n = 0

    def _next_id(self):
        self._n += 1
        return f"res_{self._n}"

    def list_events(self):
        return [{"id": e.id, "title": e.title, "seatsLeft": e.seats_left}
                for e in self.events.values()]

    def reserve(self, event_id, idem_key=None):
        # application concern #1: idempotency (NOT a domain rule)
        if idem_key and idem_key in self._seen:
            prev = self._seen[idem_key]
            return Outcome(prev.ok, prev.value, prev.code, replayed=True)
        event = self.events.get(event_id)                  # load domain object
        if event is None:
            out = Outcome(False, code="not_found")
        else:
            try:
                r = event.reserve(self._next_id())         # DELEGATE the rule
                out = Outcome(True, {"id": r.id, "event": event_id,
                                     "status": r.status})
                # application concern #2: a side effect (notify), surrounds the rule
                self._notify(event, r)
            except SoldOut as e:
                out = Outcome(False, code=e.code)
        if idem_key:
            self._seen[idem_key] = out
        return out

    def cancel(self, res_id):
        for event in self.events.values():
            if res_id in event.reservations:
                event.cancel(res_id)
                return Outcome(True, {"id": res_id, "status": "cancelled"})
        return Outcome(False, code="not_found")

    def _notify(self, event, reservation):
        print(f"[notify] reserved {reservation.id} on {event.id}")   # side effect


svc = EncoreService()


# ===== interface layer =====
STATUS = {"sold_out": 409, "not_found": 404}

@app.get("/events")
def http_list():
    return jsonify({"events": svc.list_events(), "pattern": "service-layer"})

@app.post("/events/<event_id>/reservations")
def http_reserve(event_id):
    out = svc.reserve(event_id, request.headers.get("Idempotency-Key"))
    if out.ok:
        body = dict(out.value)
        if out.replayed:
            body["replayed"] = True
        return jsonify(body), 201
    return jsonify({"error": out.code}), STATUS.get(out.code, 400)

@app.delete("/reservations/<rid>")
def http_cancel(rid):
    out = svc.cancel(rid)
    if out.ok:
        return jsonify(out.value), 200
    return jsonify({"error": out.code}), STATUS.get(out.code, 400)


if __name__ == "__main__":
    print("Encore [Service Layer] on http://localhost:3000")
    app.run(port=3000)
