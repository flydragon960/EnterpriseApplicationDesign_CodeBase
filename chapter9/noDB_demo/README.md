# Encore, Chapter 9 — classroom demo (no database)

The reserve → hold → charge → confirm flow from Chapter 9, with PostgreSQL,
SQLAlchemy and Flask removed. It needs only Python 3.9+ and the standard library.

## Run it

    python3 demo.py              # every branch, in order (about 5 seconds)
    python3 demo.py list         # branch names
    python3 demo.py timeout      # one branch
    python3 demo.py happy crash  # several

On Windows, use `python` in place of `python3`.

`demo.py` starts the payment provider on port 4000 if it is not already
running, and stops it on exit. To show the two processes side by side, start
`python3 payment_provider.py` in a second terminal first.

## Branches

| Name       | Section | What it shows |
|------------|---------|---------------|
| `happy`    | 9.2     | Hold, charge, confirm. |
| `decline`  | 9.4     | Card refused; the hold is released and the seat is freed. |
| `expiry`   | 9.4     | Charge succeeds after the hold expired; a refund is owed. |
| `rollback` | 9.2     | A failure before COMMIT writes neither the hold nor the intent. |
| `crash`    | 9.2     | A real process crash after the hold; the outbox entry survives. |
| `timeout`  | 9.3     | Charge taken, reply lost; the worker asks, and the same key cannot charge twice. |
| `refund`   | 9.6     | The refund fails once (503), then succeeds on retry. |

## Files

| File                  | Listing | Change from the database version |
|-----------------------|---------|----------------------------------|
| `domain.py`           | 9.1     | None. |
| `payment_provider.py` | 9.2     | `http.server` in place of Flask; same endpoints and failure switches. |
| `storage.py`          | 9.3     | One JSON file in place of PostgreSQL; same unit-of-work interface. |
| `worker.py`           | 9.4     | Same logic on the JSON store. |
| `demo.py`             | —       | Four more branches; starts the provider itself. |

## Where the state lives

`encore_state.json`, created next to the scripts. A transaction reads the file,
changes a copy in memory, and commits by writing a temp file and renaming it
over the old one. The rename is all-or-nothing, so the hold and its outbox
entry still commit together, and they survive a crash. Open the file in an
editor during class to watch the reservation and outbox entry change.

Not provided, unlike PostgreSQL: row locks and concurrent writers. A single
lock stands in for `SELECT ... FOR UPDATE`, and the worker assumes it is the
only worker.
