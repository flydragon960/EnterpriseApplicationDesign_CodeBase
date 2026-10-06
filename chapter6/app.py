# Listing 6.4 -- app.py (v2): the wiring point.
# The ONLY file that knows both worlds: which storage backs the interfaces.
# Run:  python3 app.py 3000 encore.db     (and, later, a second instance:
#        python3 app.py 3001 encore.db -- same file, shared truth)
import sys
from flask import Flask, jsonify, request
from sqlite_repository import (make_session_factory, SqliteEventRepository,
                               SqliteIdempotencyStore, SqliteIdSequence,
                               EventRow)
from service import EncoreService

port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
db_path = sys.argv[2] if len(sys.argv) > 2 else "encore.db"

session_factory, engine = make_session_factory(db_path)
events_repo = SqliteEventRepository(session_factory)
service = EncoreService(events_repo,
                        SqliteIdempotencyStore(session_factory),
                        SqliteIdSequence(session_factory))

# seed only if the database is empty -- restarts must not re-create state
with session_factory() as s:
    if s.get(EventRow, "ev_101") is None:
        s.add_all([EventRow(id="ev_101", title="Jazz Ensemble: Fall Concert",
                            capacity=42),
                   EventRow(id="ev_102", title="Improv Night", capacity=0),
                   EventRow(id="ev_103",
                            title="Film Society: Friday Screening",
                            capacity=2)])
        s.commit()

app = Flask(__name__)
STATUS = {"not_found": 404, "sold_out": 409,
          "idempotency_key_reuse": 422, "idempotency_key_required": 422}

@app.get("/events")
def list_events():
    return jsonify({"events":
        service.list_events(request.args.get("bookable") == "true")})

@app.get("/events/<event_id>")
def get_event(event_id):
    dto = service.get_event(event_id)
    return (jsonify(dto), 200) if dto else (jsonify({"error": "not_found"}), 404)

@app.get("/reservations/<res_id>")
def get_reservation(res_id):
    dto = service.get_reservation(res_id)
    return (jsonify(dto), 200) if dto else (jsonify({"error": "not_found"}), 404)

@app.post("/events/<event_id>/reservations")
def reserve(event_id):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return jsonify({"error": "idempotency_key_required"}), 422
    delay = float(request.headers.get("X-Demo-Slow-Reserve", 0))
    out = service.reserve(event_id, key, request.get_data() or b"",
                          demo_delay=delay)
    resp = jsonify(out.value if out.ok else {"error": out.code})
    if out.replayed:
        resp.headers["Idempotency-Replayed"] = "true"
    return resp, (201 if out.ok else STATUS[out.code])

if __name__ == "__main__":
    app.run(port=port, threaded=True)
