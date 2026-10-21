# Chapter 6 — Pattern Demos

Small, self-contained programs that show the data-source patterns from the Chapter 6 slides **running**. They are separate from the main Encore demo:

- no Flask, no SQLAlchemy, no `domain.py`;
- only Python's standard library (`sqlite3`);
- an **in-memory** database, so nothing is left on disk.

Every run starts from the same two seeded events: `ev_101` (capacity 42) and `ev_103` (capacity 2).

## Files

| File | What it shows | Slides |
|---|---|---|
| `schema.py` | The tiny shared schema (`events`, `reservations`, `idempotency`) and `fresh_db()` | — |
| `four_patterns.py` | Table Data Gateway, Row Data Gateway, Active Record and Data Mapper doing the **same** job | "Four ways to load and save an event" |
| `uow_identity_map.py` | A hand-built Identity Map and Unit of Work, repositories bound to the unit of work, and the service-layer `reserve()` | "Collect the changes, write them once", "One request, every pattern in its place" |
| `test_patterns.py` | The slides' claims pinned down as 10 tests | — |

## Requirements

Python 3.8 or later. Nothing to install. `pytest` is optional.

## Run

```bash
python3 four_patterns.py       # the four architectural patterns
python3 uow_identity_map.py    # identity map and unit of work, step by step
python3 test_patterns.py       # all tests   (or: pytest -q)
```

## What you should see

### `four_patterns.py`

Each pattern books `ev_103` three times. All four give the same answer:

```
res_1 ok | res_2 ok | res_3 SOLD OUT   seats left: 0
```

What differs is **where the rule lives**:

- **Gateways:** in a separate transaction script.
- **Active Record:** right beside its SQL.
- **Data Mapper:** in a pure `Event` class that never sees SQL.

### `uow_identity_map.py`

1. **Same row asked for twice.**
   - Without a map: two different objects and two rounds of SQL.
   - With a map: `a is b` is `True` and the second `get` sends **zero** SQL.
2. **Copies are dangerous even inside one request.** A group booking loads `ev_103` (1 seat left) through two code paths.
   - Without a map: each copy's guard honestly passes, and the database ends at **-1** seats.
   - With a map: the second path sees the first change and is refused.
3. **A crash between two writes.**
   - Without a unit of work: a seat is saved but its idempotency record is not, so a retry would book a second seat.
   - With a unit of work: **nothing** is written.
4. **A normal run.** The seat and the idempotency record go to the database as `BEGIN -> INSERT -> INSERT -> COMMIT`, one transaction. A retry with the same key is **replayed**, not re-booked.

## Points to notice in the code

- **Bound repositories.** `EventRepository.save()` and `IdempotencyStore.put()` keep their Section 6.1 interfaces but only **register** changes with the unit of work. The service never calls `register_*` itself, and nothing reaches the database until `commit()`.
- **Scope.** A `UnitOfWork`, and the `IdentityMap` inside it, lives for **one use case**. `test_identity_map_does_not_outlive_its_unit_of_work` checks this. Two requests never share them, which is why simultaneous requests can still overbook (Chapter 7).
- **Same-answer test.** `test_domain_and_sql_compute_the_same_seats_left` pins the domain's `seats_left` and the SQL read model to the same answer.
- **What an ORM gives you.** These classes are what an ORM session does for you. In SQLAlchemy, a `Session` *is* an identity map plus a unit of work, and `session.commit()` is `commit()` here.
