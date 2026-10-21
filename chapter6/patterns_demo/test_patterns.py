# test_patterns.py -- the claims on the slides, pinned down as tests.
# Run with either:   python3 test_patterns.py      or      pytest -q
from schema import fresh_db, SoldOut
from four_patterns import PATTERNS, EventMapper, seats_left as sql_seats_left
from uow_identity_map import (UnitOfWork, reserve, reserve_without_uow,
                              count_rows, selects)


# ---------- the four architectural patterns: same behaviour ----------------
def test_four_patterns_agree_on_the_rule():
    for name, reserve_fn in PATTERNS:
        conn = fresh_db()
        reserve_fn(conn, "ev_103", "res_1")
        reserve_fn(conn, "ev_103", "res_2")
        try:
            reserve_fn(conn, "ev_103", "res_3")
            assert False, f"{name}: third reservation should be SOLD OUT"
        except SoldOut:
            pass
        assert sql_seats_left(conn, "ev_103") == 0, name


def test_domain_and_sql_compute_the_same_seats_left():
    """One rule, two computations (domain object vs read-model SQL):
    pin them to the same answer so they can never drift."""
    conn = fresh_db()
    PATTERNS[3][1](conn, "ev_101", "res_1")          # Data Mapper path
    domain_answer = EventMapper(conn).find("ev_101").seats_left
    assert domain_answer == sql_seats_left(conn, "ev_101") == 41


# ---------- identity map ----------------------------------------------------
def test_identity_map_returns_the_same_object_without_sql():
    trace = []
    conn = fresh_db(trace)
    uow = UnitOfWork(conn)
    a = uow.events.get("ev_101")
    before = selects(trace)
    b = uow.events.get("ev_101")
    assert a is b                                    # identity, not equality
    assert selects(trace) == before                  # second get: zero SQL


def test_without_identity_map_two_copies_overbook_in_one_request():
    conn = fresh_db()
    reserve(conn, "ev_103", "k0", "res_0")           # 1 seat left
    first = EventMapper(conn).find("ev_103"); first.reserve("res_1")
    second = EventMapper(conn).find("ev_103"); second.reserve("res_2")
    with conn:
        EventMapper(conn).save(first); EventMapper(conn).save(second)
    assert sql_seats_left(conn, "ev_103") == -1      # the bug, documented


def test_with_identity_map_the_second_path_sees_the_first_change():
    conn = fresh_db()
    reserve(conn, "ev_103", "k0", "res_0")           # 1 seat left
    uow = UnitOfWork(conn)
    uow.events.get("ev_103").reserve("res_1")
    try:
        uow.events.get("ev_103").reserve("res_2")
        assert False, "second path should be refused"
    except SoldOut:
        pass


def test_identity_map_does_not_outlive_its_unit_of_work():
    conn = fresh_db()
    a = UnitOfWork(conn).events.get("ev_101")
    b = UnitOfWork(conn).events.get("ev_101")
    assert a is not b                                # each request: its own map


# ---------- unit of work ----------------------------------------------------
def test_without_uow_a_crash_leaves_a_seat_with_no_replay_record():
    conn = fresh_db()
    try:
        reserve_without_uow(conn, "ev_101", "key-A", "res_1", crash_between=True)
    except RuntimeError:
        pass
    assert count_rows(conn, "reservations") == 1
    assert count_rows(conn, "idempotency") == 0      # half-written: the bug


def test_with_uow_a_crash_before_commit_writes_nothing():
    conn = fresh_db()
    try:
        reserve(conn, "ev_101", "key-A", "res_1", crash_before_commit=True)
    except RuntimeError:
        pass
    assert count_rows(conn, "reservations") == 0
    assert count_rows(conn, "idempotency") == 0


def test_with_uow_seat_and_replay_record_commit_in_one_transaction():
    trace = []
    conn = fresh_db(trace)
    reserve(conn, "ev_101", "key-B", "res_7")
    kinds = [s.split()[0].upper() for s in trace
             if s.split()[0].upper() in ("BEGIN", "INSERT", "COMMIT")]
    assert kinds == ["BEGIN", "INSERT", "INSERT", "COMMIT"]


def test_retry_with_same_key_is_replayed_not_rebooked():
    conn = fresh_db()
    assert reserve(conn, "ev_101", "key-C", "res_1") == "res_1"
    assert reserve(conn, "ev_101", "key-C", "res_2") == "res_1 (replayed)"
    assert count_rows(conn, "reservations") == 1


# ---------- a minimal runner, so pytest is optional -------------------------
if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL  {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
