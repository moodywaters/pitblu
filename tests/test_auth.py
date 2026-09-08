import pytest

from pitboss_admin import auth
from pitboss_admin.auth import AdministratorTokens
from pitboss_admin.storage import AdministrativeStore


def test_bootstrap_verify_and_rotate_return_plaintext_once() -> None:
    store = AdministrativeStore()
    tokens = AdministratorTokens(store)
    assert not tokens.status().configured

    first = tokens.bootstrap()
    assert tokens.verify(first)
    assert tokens.status().configured
    assert tokens.status().changed_at is not None
    with pytest.raises(RuntimeError, match="already configured"):
        tokens.bootstrap()

    replacement = tokens.rotate()
    assert replacement != first
    assert not tokens.verify(first)
    assert tokens.verify(replacement)
    assert "replacement" not in repr(store.auth_record())
    store.close()


def test_malformed_tokens_are_rejected_without_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    store = AdministrativeStore()
    tokens = AdministratorTokens(store)
    tokens.bootstrap()

    def forbidden(*args: object) -> bytes:
        raise AssertionError("malformed input reached expensive hashing")

    monkeypatch.setattr(auth, "_digest", forbidden)
    for token in ("", "x" * 100000, "☃" * 43, "short", "=" * 43):
        assert not tokens.verify(token)
    store.close()
