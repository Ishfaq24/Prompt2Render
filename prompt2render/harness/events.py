"""Minimal synchronous in-process event bus.

Core harness events:

    stage.started
    stage.failed
    check.failed
    repair.triggered

``runner.py`` emits the first three. ``repair_router`` subscribes to
``check.failed`` and emits ``repair.triggered``.

The bus deliberately remains synchronous and in-process. It provides
deterministic event ordering without introducing an async runtime or external
message broker.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


EventHandler = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    """Immutable event delivered to subscribers."""

    type: str
    payload: dict[str, Any] = field(
        default_factory=dict
    )


class EventBus:
    """Synchronous, deterministic event dispatcher."""

    #: The complete harness event vocabulary. ``repair_router`` emits
    #: ``repair.started``/``repair.finished`` around every repair cycle;
    #: these were historically absent here, so each emit raised
    #: ``ValueError`` straight into the router's exception handler and no
    #: repair lifecycle event was ever delivered to anyone. Subscribing to
    #: them failed for the same reason.
    VALID_EVENTS = frozenset(
        {
            "stage.started",
            "stage.failed",
            "check.failed",
            "repair.triggered",
            "repair.started",
            "repair.finished",
        }
    )

    def __init__(
        self,
        *,
        strict: bool = True,
    ) -> None:
        self._subs: dict[
            str,
            list[EventHandler],
        ] = defaultdict(list)

        self.strict = strict

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Register a handler.

        Duplicate subscriptions are ignored so the same plugin cannot
        accidentally receive the same event twice.
        """

        self._validate_event_type(
            event_type
        )

        if not callable(
            handler
        ):
            raise TypeError(
                "handler must be callable"
            )

        handlers = self._subs[
            event_type
        ]

        if handler not in handlers:
            handlers.append(
                handler
            )

    def unsubscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> bool:
        """Remove a handler.

        Returns ``True`` when a subscription was removed.
        """

        handlers = self._subs.get(
            event_type
        )

        if not handlers:
            return False

        try:
            handlers.remove(
                handler
            )
        except ValueError:
            return False

        if not handlers:
            self._subs.pop(
                event_type,
                None,
            )

        return True

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def emit(
        self,
        event_type: str,
        **payload: Any,
    ) -> Event:
        """Synchronously dispatch one event.

        Subscribers are called in registration order.

        A snapshot of the subscriber list is used so a handler may safely
        subscribe/unsubscribe another handler while the current event is
        being dispatched.
        """

        self._validate_event_type(
            event_type
        )

        event = Event(
            type=event_type,
            payload=dict(
                payload
            ),
        )

        handlers = tuple(
            self._subs.get(
                event_type,
                (),
            )
        )

        for handler in handlers:
            try:
                handler(
                    event
                )
            except Exception:
                if self.strict:
                    raise

        return event

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def subscribers(
        self,
        event_type: str,
    ) -> tuple[EventHandler, ...]:
        """Return a stable snapshot of current subscribers."""

        self._validate_event_type(
            event_type
        )

        return tuple(
            self._subs.get(
                event_type,
                (),
            )
        )

    def clear(
        self,
        event_type: str | None = None,
    ) -> None:
        """Remove subscribers for one event or for all events."""

        if event_type is None:
            self._subs.clear()
            return

        self._validate_event_type(
            event_type
        )

        self._subs.pop(
            event_type,
            None,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_event_type(
        self,
        event_type: str,
    ) -> None:
        if not isinstance(
            event_type,
            str,
        ) or not event_type.strip():
            raise ValueError(
                "event_type must be a non-empty string"
            )

        if (
            self.strict
            and event_type
            not in self.VALID_EVENTS
        ):
            raise ValueError(
                f"Unknown harness event: "
                f"{event_type!r}. "
                f"Expected one of: "
                f"{sorted(self.VALID_EVENTS)}"
            )


__all__ = [
    "Event",
    "EventBus",
    "EventHandler",
]