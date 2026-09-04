import pytest

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
