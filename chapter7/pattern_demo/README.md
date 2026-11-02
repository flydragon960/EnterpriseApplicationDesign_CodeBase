# Section 7.1 Demo: Pessimistic and Optimistic Locking

These three small scripts accompany Section 7.1 ("Transactions and ACID") of
Chapter 7. They show the lost-update race in its simplest form and the two
locking patterns that fix it, using plain SQL through SQLAlchemy. There is no
Flask, no domain model, and no repository here: each script is self-contained.

(For the full Encore application with the same patterns, see the separate
`chapter7-demo` folder.)

---

## 1. The files

| File | What it shows | In the chapter |
|---|---|---|
| `locking_demo.py` | All three side by side: **unsafe**, **pessimistic**, **optimistic**. Adds a 50 ms pause between read and write so the race shows up every time. | The "Concurrency test" output in Section 7.1 |
| `pessimistic_lock.py` | `book_pessimistic()` alone: one transaction, `SELECT ... FOR UPDATE` | Listing 7.1 |
| `optimistic_lock.py` | `book_optimistic()` alone: version column, conditional `UPDATE`, retry loop | Listing 7.2 |

All three use the same story: an event has **2 seats**, and **5 students**
(kim, ana, raj, lee, tom) click "Book" at the same moment, each in its own
thread. A correct system confirms exactly 2 bookings and leaves 0 seats.

The `race()` function in each file is Listing 7.3.

---

## 2. Prerequisites

| Tool | Check with |
|---|---|
| Python 3.10 or later | `python3 --version` (Windows: `python --version`) |
| Docker Desktop, or Docker Engine on Linux | `docker --version` |

Why PostgreSQL? SQLite does not support `SELECT ... FOR UPDATE`, which the
pessimistic pattern needs. (`optimistic_lock.py` also runs on SQLite; see
section 7.)

---

## 3. Start PostgreSQL

The scripts connect to:

```
postgresql+psycopg://postgres:pw@localhost:5432/encore
```

that is, user `postgres`, password `pw`, database `encore`, port 5432.

```bash
docker run -d --name ch71-db \
  -e POSTGRES_PASSWORD=pw \
  -e POSTGRES_DB=encore \
  -p 5432:5432 \
  postgres:16
```

Check it with `docker ps` and wait a few seconds for PostgreSQL to start.

> **Warning: these scripts drop and recreate the tables `events` and
> `reservations` every time they run.** Do not point them at a database you
> care about, and do not run them against the `chapter7-demo` container
> (`encore-db`): it uses the same table names, and its data would be lost.
> The two demos also use different users and drivers, so give each its own
> container. If `encore-db` is already using port 5432, stop it first
> (`docker stop encore-db`), or see Troubleshooting.

---

## 4. Install the Python packages

```bash
cd section7-1-demo
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install sqlalchemy "psycopg[binary]"
```

These scripts use **psycopg version 3** (`postgresql+psycopg://`). The
`chapter7-demo` folder uses the older `psycopg2`. They are different packages;
install the one each demo's connection string names.

---

## 5. Run the demo

A suggested order for class: run `locking_demo.py` first to show the problem
and both fixes together, then open the two single-pattern files and walk
through each listing.

### Step 1: all three side by side

```bash
python3 locking_demo.py
```

Expected output (the winners change from run to run; the counts do not):

```
unsafe       confirmed=['ana', 'kim', 'lee', 'raj', 'tom']  seats_left=-3  rows=5  retries=0  -> WRONG
pessimistic  confirmed=['kim', 'lee']  seats_left=0  rows=2  retries=0  -> correct
optimistic   confirmed=['ana', 'tom']  seats_left=0  rows=2  retries=7  -> correct
```

What to point out:

- **unsafe**: all five read "2 seats", all five decide "there is room", all
  five write. Every SQL statement ran correctly; the bug is in the gap between
  read and write. (This version's table has no `CHECK` constraint, so nothing
  stops `seats_left` from going negative.)
- **pessimistic**: `FOR UPDATE` makes the others wait at the `SELECT`. No
  retries, but the bookings happen one at a time.
- **optimistic**: nobody waits, but `retries=7` means seven attempts found the
  version had changed and started over. That is the cost of this pattern.

### Step 2: the pessimistic listing on its own

```bash
python3 pessimistic_lock.py
```

```
pessimistic  confirmed: ana tom  seats_left=0  reservations=2  correct
```

Walk through `book_pessimistic()`: one `with engine.begin()` block, the
`SELECT ... FOR UPDATE`, the `if` in Python, and the commit that releases the
lock when the block ends.

### Step 3: the optimistic listing on its own

```bash
python3 optimistic_lock.py
```

```
optimistic   confirmed: ana tom  seats_left=0  version=2  reservations=2  correct
```

