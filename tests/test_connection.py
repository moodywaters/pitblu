import pytest

from pitboss_admin.connection import (
    BackoffPolicy,
    ConnectionState,
    ConnectionStateMachine,
    DesiredState,
    InvalidTransitionError,
)


def connected_machine() -> ConnectionStateMachine:
    machine = ConnectionStateMachine(backoff=BackoffPolicy(random_value=lambda: 0.5))
    machine.discovered()
    machine.request_connect()
    machine.transition(ConnectionState.INITIALISING)
    machine.transition(ConnectionState.CONNECTED)
    machine.transition(ConnectionState.POLLING)
    return machine


def test_complete_connection_and_recovery_flow() -> None:
    machine = connected_machine()
    assert machine.desired is DesiredState.CONNECTED
    assert machine.observed is ConnectionState.POLLING

    delay = machine.unexpected_disconnect()
    assert delay == 2
    assert machine.desired is DesiredState.CONNECTED
    assert machine.observed.value == "backoff"
    assert machine.request_connect(force=True)
    assert machine.observed.value == "connecting"


def test_disconnect_is_idempotent_and_cancels_recovery() -> None:
    machine = connected_machine()
    assert machine.request_disconnect()
    assert machine.desired is DesiredState.DISCONNECTED
    assert machine.observed is ConnectionState.DISCONNECTED
    assert not machine.request_disconnect()
    assert machine.unexpected_disconnect() is None


def test_repeated_connect_is_idempotent() -> None:
    machine = connected_machine()
    assert not machine.request_connect()
    assert machine.observed is ConnectionState.POLLING


def test_unsupported_and_invalid_transitions() -> None:
    machine = ConnectionStateMachine()
    machine.discovered(supported=False)
    assert machine.observed is ConnectionState.UNSUPPORTED
    assert not machine.transition(ConnectionState.UNSUPPORTED)
    with pytest.raises(InvalidTransitionError):
        machine.transition(ConnectionState.POLLING)


def test_backoff_schedule_cap_jitter_and_reset() -> None:
    middle = BackoffPolicy(delays=(2, 4), random_value=lambda: 0.5)
    assert [middle.next_delay() for _ in range(3)] == [2, 4, 4]
    middle.reset()
    assert middle.attempt == 0
    assert middle.next_delay() == 2
    assert BackoffPolicy(delays=(10,), random_value=lambda: 0).next_delay() == 8
    assert BackoffPolicy(delays=(10,), random_value=lambda: 1).next_delay() == 12


@pytest.mark.parametrize(
    "kwargs",
    [
        {"delays": ()},
        {"delays": (0,)},
        {"jitter_fraction": -0.1},
        {"jitter_fraction": 1.1},
    ],
)
def test_backoff_rejects_invalid_configuration(kwargs: object) -> None:
    with pytest.raises(ValueError):
        BackoffPolicy(**kwargs)  # type: ignore[arg-type]


def test_stable_connection_resets_backoff() -> None:
    machine = connected_machine()
    assert machine.unexpected_disconnect() == 2
    machine.stable()
    assert machine.backoff.attempt == 0
