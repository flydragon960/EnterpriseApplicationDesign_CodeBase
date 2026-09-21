# Listing 8.2 -- app.py: the boundary, now with a doorman.
# Two decorators guard every route: authenticated() proves WHO, and
# requires_scope() proves WHAT they may do. Neither lives in the domain.
import functools
from flask import Flask, jsonify, request, g
import jwt
import auth

app = Flask(__name__)

# in-memory Encore, scope-checked (persistence is Chapters 6-7's story)
EVENTS = {"ev_101": {"id": "ev_101", "title": "Jazz Ensemble", "seatsLeft": 42},
          "ev_102": {"id": "ev_102", "title": "Improv Night", "seatsLeft": 0}}

def authenticated(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "missing_token"}), 401
        try:
            g.claims = auth.verify(header[7:])       # the honest verify()
        except jwt.InvalidTokenError as e:
            return jsonify({"error": "invalid_token",
                            "reason": type(e).__name__}), 401
        return fn(*a, **kw)
    return wrapper

def requires_scope(scope):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not auth.has_scope(g.claims, scope):
                # 403, not 401: WHO is known, WHAT is refused (Chapter 3's
                # fault-routing applied to authorization)
                return jsonify({"error": "insufficient_scope",
                                "need": scope}), 403
            return fn(*a, **kw)
        return wrapper
    return deco

@app.get("/events")
@authenticated
@requires_scope("events:read")
def list_events():
    return jsonify({"events": list(EVENTS.values()),
                    "as": g.claims["sub"],
                    "onBehalfOf": g.claims.get("act", {}).get("sub")})

@app.post("/events/<event_id>/reservations")
@authenticated
@requires_scope("reservations:write")
def reserve(event_id):
    ev = EVENTS.get(event_id)
    if ev is None:
        return jsonify({"error": "not_found"}), 404
    if ev["seatsLeft"] <= 0:
        return jsonify({"error": "sold_out"}), 409
    ev["seatsLeft"] -= 1
    # the receipt records WHO reserved and, if delegated, FOR WHOM
    actor = g.claims["sub"]
    principal = g.claims.get("act", {}).get("sub", actor)
    return jsonify({"id": "res_1", "eventId": event_id,
                    "reservedBy": actor, "onBehalfOf": principal}), 201

if __name__ == "__main__":
    app.run(port=3000)
