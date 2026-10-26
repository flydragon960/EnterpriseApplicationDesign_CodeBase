# Chapter 7 Demo: Transactions and Concurrency

This demo reproduces the race from the end of Chapter 6 (five students, two
seats, `seatsLeft: -3`) and fixes it two ways: **pessimistic locking**
(`SELECT ... FOR UPDATE`) and **optimistic locking** (a version column and a
retry loop). It then runs the Encore API with the safe path as the only path.

You will need about 15 minutes for a first run.

---

## 1. What is in this folder

```
chapter7-demo/
├── domain.py     # from Chapter 5, unchanged (copy it in; see below)
├── storage.py    # Listing 7.1: repository with three ways to save
├── service.py    # Listing 7.2: one use case, three concurrency disciplines
├── race.py       # Listing 7.3: five students race for two seats
├── app.py        # Listing 7.4: the Flask API, pessimistic path only
└── double_click.py  # one student clicks eight times: still one booking
```

You do **not** need any code from Chapter 6. These files replace Chapter 6's
`storage.py`, `service.py`, and `app.py`.

You **do** need `domain.py` from Chapter 5. Copy it into this folder
unchanged. Both `storage.py` and `service.py` import from it.

---

## 2. Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Python | 3.10 or later | `python3 --version` (Windows: `python --version`) |
| Docker Desktop (or Docker Engine on Linux) | any recent | `docker --version` |
| curl | any | `curl --version` (Windows PowerShell: use `curl.exe`) |

Docker runs PostgreSQL for you. If you already have PostgreSQL installed
locally, you can use it instead; see "Using a local PostgreSQL" in
Troubleshooting.

Why PostgreSQL and not SQLite? SQLite does not support `SELECT ... FOR UPDATE`,
which the pessimistic discipline needs (Section 7.1).

---

## 3. Start PostgreSQL

The code connects to:

```
postgresql+psycopg2://encore:encore@localhost/encore
```

that is, user `encore`, password `encore`, database `encore`, port 5432.
Start a container that matches:

```bash
docker run -d --name encore-db \
  -e POSTGRES_USER=encore \
  -e POSTGRES_PASSWORD=encore \
  -e POSTGRES_DB=encore \
  -p 5432:5432 \
  postgres:16
```

On Windows PowerShell, write it on one line or replace each `\` with a
backtick (`` ` ``).

Check that it is running:

```bash
docker ps
```

You should see `encore-db` with status `Up`. Wait a few seconds after the
first start before running the demo; PostgreSQL needs a moment to initialize.

You do not create any tables yourself. The first time the Python code runs,
`make_session_factory()` creates the `events`, `reservations`, and
`idempotency` tables.

---

## 4. Install the Python packages

Create a virtual environment so the packages stay with this project:

```bash
cd chapter7-demo
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install flask sqlalchemy psycopg2-binary
```

Note the driver: the connection string says `psycopg2`, so install
`psycopg2-binary`. The newer `psycopg` (version 3) package will **not** work
with this connection string.

---

## 5. Run the race: three disciplines

`race.py` resets the database to one event, `ev_103`, with **capacity 2**.
Five students (kim, ana, raj, lee, mia) try to reserve at the same moment.
Each attempt pauses 0.4 seconds between deciding and saving
(`demo_delay=0.4`) to widen the race window so the result is reproducible.

Run the three disciplines one after another:

```bash
python3 race.py unsafe
python3 race.py pessimistic
python3 race.py optimistic
```

Reservation ids are random and the winners change from run to run, but the
counts should look like this.

