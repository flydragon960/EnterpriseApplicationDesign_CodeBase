"""
Demo driver for listing_4_1_graphql.py (Chapter 4, GraphQL / query-oriented).

Start the server first, in another terminal:
    python listing_4_1_graphql.py        # serves POST /graphql on :4000
Then run this:
    python demo_queries.py

It fires three queries that make Chapter 4's points visible.
"""
import json, urllib.request

URL = "http://localhost:4000/graphql"

def run(label, query):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    print("=" * 70)
    print(label)
    print("  query :", query.strip())
    print("  result:", json.dumps(data["data"], separators=(",", ":")))
    print()

# 1) The caller states the SHAPE -> gets exactly it (no over-fetching)
run("1. Caller asks for only title + seatsLeft (precise shape, no over-fetch)",
    "{ events(bookable: true) { title seatsLeft } }")

# 2) events + each event's reservations in ONE round trip (kills REST's N+1)
run("2. events WITH reservations in one request (the N+1 of Ex.1.8, one round trip)",
    "{ events { title reservations { id status } } }")

# 3) A single event
run("3. One event by id",
    '{ event(id: "ev_101") { id title seatsLeft } }')

print("NOTE (teaching point): query #2 returns the whole subgraph in ONE HTTP")
print("round trip -- but behind the boundary, resolve_reservations() runs ONCE")
print("PER EVENT. The N+1 didn't disappear; it MOVED into the resolvers.")
print("That is Chapter 4's refrain: styles relocate costs, they rarely delete them.")
