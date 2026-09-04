"""Explicit desired and observed per-device connection state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from random import Random


class DesiredState(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class ConnectionState(StrEnum):
    DISCOVERED = "discovered"
    CONNECTING = "connecting"
    INITIALISING = "initialising"
    CONNECTED = "connected"
    POLLING = "polling"
    DEGRADED = "degraded"
    BACKOFF = "backoff"
    DISCONNECTED = "disconnected"
    UNSUPPORTED = "unsupported"


class InvalidTransitionError(RuntimeError):
    """The requested observed-state transition is not legal."""


_ALLOWED: dict[ConnectionState, frozenset[ConnectionState]] = {
    ConnectionState.DISCOVERED: frozenset(
        {ConnectionState.CONNECTING, ConnectionState.DISCONNECTED, ConnectionState.UNSUPPORTED}
    ),
    ConnectionState.CONNECTING: frozenset(
        {ConnectionState.INITIALISING, ConnectionState.BACKOFF, ConnectionState.DISCONNECTED}
    ),
    ConnectionState.INITIALISING: frozenset(
        {
            ConnectionState.CONNECTED,
            ConnectionState.BACKOFF,
            ConnectionState.DISCONNECTED,
            ConnectionState.UNSUPPORTED,
        }
    ),
    ConnectionState.CONNECTED: frozenset(
        {
            ConnectionState.POLLING,
            ConnectionState.DEGRADED,
            ConnectionState.BACKOFF,
            ConnectionState.DISCONNECTED,
        }
    ),
    ConnectionState.POLLING: frozenset(
        {ConnectionState.DEGRADED, ConnectionState.BACKOFF, ConnectionState.DISCONNECTED}
    ),
    ConnectionState.DEGRADED: frozenset(
        {ConnectionState.POLLING, ConnectionState.BACKOFF, ConnectionState.DISCONNECTED}
    ),
    ConnectionState.BACKOFF: frozenset({ConnectionState.CONNECTING, ConnectionState.DISCONNECTED}),
    ConnectionState.DISCONNECTED: frozenset(
        {ConnectionState.DISCOVERED, ConnectionState.CONNECTING, ConnectionState.UNSUPPORTED}
    ),
    ConnectionState.UNSUPPORTED: frozenset({ConnectionState.DISCONNECTED}),
}


@dataclass(slots=True)
class BackoffPolicy:
    delays: tuple[float, ...] = (2, 4, 8, 15, 30, 60)
    jitter_fraction: float = 0.2
    random_value: Callable[[], float] = field(default_factory=lambda: Random().random)
    _attempt: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if not self.delays or any(delay <= 0 for delay in self.delays):
            raise ValueError("backoff delays must be positive")
        if not 0 <= self.jitter_fraction <= 1:
            raise ValueError("jitter fraction must be between 0 and 1")

    @property
    def attempt(self) -> int:
        return self._attempt

    def next_delay(self) -> float:
        base = self.delays[min(self._attempt, len(self.delays) - 1)]
        self._attempt += 1
        factor = 1 + ((self.random_value() * 2) - 1) * self.jitter_fraction
        return base * factor

    def reset(self) -> None:
        self._attempt = 0


@dataclass(slots=True)
class ConnectionStateMachine:
    desired: DesiredState = DesiredState.DISCONNECTED
    observed: ConnectionState = ConnectionState.DISCONNECTED
    backoff: BackoffPolicy = field(default_factory=BackoffPolicy)

    def transition(self, new_state: ConnectionState) -> bool:
        if new_state is self.observed:
            return False
        if new_state not in _ALLOWED[self.observed]:
            raise InvalidTransitionError(f"cannot transition {self.observed} to {new_state}")
        self.observed = new_state
        return True

    def discovered(self, *, supported: bool = True) -> None:
        self.transition(ConnectionState.DISCOVERED if supported else ConnectionState.UNSUPPORTED)

    def request_connect(self, *, force: bool = False) -> bool:
        changed = self.desired is not DesiredState.CONNECTED
        self.desired = DesiredState.CONNECTED
        if self.observed is ConnectionState.BACKOFF and force:
            self.transition(ConnectionState.CONNECTING)
            return True
        if self.observed in {ConnectionState.DISCOVERED, ConnectionState.DISCONNECTED}:
            self.transition(ConnectionState.CONNECTING)
            return True
        return changed

    def request_disconnect(self) -> bool:
        changed = self.desired is not DesiredState.DISCONNECTED
        self.desired = DesiredState.DISCONNECTED
        if self.observed is not ConnectionState.DISCONNECTED:
            self.transition(ConnectionState.DISCONNECTED)
            changed = True
        self.backoff.reset()
        return changed

    def unexpected_disconnect(self) -> float | None:
        if self.desired is DesiredState.DISCONNECTED:
            if self.observed is not ConnectionState.DISCONNECTED:
                self.transition(ConnectionState.DISCONNECTED)
            return None
        self.transition(ConnectionState.BACKOFF)
        return self.backoff.next_delay()

    def stable(self) -> None:
        self.backoff.reset()
