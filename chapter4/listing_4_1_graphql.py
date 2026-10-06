# Listing 4.1 -- Encore's boundary, query-oriented (GraphQL, schema-first).
# The SDL document below plays the role encore-openapi.yaml played in
# Chapter 2: authored contract, implementation conforming to it.
# Run: python3 listing_4_1_graphql.py    (serves POST /graphql on :4000)
from ariadne import QueryType, gql, make_executable_schema, graphql_sync
from flask import Flask, jsonify, request

SDL = gql("""
  type Query {
    "Events, most imminent first. Safe: reading changes nothing."
    events(bookable: Boolean): [Event!]!
    "One event, or null if the id is unknown."
    event(id: ID!): Event
  }

  type Event {
    id: ID!
    title: String!
    "Point-in-time observation, not a promise; may be stale by booking time."
    seatsLeft: Int!
    "Reservations made against this event."
    reservations: [Reservation!]!
  }

  type Reservation {
    id: ID!
    status: String!
    createdAt: String!
  }
""")

EVENTS = [
    {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert", "seatsLeft": 42},
    {"id": "ev_102", "title": "Improv Night", "seatsLeft": 0},
    {"id": "ev_103", "title": "Film Society: Friday Screening", "seatsLeft": 15},
]
RESERVATIONS = {
    "ev_101": [{"id": "res_1", "status": "confirmed",
                "createdAt": "2026-09-12T19:00:00Z"}],
    "ev_102": [], "ev_103": [],
}

query = QueryType()

@query.field("events")
def resolve_events(_, info, bookable=None):
    evs = EVENTS
    if bookable:
        evs = [e for e in evs if e["seatsLeft"] > 0]
    return evs

@query.field("event")
def resolve_event(_, info, id):
    return next((e for e in EVENTS if e["id"] == id), None)

# Field-level resolver: runs once PER EVENT in the result -- remember this.
def resolve_reservations(event, info):
    return RESERVATIONS.get(event["id"], [])

schema = make_executable_schema(SDL, query,
    # attach the Event.reservations resolver
)
from ariadne import ObjectType
event_type = ObjectType("Event")
event_type.set_field("reservations", resolve_reservations)
schema = make_executable_schema(SDL, query, event_type)

app = Flask(__name__)

@app.post("/graphql")
def graphql_endpoint():
    ok, result = graphql_sync(schema, request.get_json())
    return jsonify(result), (200 if ok else 400)

if __name__ == "__main__":
    app.run(port=4000)