Walk through `book_optimistic()`: the read of `seats_left` **and** `version`,
the conditional `UPDATE ... WHERE version = :v`, and the `rowcount` check that
decides between "we won" and "start over". `version=2` at the end means the
row was successfully changed twice, once per booking.

These two files have no artificial pause, so `optimistic_lock.py` often needs
few or no retries. To see retries, use `locking_demo.py`.

---

## 6. Watch a row lock by hand

This reproduces the two-session timeline from Section 7.1. Run
`pessimistic_lock.py` once so the tables exist, then open **two** terminals and
run this in each:

```bash
docker exec -it ch71-db psql -U postgres -d encore
```

Type, in this order:

```sql
-- Terminal A
BEGIN;
SELECT seats_left FROM events WHERE id = 1 FOR UPDATE;

-- Terminal B
BEGIN;
SELECT seats_left FROM events WHERE id = 1 FOR UPDATE;
-- Terminal B now hangs: it is waiting for A's lock.

-- Terminal A
COMMIT;
-- Terminal B returns immediately.

-- Terminal B
ROLLBACK;
```

While B is waiting, try a plain `SELECT seats_left FROM events WHERE id = 1;`
in a third terminal. It returns at once: `FOR UPDATE` blocks other writers,
not ordinary readers.

To try the optimistic version by hand, in two terminals read
`SELECT seats_left, version FROM events WHERE id = 1;`, then run the same
`UPDATE events SET seats_left = seats_left - 1, version = version + 1 WHERE id = 1 AND version = <the version you read>;`
in both. The first reports `UPDATE 1`, the second `UPDATE 0`.

Type `\q` to leave `psql`.

---

## 7. Experiments for students

1. **Change the timing.** In `locking_demo.py`, set `THINK_TIME = 0` and run
   it several times. Does the unsafe race disappear, or only get rarer?
2. **Change the capacity.** In `race()`, change `reset_database(seats=2)` to
   `seats=4`. Predict the output before you run it.
3. **Remove the lock.** In `pessimistic_lock.py`, delete `FOR UPDATE` from the
   `SELECT`, and add `time.sleep(0.05)` (with `import time`) right after it to
   widen the window. Run it. You will see `CheckViolation` exceptions from
   three threads, and the final line may still say "correct". The
   `CHECK (seats_left >= 0)` constraint caught the overselling, because the
   `UPDATE` subtracts from the current value. Discuss: is this a fix? (The
   losers crash with a database error instead of being told "sold out", and the
   constraint only helps because this rule fits in one row; Encore's real rule,
   "confirmed reservations ≤ capacity", spans many rows and cannot be a
   `CHECK`.)
4. **Remove the version check.** In `optimistic_lock.py`, delete
   `AND version = :v` from the `UPDATE`. What changes, and why?
5. **Run the optimistic version on SQLite.** In `optimistic_lock.py`, comment
   out the PostgreSQL `DATABASE_URL` and uncomment the SQLite one. No other
   change is needed, because the pattern uses only standard SQL. (Try the same
   with `pessimistic_lock.py`: it fails, because SQLite has no `FOR UPDATE`.)

Restore the original files afterwards (or re-download them).

---

## 8. Stopping and cleaning up

```bash
docker stop ch71-db        # stop; data kept
docker start ch71-db       # start again
docker rm -f ch71-db       # delete the container and its data
```

Every script resets its own tables when it starts, so you never need to clean
the data between runs.

---

## 9. Troubleshooting

**`ModuleNotFoundError: No module named 'psycopg'`**
Install `"psycopg[binary]"` and check that your virtual environment is active.
(`psycopg2-binary` is a different package and does not satisfy this import.)

**`connection ... failed: Connection refused`**
PostgreSQL is not running or not ready yet. Run `docker ps`, use
`docker start ch71-db` if needed, and wait a few seconds.

**`password authentication failed for user "postgres"`**
The container was created with a different password. Remove it
(`docker rm -f ch71-db`) and run the command in section 3 exactly.

**`Bind for 0.0.0.0:5432 failed: port is already allocated`**
Another PostgreSQL (often `encore-db` from the `chapter7-demo` folder) is using
port 5432. Stop it with `docker stop encore-db`, or start this container with
`-p 5433:5432` and change `localhost:5432` to `localhost:5433` in the three
scripts.

**`TooManyRetries` or `RuntimeError: gave up after 10 attempts`**
The optimistic loop lost the race ten times in a row. This is rare with five
students; if you raised the number of students a lot, raise `max_attempts` too.

**`database is locked` (SQLite only)**
SQLite allows only one writer at a time and can time out under heavy
concurrency. It is a limitation of SQLite, not of the optimistic pattern;
PostgreSQL does not have it.
