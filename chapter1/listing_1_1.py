# Listing 1.1 (Python) -- The smallest possible service: one capability, one endpoint.
# Standard library only, to match the zero-dependency Node version.
# Run: python3 listing_1_1.py     Then: curl http://localhost:3000/events
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

events = [
    {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert", "seatsLeft": 42},
    {"id": "ev_102", "title": "Improv Night", "seatsLeft": 0},
]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/events":
            self._send(200, events)
        else:
            self._send(404, {"error": "not_found"})

    def _send(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep the demo output quiet
        pass

if __name__ == "__main__":
    print("listening on http://localhost:3000")
    HTTPServer(("", 3000), Handler).serve_forever()
