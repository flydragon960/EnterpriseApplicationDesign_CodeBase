"""
Contract-first, done properly.

The YAML file is the source of truth (Swagger UI renders it), AND this server
actually IMPLEMENTS the endpoints the contract promises -- so "Try it out" in
Swagger UI really works (no 404s).

This is the full Chapter-2 posture:
    1. the contract (encore-openapi-v1.1.yaml) is authored first and is the truth
    2. the code below implements endpoints that CONFORM to it   <-- the part
       the earlier docs-only demo was missing
    3. (a conformance suite would then check 2 against 1)

Run:
    pip install flask flask-swagger-ui pyyaml
    python swagger_contract_first.py
Open:
    http://localhost:3000/docs     <-- Swagger UI; click "Try it out" -- it works
"""
from flask import Flask, request, jsonify, send_file
from flask_swagger_ui import get_swaggerui_blueprint

CONTRACT = "encore-openapi-v1.1.yaml"

app = Flask(__name__)

# ---- in-memory state (Chapter 6 makes this durable) ----
EVENTS = {
    "ev_101": {"id": "ev_101", "title": "Jazz Night", "capacity": 2, "seatsTaken": 0},
    "ev_102": {"id": "ev_102", "title": "Improv Night", "capacity": 0, "seatsTaken": 0},
}
RESERVATIONS = {}          # reservation_id -> record
IDEMPOTENCY = {}           # key -> (status, body)
_next = [1]

def seats_left(ev):
    return ev["capacity"] - ev["seatsTaken"]

def event_view(ev):
    return {"id": ev["id"], "title": ev["title"], "seatsLeft": seats_left(ev)}

# ---- (1) serve the contract + Swagger UI ----
@app.get("/openapi.yaml")
def contract():
    return send_file(CONTRACT, mimetype="application/yaml")

app.register_blueprint(
    get_swaggerui_blueprint("/docs", "/openapi.yaml",
                            config={"app_name": "Encore (contract-first)"}),
    url_prefix="/docs",
)

# ---- (2) REAL endpoints that CONFORM to the contract ----

@app.get("/events")
def list_events():
    evs = list(EVENTS.values())
    if request.args.get("bookable") == "true":
        evs = [e for e in evs if seats_left(e) > 0]
    return jsonify({"events": [event_view(e) for e in evs]})

@app.get("/events/<event_id>")
def get_event(event_id):
    ev = EVENTS.get(event_id)
    if ev is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(event_view(ev))

@app.post("/events/<event_id>/reservations")
def create_reservation(event_id):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return jsonify({"error": "idempotency_key_required"}), 422
    if key in IDEMPOTENCY:                          # replay the stored outcome
        status, body = IDEMPOTENCY[key]
        return jsonify({**body, "replayed": True}), status

    ev = EVENTS.get(event_id)
    if ev is None:
        outcome = ({"error": "not_found"}, 404)
    elif seats_left(ev) <= 0:
        outcome = ({"error": "sold_out"}, 409)
    else:
        ev["seatsTaken"] += 1
        rid = f"res_{_next[0]}"; _next[0] += 1
        RESERVATIONS[rid] = {"id": rid, "event": event_id, "status": "confirmed"}
        outcome = (RESERVATIONS[rid], 201)

    body, status = outcome
    IDEMPOTENCY[key] = (status, body)
    return jsonify(body), status

@app.get("/reservations/<rid>")
def get_reservation(rid):
    r = RESERVATIONS.get(rid)
    if r is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(r)

@app.get("/")
def home():
    return jsonify({"swagger_ui": "/docs", "contract": "/openapi.yaml"})

if __name__ == "__main__":
    print("Swagger UI (Try it out works):  http://localhost:3000/docs")
    app.run(port=3000)
