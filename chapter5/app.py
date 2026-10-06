# Listing 5.4 -- app.py: two projections, one truth.
# Both interfaces are TRANSLATORS: protocol in, service call, protocol out.
# Neither contains a single business rule. Count the lines that would
# change if a rule changed: zero.
from ariadne import QueryType, MutationType, gql, make_executable_schema, graphql_sync
from flask import Flask, jsonify, request
from service import EncoreService

service = EncoreService()          # ONE instance; both projections share it
app = Flask(__name__)

# Chapter 3's error catalog, as a translation table owned by the interface:
STATUS = {"not_found": 404, "sold_out": 409,
          "idempotency_key_reuse": 422, "idempotency_key_required": 422}

# ---------------- REST projection ----------------
@app.get("/events")
def list_events():
    bookable = request.args.get("bookable") == "true"
    return jsonify({"events": service.list_events(bookable)})

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
    out = service.reserve(event_id, key, request.get_data() or b"")
    if not out.ok:
        resp = jsonify({"error": out.code})
    else:
        resp = jsonify(out.value)
    if out.replayed:
        resp.headers["Idempotency-Replayed"] = "true"
    return resp, (201 if out.ok else STATUS[out.code])

# ---------------- GraphQL projection ----------------
SDL = gql("""
  type Query {
    events(bookable: Boolean): [Event!]!
    event(id: ID!): Event
  }
  type Mutation {
    reserveSeat(eventId: ID!, idempotencyKey: String!): Reservation
    cancelReservation(eventId: ID!, reservationId: ID!): Reservation
  }
  type Event { id: ID!  title: String!  seatsLeft: Int! }
  type Reservation { id: ID!  eventId: ID!  status: String!  createdAt: String! }
""")
query, mutation = QueryType(), MutationType()

query.set_field("events", lambda *_ , bookable=False: service.list_events(bookable))
query.set_field("event", lambda *_, id: service.get_event(id))

@mutation.field("reserveSeat")
def gql_reserve(_, info, eventId, idempotencyKey):
    out = service.reserve(eventId, idempotencyKey)
    return out.value                     # errors -> null (kept simple here)

@mutation.field("cancelReservation")
def gql_cancel(_, info, eventId, reservationId):
    out = service.cancel(eventId, reservationId)
    return out.value

schema = make_executable_schema(SDL, query, mutation)

@app.post("/graphql")
def graphql_endpoint():
    ok, result = graphql_sync(schema, request.get_json())
    return jsonify(result), (200 if ok else 400)

if __name__ == "__main__":
    app.run(port=3000)
