# EnterpriseApplicationDesign_CodeBase
SONE387 Demo Code 2026 Version
Layout: one folder per chapter, matching the book's listings.
  chapter1/   stdlib + Flask handlers, Ch.1 exercise solutions
  chapter2/   OpenAPI contract + conformance suite
  chapter3/   idempotency/retry server + client
  chapter4/   GraphQL, gRPC (proto + server/client), tool schema
  chapter5/   domain / service / app layers
  chapter6/   repository, SQLite mapper, migrations
  chapter7/   Postgres storage, optimistic+pessimistic concurrency, race harness
  chapter8/   JWT auth, forgery attacks, authorized app
  chapter9/   payment provider, outbox worker, compensation demo
  chapter10/  test pyramid, consumer contracts, observability, eval harness
  chapter11/  config, health/readiness app, rollout sim, Dockerfile, compose
  chapter12/  rate limiter, circuit breaker, caching, statelessness

Infrastructure notes:
  - Chapters 6+ use SQLite; Chapters 7-9 use PostgreSQL
    (user encore / password encore / db encore).
  - pip install: flask sqlalchemy psycopg2-binary ariadne grpcio grpcio-tools
    pyjwt cryptography pytest gunicorn jsonschema
  - Every listing was executed; outputs in the book are real runs.
