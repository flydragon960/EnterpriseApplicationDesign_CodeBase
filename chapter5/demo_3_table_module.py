"""
demo_3_table_module.py  --  Encore, TABLE MODULE pattern
====================================================================
TABLE MODULE: ONE object represents the whole TABLE (not one object per row).
A single EventsTable instance handles all events; you pass the event_id in on
every call. The rule lives in a method of the table object, keyed by id.

Contrast with Domain Model: there it was `event.reserve()` (one object per
event, which knows who it is); here it is `table.reserve(event_id)` -- the
table object has no identity of its own, so the id must be passed every time.

Storage is in-memory (same as the other demos) -- the point is the shape of
the object (one-per-table), not databases.

Run:   pip install flask ;  python demo_3_table_module.py
Port:  3000   (run ONE demo at a time)
"""
from flask import Flask, jsonify

app = Flask(__name__)


class SoldOut(Exception):
    code = "sold_out"
class NotFound(Exception):
    code = "not_found"


# ===== TABLE MODULE: one object for the WHOLE events table =====

class EventsTable:
    """ONE instance for the entire 'events' table. Every method takes the id."""
    def __init__(self):
        # the "table": rows keyed by id (in memory, but think 'a table')
        self.rows = {
            "ev_101": {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert",
                       "capacity": 3, "taken": 0},
            "ev_102": {"id": "ev_102", "title": "Improv Night",
                       "capacity": 1, "taken": 0},
        }

    def seats_left(self, event_id):
        row = self.rows[event_id]
        return row["capacity"] - row["taken"]

    def list_all(self):
        return [{"id": r["id"], "title": r["title"],
                 "seatsLeft": r["capacity"] - r["taken"]} for r in self.rows.values()]

    def reserve(self, event_id):
        if event_id not in self.rows:
            raise NotFound()
        if self.seats_left(event_id) <= 0:    # <- rule, keyed by id, over the table
            raise SoldOut()
        self.rows[event_id]["taken"] += 1

    def free_one(self, event_id):             # cancel frees a seat on the table
        if self.rows[event_id]["taken"] > 0:
            self.rows[event_id]["taken"] -= 1


class ReservationsTable:
    """A second table module, for reservations."""
    def __init__(self):
        self.rows = {}                        # res_id -> row
        self._n = 0
    def insert(self, event_id):
        self._n += 1
        rid = f"res_{self._n}"
        self.rows[rid] = {"id": rid, "event_id": event_id, "status": "confirmed"}
        return rid
    def cancel(self, rid):
        if rid not in self.rows:
            raise NotFound()
        self.rows[rid]["status"] = "cancelled"
        return self.rows[rid]["event_id"]


events_table = EventsTable()
reservations_table = ReservationsTable()


# ===== interface layer =====
STATUS = {"sold_out": 409, "not_found": 404}

@app.get("/events")
def http_list():
    return jsonify({"events": events_table.list_all(), "pattern": "table-module"})

@app.post("/events/<event_id>/reservations")
def http_reserve(event_id):
    try:
        events_table.reserve(event_id)        # table.reserve(id), not event.reserve()
    except NotFound as e:
        return jsonify({"error": e.code}), 404
    except SoldOut as e:
        return jsonify({"error": e.code}), 409
    rid = reservations_table.insert(event_id)
    return jsonify({"id": rid, "event": event_id, "status": "confirmed"}), 201

@app.delete("/reservations/<rid>")
def http_cancel(rid):
    try:
        event_id = reservations_table.cancel(rid)
    except NotFound as e:
        return jsonify({"error": e.code}), 404
    events_table.free_one(event_id)
    return jsonify({"id": rid, "status": "cancelled"}), 200


if __name__ == "__main__":
    print("Encore [Table Module] on http://localhost:3000")
    app.run(port=3000)
