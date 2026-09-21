# Listing 6.2 -- sqlite_repository.py: the data source layer, for real.
# Two kinds of class live here and must not be confused:
#   *Row classes are the ORM's mapped tables -- the database's shape.
#   The repositories TRANSLATE between rows and the pure domain objects
#   of Chapter 5 (this translation is Fowler's Data Mapper, and doing it
#   here is what keeps domain.py's import list empty).
import json
from sqlalchemy import (create_engine, event as sa_event, select, func,
                        String, Integer, Boolean, ForeignKey, text)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)
from domain import Event, Reservation
from repository import EventRepository, IdempotencyStore, IdSequence

class Base(DeclarativeBase):
    pass

class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    capacity: Mapped[int] = mapped_column(Integer)
    reservations: Mapped[list["ReservationRow"]] = relationship(
        back_populates="event", lazy="select")     # lazy: loaded on touch

class ReservationRow(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    event: Mapped[EventRow] = relationship(back_populates="reservations")

class IdempotencyRow(Base):
    __tablename__ = "idempotency"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    ok: Mapped[bool] = mapped_column(Boolean)
    code: Mapped[str] = mapped_column(String, nullable=True)
    value_json: Mapped[str] = mapped_column(String, nullable=True)

class CounterRow(Base):
    __tablename__ = "counters"
    name: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[int] = mapped_column(Integer)

def make_session_factory(db_path):
    engine = create_engine(f"sqlite:///{db_path}",
                           connect_args={"check_same_thread": False,
                                         "timeout": 30})
    Base.metadata.create_all(engine)
    # a visible query counter, so "the ORM leaks" can be MEASURED
    engine.query_count = 0
    @sa_event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, *a):
        engine.query_count += 1
    return sessionmaker(engine), engine

# ---------- the repositories (Data Mapper role) ----------
class SqliteEventRepository(EventRepository):
    def __init__(self, session_factory):
        self.sf = session_factory

    def _to_domain(self, row):
        e = Event(row.id, row.title, row.capacity)
        for r in row.reservations:                  # touching this MAY query
            dr = Reservation(r.id, r.event_id)
            dr.status, dr.created_at = r.status, r.created_at
            e.reservations[r.id] = dr
        return e

    def get(self, event_id):
        with self.sf() as s:
            row = s.get(EventRow, event_id)
            return self._to_domain(row) if row else None

    def list(self):
        """The naive translation: one query for events, then -- because
        _to_domain touches .reservations -- one MORE query per event.
        Chapter 1's N+1, reborn at the database boundary."""
        with self.sf() as s:
            rows = s.scalars(select(EventRow)).all()
            return [self._to_domain(r) for r in rows]

    def list_summaries(self):
        """The repaired read: seats computed IN the database, one query.
        Returns (id, title, seats_left) tuples -- a read model, not
        domain objects, because listing needs no behavior."""
        with self.sf() as s:
            confirmed = (select(ReservationRow.event_id,
                                func.count().label("n"))
                         .where(ReservationRow.status == "confirmed")
                         .group_by(ReservationRow.event_id).subquery())
            q = (select(EventRow.id, EventRow.title,
                        (EventRow.capacity -
                         func.coalesce(confirmed.c.n, 0)).label("seats_left"))
                 .outerjoin(confirmed, confirmed.c.event_id == EventRow.id))
            return [{"id": i, "title": t, "seatsLeft": sl}
                    for i, t, sl in s.execute(q).all()]

    def save(self, event):
        with self.sf() as s:
            s.merge(EventRow(id=event.id, title=event.title,
                             capacity=event.capacity))
            for r in event.reservations.values():
                s.merge(ReservationRow(id=r.id, event_id=r.event_id,
                                       status=r.status,
                                       created_at=r.created_at))
            s.commit()

class SqliteIdempotencyStore(IdempotencyStore):
    def __init__(self, session_factory):
        self.sf = session_factory

    def get(self, key):
        with self.sf() as s:
            row = s.get(IdempotencyRow, key)
            if row is None:
                return None
            value = json.loads(row.value_json) if row.value_json else None
            return row.request_hash, {"ok": row.ok, "code": row.code,
                                      "value": value}

    def put(self, key, request_hash, outcome):
        with self.sf() as s:
            s.merge(IdempotencyRow(key=key, request_hash=request_hash,
                                   ok=outcome["ok"], code=outcome["code"],
                                   value_json=json.dumps(outcome["value"])))
            s.commit()

class SqliteIdSequence(IdSequence):
    def __init__(self, session_factory):
        self.sf = session_factory
        with self.sf() as s:
            if s.get(CounterRow, "reservation") is None:
                s.add(CounterRow(name="reservation", value=0))
                s.commit()

    def next(self, prefix):
        # One statement, increment-and-read: the database performs it
        # atomically. Preview of Chapter 7: the seat check cannot be
        # rescued this way, because it spans TWO statements.
        with self.sf() as s:
            n = s.execute(text(
                "UPDATE counters SET value = value + 1 "
                "WHERE name = 'reservation' RETURNING value")).scalar_one()
            s.commit()
            return f"{prefix}_{n}"
