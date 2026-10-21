# Encore — Chapter 6 Demo: The Data Source Layer

SOEN 387 · Web-Based Enterprise Application Design · Concordia University

This demo makes Encore's state **durable**. Events, reservations, idempotency records and the id counter now live in a SQLite database file instead of in one process's memory. With the demo you can verify the chapter's claims yourself:

- Promises survive a **restart**.
- Two **instances** share one truth.
- A **race** between five simultaneous writers still breaks the seat invariant. That is Chapter 7's problem.

---

## 1. Requirements

| Requirement | Version | Why |
|---|---|---|
| Python | 3.10 or later | The ORM mappings use modern type-hint syntax |
| SQLite (bundled with Python) | **3.35 or later** | `SqliteIdSequence.next()` uses `UPDATE ... RETURNING` |
| Flask, SQLAlchemy | SQLAlchemy 2.x | Installed with `pip` in step 3 |

### Check your SQLite version

Python ships with SQLite built in; you do **not** install it separately. Check which version your Python uses:

```bash
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
```

If the number is below `3.35`, upgrade Python. Otherwise the first reservation fails with a syntax error near `RETURNING`.

The separate `sqlite3` **command-line tool** is optional. It is handy for looking inside the database (section 6) but is not needed to run the demo:

```bash
sqlite3 --version
```

---

## 2. Project layout

Put all files in one folder:

```
encore-ch6/
├── app.py                 # Listing 6.4 — the wiring point (Flask)
├── service.py             # Listing 6.3 — the service layer, now against interfaces
├── repository.py          # Listing 6.1 — the three repository interfaces
├── sqlite_repository.py   # Listing 6.2 — SQLite implementations (Data Mapper role)
├── migrate.py             # Listing 6.5 — versioned schema migrations
└── domain.py              # Chapter 5's domain layer, unchanged
```

Two things are easy to miss:

- The interface file **must be named `repository.py`**, because `sqlite_repository.py` does `from repository import ...`.
- `domain.py` is **Chapter 5's file, copied unchanged**. The domain layer did not change in this chapter.

---

## 3. Set up the environment

```bash
cd encore-ch6
python3 -m venv .venv
source .venv/bin/activate          # Windows (cmd/PowerShell): .venv\Scripts\activate
pip install flask sqlalchemy
```

> **Windows users:** run the `curl` commands below in **Git Bash** or **WSL**. PowerShell's `curl` is a different program with different quoting rules.

---

## 4. Start the server

```bash
python3 app.py 3000 encore.db
```

The two arguments are the port and the database file. On first start the server:

1. creates `encore.db` and all tables, and
2. seeds three events (only if the database is empty, so a restart never re-creates state):

| id | title | capacity |
|---|---|---|
| `ev_101` | Jazz Ensemble: Fall Concert | 42 |
| `ev_102` | Improv Night | 0 |
| `ev_103` | Film Society: Friday Screening | 2 |

Leave this terminal running and open a **second terminal** for the commands below.

---

## 5. The demos

### 5.1 List events

```bash
curl -s localhost:3000/events
curl -s "localhost:3000/events?bookable=true"
```

`bookable=true` filters out sold-out events (`ev_102`). This listing is served by the **read model** `list_summaries()`: one SQL query, no domain objects.

### 5.2 Reserve a seat, then retry

```bash
curl -s -i -X POST localhost:3000/events/ev_101/reservations \
     -H "Idempotency-Key: demo-1"
```

Expected: `201 Created` with a body containing `"id": "res_1"`.

Run the **same command again**. Expected:

- the same `res_1`, and
- the response header `Idempotency-Replayed: true`.

The seat count does not move twice:

```bash
curl -s localhost:3000/events/ev_101          # seatsLeft: 41
```

### 5.3 Restart survival (Section 6.6)

1. In the server terminal, press **Ctrl+C**. Then restart against the **same file**:

   ```bash
   python3 app.py 3000 encore.db
   ```

2. In the second terminal:

   ```bash
   curl -s localhost:3000/reservations/res_1
   curl -s -i -X POST localhost:3000/events/ev_101/reservations \
        -H "Idempotency-Key: demo-1"
   curl -s localhost:3000/events/ev_101
   ```

Expected:

- the receipt `res_1` is still there;
- the retry is still recognized as a replay (`Idempotency-Replayed: true`);
- `seatsLeft` is still **41**.

The promise now outlives the process that made it.

