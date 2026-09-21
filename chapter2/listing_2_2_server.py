# Listing 2.2 -- Encore implementing the contract (Flask).
# The contract came first; this code's job is to conform to it.
from flask import Flask, jsonify, request

app = Flask(__name__)

EVENTS = [
    {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert", "seatsLeft": 42},
    {"id": "ev_102", "title": "Improv Night", "seatsLeft": 0},
    {"id": "ev_103", "title": "Film Society: Friday Screening", "seatsLeft": 15},
]

@app.get("/events")
def list_events():
    events = EVENTS
    if request.args.get("bookable") == "true":
        events = [e for e in events if e["seatsLeft"] > 0]
    return jsonify({"events": events})

@app.get("/events/<event_id>")
def get_event(event_id):
    ev = next((e for e in EVENTS if e["id"] == event_id), None)
    if ev is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(ev)

if __name__ == "__main__":
    app.run(port=3000)
