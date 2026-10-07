"""
demo_2_domain_model.py  --  Encore, DOMAIN MODEL pattern
====================================================================
DOMAIN MODEL: one object per business thing (one Event object per event).
The rule lives INSIDE the object as a method/property. seats_left is a single
computed property -- stated ONCE -- so the two-formulas drift bug of the
transaction script simply cannot exist.

Storage is in-memory on purpose (same as the other demos): this is about
WHERE THE RULE LIVES, not databases.

Run:   pip install flask ;  python demo_2_domain_model.py
Port:  3000   (run ONE demo at a time)
"""
from flask import Flask, jsonify

app = Flask(__name__)


# ===== DOMAIN: the rule lives in the object =====

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
        self.reservations = {}                # id -> Reservation

    @property
    def seats_left(self):
        # THE rule, stated ONCE -- no duplicate formula to drift
        confirmed = sum(1 for r in self.reservations.values()
                        if r.status == "confirmed")
        return self.capacity - confirmed

    def reserve(self, res_id):
        if self.seats_left <= 0:              # <- rule lives IN the object
            raise SoldOut()
        self.reservations[res_id] = Reservation(res_id)
        return self.reservations[res_id]

    def cancel(self, res_id):
        r = self.reservations.get(res_id)
        if r is None:
            raise NotFound()
        r.status = "cancelled"                # frees a seat by construction
        return r


# ---- in-memory "repository" of domain objects ----
EVENTS = {
    "ev_101": Event("ev_101", "Jazz Ensemble: Fall Concert", 3),
    "ev_102": Event("ev_102", "Improv Night", 1),
}
_counter = [0]
def _next_id():
    _counter[0] += 1
    return f"res_{_counter[0]}"

def _find_event_of(res_id):
    for ev in EVENTS.values():
        if res_id in ev.reservations:
            return ev
    return None


# ===== interface layer =====
STATUS = {"sold_out": 409, "not_found": 404}

@app.get("/events")
def http_list():
    events = [{"id": e.id, "title": e.title, "seatsLeft": e.seats_left}  # one formula
              for e in EVENTS.values()]
    return jsonify({"events": events, "pattern": "domain-model"})

@app.post("/events/<event_id>/reservations")
def http_reserve(event_id):
    ev = EVENTS.get(event_id)
    if ev is None:
        return jsonify({"error": "not_found"}), 404
    try:
        r = ev.reserve(_next_id())
    except SoldOut as e:
        return jsonify({"error": e.code}), STATUS[e.code]
    return jsonify({"id": r.id, "event": event_id, "status": r.status}), 201

@app.delete("/reservations/<rid>")
def http_cancel(rid):
    ev = _find_event_of(rid)
    if ev is None:
        return jsonify({"error": "not_found"}), 404
    ev.cancel(rid)
    return jsonify({"id": rid, "status": "cancelled"}), 200


if __name__ == "__main__":
    print("Encore [Domain Model] on http://localhost:3000")
    app.run(port=3000)
