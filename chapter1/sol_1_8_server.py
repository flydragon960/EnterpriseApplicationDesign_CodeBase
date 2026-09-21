# Solution 1.8 server (Python) -- adds GET /events/<id>
import json, re
from http.server import BaseHTTPRequestHandler, HTTPServer

events = [
    {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert", "seatsLeft": 42},
    {"id": "ev_102", "title": "Improv Night", "seatsLeft": 0},
    {"id": "ev_103", "title": "Film Society: Friday Screening", "seatsLeft": 15},
]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        one = re.fullmatch(r"/events/(\w+)", self.path)
        if self.path == "/events":
            self._send(200, events)
        elif one:
            ev = next((e for e in events if e["id"] == one.group(1)), None)
            self._send(200, ev) if ev else self._send(404, {"error": "not_found"})
        else:
            self._send(404, {"error": "not_found"})

    def _send(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args): pass

if __name__ == "__main__":
    HTTPServer(("", 3000), Handler).serve_forever()
