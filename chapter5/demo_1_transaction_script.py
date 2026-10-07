"""
demo_1_transaction_script.py  --  Encore, TRANSACTION SCRIPT pattern
====================================================================
One of four pattern demos. All four expose the SAME HTTP API and behave
identically; only the INTERNAL organization of the rule differs.

TRANSACTION SCRIPT: one procedure per use case; the business rule is written
INLINE inside each procedure. Notice the "seats left" rule appears in TWO
procedures (list_events AND reserve_seat) -- that duplication is the point,
and the weakness: change one, forget the other, and they drift.

Storage is a plain in-memory dict, on purpose: this file is about WHERE THE
RULE LIVES, not about databases. (Transaction Script is a choice about logic
organization, independent of SQL/ORM.)

Run:   pip install flask ;  python demo_1_transaction_script.py
Port:  3000   (same as the other three -- run ONE at a time)
"""
from flask import Flask, jsonify

app = Flask(__name__)

# ---- in-memory state ----
EVENTS = {
    "ev_101": {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert", "capacity": 3},
    "ev_102": {"id": "ev_102", "title": "Improv Night", "capacity": 1},
}
RESERVATIONS = {}          # res_id -> {"id","event_id","status"}
_counter = [0]


def _next_id():
    _counter[0] += 1
    return f"res_{_counter[0]}"


# ===== TRANSACTION SCRIPTS: one procedure per use case =====

def list_events():
    out = []
    for ev in EVENTS.values():
        # <-- THE RULE (copy #1): seats_left = capacity - confirmed
        confirmed = sum(1 for r in RESERVATIONS.values()
                        if r["event_id"] == ev["id"] and r["status"] == "confirmed")
        out.append({"id": ev["id"], "title": ev["title"],
                    "seatsLeft": ev["capacity"] - confirmed})
    return out


def reserve_seat(event_id):
    ev = EVENTS.get(event_id)
    if ev is None:
        return {"error": "not_found"}, 404
    # <-- THE RULE (copy #2): same formula written again, inline
    confirmed = sum(1 for r in RESERVATIONS.values()
                    if r["event_id"] == event_id and r["status"] == "confirmed")
    if ev["capacity"] - confirmed <= 0:          # the sold-out check, inline
        return {"error": "sold_out"}, 409
    rid = _next_id()
    RESERVATIONS[rid] = {"id": rid, "event_id": event_id, "status": "confirmed"}
    return {"id": rid, "event": event_id, "status": "confirmed"}, 201


def cancel_reservation(rid):
    r = RESERVATIONS.get(rid)
    if r is None:
        return {"error": "not_found"}, 404
    r["status"] = "cancelled"
    return {"id": rid, "status": "cancelled"}, 200


# ===== interface layer: HTTP -> script, result -> status code =====

@app.get("/events")
def http_list():
    return jsonify({"events": list_events(), "pattern": "transaction-script"})

@app.post("/events/<event_id>/reservations")
def http_reserve(event_id):
    body, status = reserve_seat(event_id)
    return jsonify(body), status

@app.delete("/reservations/<rid>")
def http_cancel(rid):
    body, status = cancel_reservation(rid)
    return jsonify(body), status


if __name__ == "__main__":
    print("Encore [Transaction Script] on http://localhost:3000")
    app.run(port=3000)