**Unsafe** (Chapter 6's load-check-save, kept as the control):

```
  kim: 201 res_33c870c6
  ana: 201 res_4e6d0ed3
  raj: 201 res_6ffa0583
  lee: 201 res_396247e6
  mia: 201 res_974f5626
  capacity 2 -> confirmed 5, seatsLeft -3, elapsed 0.5s
```

Five confirmations for two seats. Every request loaded its own copy of the
event, each copy honestly showed two seats, and each passed the domain check.

**Pessimistic** (one transaction holds a row lock from load to commit):

```
  kim: 201 res_58d458fa
  ana: 409 sold_out
  raj: 409 sold_out
  lee: 201 res_0cd9aaed
  mia: 409 sold_out
  capacity 2 -> confirmed 2, seatsLeft 0, elapsed 0.9s
```

Correct. Notice the longer elapsed time: the requests queued at the lock.

**Optimistic** (conditional write on a version number; retry on conflict):

```
  kim: 201 res_8d04358d
  ana: 409 sold_out  (retries=2)
  raj: 409 sold_out  (retries=2)
  lee: 409 sold_out  (retries=2)
  mia: 201 res_40e1c1f1  (retries=1)
  capacity 2 -> confirmed 2, seatsLeft 0, elapsed 1.0s
```

Correct. Nobody waited for a lock, but several attempts found the version had
changed and started over.

### Things to try

- Run each discipline several times and compare who wins and how many retries
  happen.
- In `race.py`, change `demo_delay=0.4` to `demo_delay=0`. The unsafe race
  becomes less reliable but does not disappear; the window is smaller, not
  closed.
- Change the capacity in `reset()` from 2 to 4 and predict the output before
  you run it.

---

## 6. Run the double-click test

A student who double-clicks, or whose browser retries after a timeout, sends
the **same** request with the **same** `Idempotency-Key` several times, often
at the same moment. `double_click.py` sends eight such requests at once to an
event with 10 seats:

```bash
python3 double_click.py pessimistic
python3 double_click.py optimistic
```

```
  click 1: 201 res_9fbdb3a8  (booked)
  click 2: 201 res_9fbdb3a8  (replayed)
  ...
  click 8: 201 res_9fbdb3a8  (replayed)
  8 clicks -> 1 reservation(s), seatsLeft 9 of 10
```

All eight get the same reservation; only one seat is taken. This works
because the booking and its idempotency record are committed in **one**
transaction, and the primary key on the idempotency table lets only one
request own the key. The others find their transaction rolled back and replay
the winner's result.

---

## 7. Run the API

```bash
python3 app.py
```

The server listens on `http://localhost:3000`. On startup it adds two events
if they are missing: `ev_101` (capacity 42) and `ev_102` (capacity 0, already
sold out). Leave it running and open a second terminal for the requests below.

On Windows PowerShell, type `curl.exe` instead of `curl`.

**List events, and only the bookable ones:**

```bash
curl http://localhost:3000/events
curl "http://localhost:3000/events?bookable=true"
```

**Reserve a seat.** Every reservation request must carry an
`Idempotency-Key` header. Use a new, unique key for each new reservation:

```bash
curl -i -X POST -H "Idempotency-Key: demo-001" \
  http://localhost:3000/events/ev_101/reservations
```

```
HTTP/1.1 201 CREATED
{"createdAt":"...","eventId":"ev_101","id":"res_dec383d3","status":"confirmed"}
```

**Retry the same request with the same key.** The server recognizes the key
and replays the original result instead of booking a second seat:

```bash
curl -i -X POST -H "Idempotency-Key: demo-001" \
  http://localhost:3000/events/ev_101/reservations
```

```
HTTP/1.1 201 CREATED
Idempotency-Replayed: true
{"createdAt":"...","eventId":"ev_101","id":"res_dec383d3","status":"confirmed"}
```

Check that only one seat was taken:

```bash
curl http://localhost:3000/events/ev_101
```

```
{"id":"ev_101","seatsLeft":41,"title":"Jazz Ensemble: Fall Concert"}
```

**The error cases:**

| Request | Response |
|---|---|
| `POST /events/ev_101/reservations` with no `Idempotency-Key` header | `422 {"error":"idempotency_key_required"}` |
| `POST /events/ev_102/reservations` (sold-out event) | `409 {"error":"sold_out"}` |
| The same sold-out request again, same key | `409 {"error":"sold_out"}` with `Idempotency-Replayed: true` |
| `POST /events/ev_999/reservations` (no such event) | `404 {"error":"not_found"}` |
| A key already used for a **different event** (for example `demo-001` sent to `ev_102`) | `422 {"error":"idempotency_key_reuse"}` |
| A key already used, same event, but a **different request body** | `422 {"error":"idempotency_key_reuse"}` |

A key identifies one specific request: the operation, the event, and the
body. Sending it with anything else is treated as a client error, not as a
retry.

**Double-click over HTTP** (macOS/Linux shell): six identical requests in
parallel, then check the seat count. It drops by exactly one.

```bash
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -w "%{http_code} " -X POST \
    -H "Idempotency-Key: dbl-1" \
    http://localhost:3000/events/ev_101/reservations &
done; wait; echo
curl http://localhost:3000/events/ev_101
```

Stop the server with `Ctrl+C`.

---

## 8. Optional: watch a row lock with your own eyes

This reproduces the two-session timeline from Section 7.1 by hand. Open two
terminals and run this in each:

```bash
docker exec -it encore-db psql -U encore -d encore
```

Then type, in this order:

```sql
-- Terminal A
BEGIN;
SELECT * FROM events WHERE id = 'ev_101' FOR UPDATE;

-- Terminal B
BEGIN;
SELECT * FROM events WHERE id = 'ev_101' FOR UPDATE;
-- Terminal B now hangs: it is waiting for A's lock.

-- Terminal A
COMMIT;
-- Terminal B returns immediately.

-- Terminal B
ROLLBACK;
```

Type `\q` to leave `psql`.

---

## 9. Stopping and resetting

```bash
docker stop encore-db       # stop; data is kept
docker start encore-db      # start again later
docker rm -f encore-db      # delete the container and its data
```

To start completely fresh, delete the container and run the `docker run`
command from step 3 again. `race.py` also resets its own data each time it
runs, so you rarely need a full reset.

---

## 10. Troubleshooting

**`ModuleNotFoundError: No module named 'domain'`**
Copy Chapter 5's `domain.py` into this folder.

**`ModuleNotFoundError: No module named 'psycopg2'`**
Install `psycopg2-binary`, and make sure your virtual environment is active.

**`connection to server at "localhost" ... Connection refused`**
PostgreSQL is not running or not ready yet. Run `docker ps`, start the
container with `docker start encore-db` if needed, and wait a few seconds.

**`password authentication failed for user "encore"`**
The container was created with different credentials. Remove it with
`docker rm -f encore-db` and run the command from step 3 exactly.

**`Bind for 0.0.0.0:5432 failed: port is already allocated`**
Another PostgreSQL is already using port 5432. Either stop it, or map the
container to another port with `-p 5433:5432` and change the URL in both
`race.py` and `app.py` to `...@localhost:5433/encore`.

**`column events.version does not exist`**
The database still holds an `events` table from an earlier run without the
`version` column. `create_all()` creates missing tables but never adds columns
to existing ones. Delete the container (`docker rm -f encore-db`) and start
again from step 3.

**Every discipline, even pessimistic, oversells**
Check Chapter 5's `domain.py`: `Event.seats_left` must be computed from the
confirmed entries in `event.reservations`. The repository rebuilds an `Event`
by filling `event.reservations`; it does not set a separate seat counter.

**`Address already in use` when starting `app.py`**
Another program is using port 3000. Change `port=3000` at the bottom of
`app.py`, or stop the other program.

**`422 {"error":"idempotency_key_reuse"}` on a request you expected to work**
You reused a key from an earlier, different request: another event, another
body, or a key that `race.py` or `double_click.py` already used (such as
`kim-1`). Use a new key for each new reservation; reuse a key only to retry
exactly the same request.

**Using a local PostgreSQL instead of Docker**
Create the user and database once, then run the demo as above:

```sql
CREATE ROLE encore LOGIN PASSWORD 'encore';
CREATE DATABASE encore OWNER encore;
```
