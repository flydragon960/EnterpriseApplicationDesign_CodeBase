# Chapter 4 demo — gRPC (RPC, the interior style)

Runnable Encore gRPC service + client (listing_4_2). Demonstrates Chapter 4's
RPC style: a typed `.proto` contract, generated code, and — the capability new
to this book — **server-side streaming** (`WatchSeats` pushes updates over one
connection).

Files:
  encore.proto                  the RPC contract (Protocol Buffers)
  listing_4_2_grpc_server.py    the service
  listing_4_2_grpc_client.py    a client that calls it (incl. the stream)

## 1. Install

```bash
pip install -r requirements.txt
```

(`grpcio` = the runtime; `grpcio-tools` = the `.proto` compiler `protoc`.)

## 2. Compile the .proto — THE STEP PEOPLE FORGET

Unlike REST/GraphQL, gRPC needs a code-generation step. The server and client
both `import encore_pb2, encore_pb2_grpc`, and **those two files do not exist
until you generate them from encore.proto**:

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. encore.proto
```

This creates two files in the current directory:
  encore_pb2.py        message classes (Event, ListEventsRequest, ...)
  encore_pb2_grpc.py   service stubs (EncoreStub, EncoreServicer, ...)

If you skip this step you get:  `ModuleNotFoundError: No module named 'encore_pb2'`.
That error means "you didn't compile the .proto," not "a library is missing."

## 3. Run — two terminals

Terminal 1 (server, listens on localhost:50051):
```bash
python listing_4_2_grpc_server.py
```

Terminal 2 (client):
```bash
python listing_4_2_grpc_client.py
```

Expected output:
```
bookable: [('Jazz Ensemble: Fall Concert', 42)]
watching seats on ev_101:
  seats_left = 42
  seats_left = 41        <- PUSHED by the server, over one connection
  seats_left = 40
```

## What each part shows (the Chapter 4 points)

1. **Typed contract + generated code.** `encore.proto` is the contract; `protoc`
   generates typed stubs into every language. The client reads like local code
   (`stub.ListEvents(...)`) — Chapter 1's "costume," worn openly.
2. **Native streaming.** `WatchSeats` returns `stream SeatUpdate`; the server
   `yield`s three updates over one connection. The request/response grammar of
   REST/GraphQL cannot say this sentence — the resource world's answers
   (polling, or stepping outside to WebSockets) come from *outside* the style.
3. **The costs mirror the strengths (talk through, not shown by curl):**
   - Binary wire → opaque to humans/generic tooling: you can't `curl` it or
     grep the payload; every debug goes through the schema.
   - Generated code → couples every caller to a toolchain (they must run
     `protoc` in their build). A demand you make of teams you employ, not of
     strangers. Browsers need a proxy (gRPC-Web).
   - Field numbers are their own compatibility system: renaming a field is free
     (the wire carries the *number*), but RENUMBERING is silent data corruption
     — a different taxonomy from Chapter 3.

So gRPC is the **interior** style: service-to-service, both sides owned, high
volume, streaming real, humans out of the loop. The exterior stays
resource-oriented.

## Common gotchas (for students)

- `ModuleNotFoundError: encore_pb2` → you skipped step 2 (compile the .proto).
- Regenerate the pb2 files whenever you edit `encore.proto`.
- On Windows the compile command is the same (`python -m grpc_tools.protoc ...`).
- Keep all files in one directory so the generated `import encore_pb2` resolves.
- Newer generated code may need the current directory on the import path; if you
  reorganize into packages, add an `__init__.py` or adjust `-I` paths.

## Try it yourself: inspect the service without a client

gRPC has a reflection/inspection tool, grpcurl (separate install), e.g.:
```bash
grpcurl -plaintext localhost:50051 encore.Encore/ListEvents
```
Mention it as the "there is a way to poke a gRPC service by hand" note — but it
underscores the point: you needed a *special tool*, unlike `curl` for REST.
