"""A minimal synchronous in-process event bus.

Four event types per the brief: stage.started, stage.failed, check.failed, repair.triggered.
`runner.py` emits the first three; `repair_router` (Stage 4) subscribes to check.failed and emits
repair.triggered itself.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Event:
    type: str
    payload: dict = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._subs[event_type].append(handler)

    def emit(self, event_type: str, **payload) -> None:
        ev = Event(type=event_type, payload=payload)
        for handler in self._subs.get(event_type, []):
            handler(ev)
