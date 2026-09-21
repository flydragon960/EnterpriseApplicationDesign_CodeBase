# Listing 5.1 -- The bug Chapter 4's Exercise 10 predicted, manufactured.
# One service, two projections (REST and GraphQL), and the reservation
# logic written TWICE -- once in each handler. Then a new rule arrives:
# "cancelling a reservation frees its seat." The maintainer implements it
# where they are looking. Watch the two projections come apart.
# Run: python3 listing_5_1_divergence.py   (REST :3000 paths + POST /graphql)
from ariadne import QueryType, MutationType, gql, make_executable_schema, graphql_sync
from flask import Flask, jsonify, request

# ---- shared state (that part, at least, is shared) ----
EVENTS = {"ev_103": {"id": "ev_103", "title": "Film Society: Friday Screening",
                     "capacity": 15, "seatsTaken": 0}}
RESERVATIONS = {}      # id -> {"id", "eventId", "status"}
NEXT = {"n": 1}

app = Flask(__name__)

# ---- REST projection: computes seats from the COUNTER ----
@app.get("/events/<event_id>")
def rest_get_event(event_id):
    ev = EVENTS[event_id]
    return jsonify({"id": ev["id"], "title": ev["title"],
                    "seatsLeft": ev["capacity"] - ev["seatsTaken"]})

@app.post("/events/<event_id>/reservations")
def rest_reserve(event_id):
    ev = EVENTS[event_id]
    if ev["capacity"] - ev["seatsTaken"] <= 0:              # rule, copy 1
        return jsonify({"error": "sold_out"}), 409
    ev["seatsTaken"] += 1
    rid = f"res_{NEXT['n']}"; NEXT["n"] += 1
    RESERVATIONS[rid] = {"id": rid, "eventId": event_id, "status": "confirmed"}
    return jsonify(RESERVATIONS[rid]), 201

# ---- GraphQL projection: computes seats from the RESERVATIONS ----
SDL = gql("""
  type Query { event(id: ID!): Event }
  type Mutation { cancelReservation(id: ID!): Boolean! }
  type Event { id: ID!  title: String!  seatsLeft: Int! }
""")
query, mutation = QueryType(), MutationType()

@query.field("event")
def gql_event(_, info, id):
    ev = EVENTS[id]
    confirmed = sum(1 for r in RESERVATIONS.values()
                    if r["eventId"] == id and r["status"] == "confirmed")
    return {"id": ev["id"], "title": ev["title"],
            "seatsLeft": ev["capacity"] - confirmed}        # rule, copy 2

@mutation.field("cancelReservation")
def gql_cancel(_, info, id):
    # The NEW rule, implemented where the maintainer was looking:
    RESERVATIONS[id]["status"] = "cancelled"
    # ...and nobody told the counter.  <- the bug is this missing line's absence
    return True

schema = make_executable_schema(SDL, query, mutation)

@app.post("/graphql")
def graphql_endpoint():
    ok, result = graphql_sync(schema, request.get_json())
    return jsonify(result), (200 if ok else 400)

if __name__ == "__main__":
    app.run(port=3000)
