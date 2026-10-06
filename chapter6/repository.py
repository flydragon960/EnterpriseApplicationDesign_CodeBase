# Listing 6.1 -- repository.py: persistence as an interface.
# Exercise 5.12 found three kinds of state that must survive a restart.
# Here they become three interfaces. The service layer will depend on
# these abstractions; WHICH storage stands behind them is a wiring
# decision made at startup, invisible to every layer above.
from abc import ABC, abstractmethod

class EventRepository(ABC):
    """Home of domain state: events and their reservations, loaded and
    saved as one unit (the Event is the consistency boundary)."""
    @abstractmethod
    def get(self, event_id):            # -> domain.Event | None
        ...
    @abstractmethod
    def list(self):                     # -> [domain.Event]
        ...
    @abstractmethod
    def save(self, event):              # persist the aggregate's state
        ...

class IdempotencyStore(ABC):
    """Home of the Chapter 3 promise: one attempt, one outcome."""
    @abstractmethod
    def get(self, key):                 # -> (request_hash, outcome_dict) | None
        ...
    @abstractmethod
    def put(self, key, request_hash, outcome_dict):
        ...

class IdSequence(ABC):
    """Home of identifier uniqueness: 'identifiers are forever' (Ch. 2)
    requires that no id is ever minted twice."""
    @abstractmethod
    def next(self, prefix):             # -> "res_7"
        ...