### 5.4 Two instances, one truth (Section 6.6)

Start a second instance in a **third terminal**, on another port but the **same database file**:

```bash
python3 app.py 3001 encore.db
```

Then send a reservation to one instance and its retry to the other:

```bash
curl -s -i -X POST localhost:3000/events/ev_101/reservations \
     -H "Idempotency-Key: demo-2"
curl -s -i -X POST localhost:3001/events/ev_101/reservations \
     -H "Idempotency-Key: demo-2"
curl -s localhost:3000/events/ev_101
curl -s localhost:3001/events/ev_101
```

Expected:

- the retry on `:3001` returns the **same** reservation, marked as replayed, even though `:3001` never saw the original request;
- both instances report the **same** `seatsLeft`.

The memory of the promise lives *behind* both instances, not *inside* either.

### 5.5 The race: what durability cannot buy (Section 6.9)

`ev_103` has **2 seats**. Five students click *Reserve* at the same instant, each with their own idempotency key.

The demo header `X-Demo-Slow-Reserve` makes each request pause between its read and its write. It does not create the gap between load and save; it only widens a gap that is always there, so the race reproduces reliably.

```bash
for u in kim ana raj lee mia; do
  curl -s -X POST localhost:3000/events/ev_103/reservations \
       -H "Idempotency-Key: race-$u" \
       -H "X-Demo-Slow-Reserve: 0.5" &
done; wait
echo
curl -s localhost:3000/events/ev_103
```

Expected:

- **five** `201` responses with five different reservation ids;
- `seatsLeft: -3`.

Everything is durable, and nothing is correct. Notice also that the five reservation ids are all **distinct**: the id counter is incremented by a *single* atomic statement, while the seat check spans *two* statements with a decision in between.

---

## 6. Look inside the database

With the `sqlite3` command-line tool:

```bash
sqlite3 encore.db "SELECT * FROM events;"
sqlite3 encore.db "SELECT * FROM reservations;"
sqlite3 encore.db "SELECT key, request_hash, ok, code FROM idempotency;"
sqlite3 encore.db "SELECT * FROM counters;"
```

Without it, use Python:

```bash
python3 -c "import sqlite3; db = sqlite3.connect('encore.db'); \
print(db.execute('SELECT * FROM reservations').fetchall())"
```

Things to notice:

- **`idempotency.value_json`** stores the whole outcome as one JSON string. This is a *Serialized LOB*: the database cannot query inside it, and it never needs to.
- **`reservations.event_id`** is a *Foreign Key Mapping* of the object reference `event.reservations`.
- **`counters`** is a *key table*: the id sequence persisted as a row.

---

## 7. Start over

Delete the database file. The next start re-creates the tables and re-seeds the three events:

```bash
rm encore.db            # Windows (cmd): del encore.db
```

---

## 8. About `migrate.py`

`migrate.py` applies numbered SQL files from a `migrations/` folder, in order, and records each one in a `schema_version` table so it is never applied twice:

```
migrations/
├── 001_initial.sql
└── 002_add_venue.sql
```

```bash
python3 migrate.py encore.db
```

You do **not** need it to run the demos above, because `app.py` creates the tables on startup. Use it for the schema-evolution exercises (Section 6.8 and Exercises 6 and 7).

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'repository'` | The interface file has a different name | Rename it to `repository.py` |
| `ModuleNotFoundError: No module named 'domain'` | Chapter 5's domain file is missing | Copy `domain.py` from Chapter 5 into the folder |
| `ModuleNotFoundError: No module named 'flask'` (or `sqlalchemy`) | Virtual environment not active, or packages not installed | `source .venv/bin/activate`, then `pip install flask sqlalchemy` |
| `sqlite3.OperationalError: near "RETURNING": syntax error` | Python's bundled SQLite is older than 3.35 | Upgrade Python (see section 1) |
| `Address already in use` | Another server is already on that port | Stop it (Ctrl+C), or choose another port: `python3 app.py 3002 encore.db` |
| `database is locked` | Many simultaneous writers on SQLite | Normally absorbed by the 30-second timeout in `sqlite_repository.py`; retry the request |
| The race shows `seatsLeft: 0`, not `-3` | Requests did not overlap | Make sure each `curl` line ends with `&`; increase the delay, e.g. `X-Demo-Slow-Reserve: 1.0` |
| Seeded data keeps reappearing, or old reservations linger | Old `encore.db` in use | Delete it (section 7) for a clean run |
