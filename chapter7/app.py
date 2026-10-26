# Listing 7.4 -- app.py (v3): the safe path becomes THE path.
# Run: python3 app.py     (Postgres behind, pessimistic reserve default)
from flask import Flask, jsonify, request
from sqlalchemy import text
from storage import (make_session_factory, EventRepository, IdempotencyStore,
                     EventRow)
from service import EncoreService, HTTP_STATUS

URL = "postgresql+psycopg2://encore:encore@localhost/encore"
sf, _ = make_session_factory(URL)
service = EncoreService(EventRepository(sf), IdempotencyStore(sf))

with sf() as s:
    if s.get(EventRow, "ev_101") is None:
        s.add_all([EventRow(id="ev_101", title="Jazz Ensemble: Fall Concert",
                            capacity=42, version=0),
                   EventRow(id="ev_102", title="Improv Night", capacity=0,
                            version=0)])
        s.commit()

app = Flask(__name__)

@app.get("/events")
def list_events():
    return jsonify({"events":
        service.list_events(request.args.get("bookable") == "true")})

@app.get("/events/<event_id>")
def get_event(event_id):
    dto = service.get_event(event_id)
    return (jsonify(dto), 200) if dto else (jsonify({"error": "not_found"}), 404)

@app.post("/events/<event_id>/reservations")
def reserve(event_id):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return (jsonify({"error": "idempotency_key_required"}),
                HTTP_STATUS["idempotency_key_required"])
    out = service.reserve_pessimistic(event_id, key, request.get_data() or b"")
    resp = jsonify(out.value if out.ok else {"error": out.code})
    if out.replayed:
        resp.headers["Idempotency-Replayed"] = "true"
    return resp, out.http_status

if __name__ == "__main__":
    app.run(port=3000, threaded=True)
