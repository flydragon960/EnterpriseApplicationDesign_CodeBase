"""
Encore -- Chapter 3 demo: idempotency keys + a coded error model,
with an interactive Swagger UI.

Run:
    pip install flask flasgger
    python encore_ch3_swagger.py
Then open:
    http://localhost:3000/apidocs      <-- Swagger UI (try the endpoints here)

What to demonstrate in the browser:
  1. POST a reservation with Idempotency-Key "kim-1"  -> 201, a new reservation.
  2. POST again with the SAME key "kim-1"             -> 201 (replayed) SAME reservation.
     (Chapter 3: a repeated attempt has ONE outcome -- no double booking.)
  3. Keep reserving until seats run out               -> 409 with code "sold_out".
     (Chapter 3: errors are contract too -- a stable, machine-readable code.)
"""
from flask import Flask, request, jsonify
from flasgger import Swagger

app = Flask(__name__)

# Swagger UI config: served at /apidocs
app.config["SWAGGER"] = {"title": "Encore API (Chapter 3 demo)", "uiversion": 3}
swagger = Swagger(app)

# --- in-memory state (Chapter 6 would make this durable; fine for a demo) ---
EVENTS = {"ev_101": {"id": "ev_101", "title": "Jazz Night", "capacity": 2, "seatsTaken": 0}}
RESERVATIONS = {}          # reservation_id -> record
IDEMPOTENCY = {}           # key -> stored outcome (status_code, body)
_next_id = [1]


@app.get("/events/<event_id>")
def get_event(event_id):
    """Fetch one event.
    ---
    tags: [events]
    parameters:
      - name: event_id
        in: path
        required: true
        schema: {type: string}
        example: ev_101
    responses:
      200:
        description: The event, with seats remaining.
      404:
        description: No event has this id (error code not_found).
    """
    ev = EVENTS.get(event_id)
    if ev is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"id": ev["id"], "title": ev["title"],
                    "seatsLeft": ev["capacity"] - ev["seatsTaken"]})


@app.post("/events/<event_id>/reservations")
def create_reservation(event_id):
    """Reserve one seat.  NOT naturally idempotent -- the Idempotency-Key makes it safe.
    ---
    tags: [reservations]
    description: >
      A repeated request carrying the same Idempotency-Key is recognized as a
      repeat and answered with the STORED OUTCOME of the first attempt, applied
      exactly once.  A timed-out caller MUST retry with the same key; a fresh
      key creates a second reservation.
    parameters:
      - name: event_id
        in: path
        required: true
        schema: {type: string}
        example: ev_101
      - name: Idempotency-Key
        in: header
        required: true
        schema: {type: string}
        example: kim-1
    responses:
      201:
        description: The seat is reserved (or, on retry with the same key, the replayed original).
      409:
        description: No seats remain (error code sold_out). Not retryable.
      422:
        description: Missing or reused idempotency key.
    """
    key = request.headers.get("Idempotency-Key")
    if not key:
        return jsonify({"error": "idempotency_key_required"}), 422

    # --- idempotency: recognize a repeat, replay the stored outcome ---
    if key in IDEMPOTENCY:
        status, body = IDEMPOTENCY[key]
        body = {**body, "replayed": True}
        return jsonify(body), status

    ev = EVENTS.get(event_id)
    if ev is None:
        outcome = ({"error": "not_found"}, 404)
    elif ev["capacity"] - ev["seatsTaken"] <= 0:
        outcome = ({"error": "sold_out"}, 409)          # <-- Chapter 3: coded error
    else:
        ev["seatsTaken"] += 1
        rid = f"res_{_next_id[0]}"; _next_id[0] += 1
        RESERVATIONS[rid] = {"id": rid, "event": event_id, "status": "confirmed"}
        outcome = (RESERVATIONS[rid], 201)

    body, status = outcome
    IDEMPOTENCY[key] = (status, body)                    # <-- store outcome under the key
    return jsonify(body), status


if __name__ == "__main__":
    print("Swagger UI:  http://localhost:3000/apidocs")
    app.run(port=3000)
