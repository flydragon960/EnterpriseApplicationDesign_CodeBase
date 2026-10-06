# Listing 1.1 (Flask variant) -- the same boundary, framework edition.
# Students know Flask from SOEN 287. Note: the boundary is IDENTICAL to the
# stdlib version; only the machinery changed. That is the chapter's point.
# Run: python3 listing_1_1_flask.py
from flask import Flask, jsonify

app = Flask(__name__)

events = [
    {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert", "seatsLeft": 42},
    {"id": "ev_102", "title": "Improv Night", "seatsLeft": 0},
]

@app.get("/events")
def list_events():
    return jsonify(events)                       # 200

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "not_found"}), 404  # structured, never a bare string

if __name__ == "__main__":
    app.run(port=3000)
