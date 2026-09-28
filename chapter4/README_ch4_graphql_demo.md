# Chapter 4 demo — GraphQL (query-oriented), listing_4_1_graphql.py

A runnable Encore GraphQL service (schema-first, using **ariadne**) that
demonstrates Chapter 4's query-oriented style: the caller states the *shape*
of the data and gets exactly it, and a whole subgraph arrives in one round trip.

## 1. Install (mind the version pin!)

```bash
pip install -r requirements.txt
```

`requirements.txt` pins `graphql-core>=3.2,<3.3`. **This matters:** ariadne
breaks with a mismatched graphql-core (`ImportError: cannot import name
'ExecutionContext' from 'graphql'`). If you hit that error, the fix is:

```bash
pip install "graphql-core>=3.2,<3.3"
```

(Good teaching point: GraphQL libraries are sensitive to their graphql-core
version — a real-world dependency lesson.)

## 2. Run the server (terminal 1)

```bash
python listing_4_1_graphql.py        # serves POST /graphql on :4000
```

## 3. Try it — three ways to demo

### Option A — the driver script (terminal 2)

```bash
python demo_queries.py
```

Fires three queries and prints a teaching note about the N+1 moving into resolvers.

### Option B — curl by hand

```bash
# caller asks for ONLY title + seatsLeft (precise shape, no over-fetching)
curl -s -X POST http://localhost:4000/graphql -H "Content-Type: application/json" \
  -d '{"query":"{ events(bookable: true) { title seatsLeft } }"}'

# events WITH each event's reservations, in ONE round trip (REST's N+1, gone from the wire)
curl -s -X POST http://localhost:4000/graphql -H "Content-Type: application/json" \
  -d '{"query":"{ events { title reservations { id status } } }"}'
```

### Option C — GraphiQL / a browser playground (most visual for class)

ariadne can serve an interactive in-browser query explorer. Add this to the
script (or mention it in class):

```python
from ariadne.explorer import ExplorerGraphiQL
@app.get("/graphql")
def graphql_playground():
    return ExplorerGraphiQL().html(None), 200
```

Then open http://localhost:4000/graphql in a browser and type queries live —
the equivalent of Swagger UI, but for GraphQL.

## What each demo shows (the Chapter 4 points)

1. **The caller states the shape** — ask for `title seatsLeft`, get exactly
   those fields. No over-fetching (contrast the REST resource that returns the
   whole object).
2. **One round trip for a subgraph** — `events { reservations { ... } }` fetches
   events *and* their reservations in a single request. This is the N+1 of
   Exercise 1.8, gone from the wire.
3. **But the N+1 MOVED, it didn't vanish.** Look at `resolve_reservations` in
   the listing — the comment says it: *"runs once PER EVENT in the result."*
   The client made one request; a naive server made N database lookups behind
   the boundary. Chapter 4's refrain: **styles relocate costs; they rarely
   delete them.** (The fix is a dataloader/batching — Exercise material.)

## Note on where this sits

Every GraphQL request is a `POST /graphql` to one URL — so HTTP caching and
safe-retry-by-method go blind (Section 4.3). That's the trade for the shape
flexibility. Query-orientation nets positive for *your own, shape-diverse
frontends*, not for anonymous exterior traffic.
