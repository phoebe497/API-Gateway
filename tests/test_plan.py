from __future__ import annotations

import pytest

from safe_probe import payloads, plan

ROUTES = [
    {"id": "health", "method": "GET", "path": "/health"},
    {"id": "items-list", "method": "GET", "path": "/api/items"},
    {"id": "slow", "method": "GET", "path": "/slow"},
    {"id": "echo", "method": "POST", "path": "/echo"},
    {"id": "login", "method": "POST", "path": "/login"},
]


def test_propose_only_references_known_ids() -> None:
    steps = plan.propose("input validation", ROUTES)
    known_routes = {r["id"] for r in ROUTES}
    known_payloads = set(payloads.ids())
    for step in steps:
        assert step.route_id in known_routes
        assert step.payload_id is None or step.payload_id in known_payloads
    # validate() must accept a self-produced plan.
    plan.validate(steps, ROUTES)


def test_slow_route_only_probed_for_timeout_goals() -> None:
    normal = plan.propose("input validation", ROUTES)
    assert all(s.route_id != "slow" for s in normal)

    timeout = plan.propose("check timeout resilience", ROUTES)
    assert any(s.route_id == "slow" for s in timeout)


def test_theme_selection_picks_boundary_payloads() -> None:
    steps = plan.propose("numeric boundary overflow", ROUTES)
    used = {s.payload_id for s in steps if s.payload_id}
    assert {"int-max", "int-min"} <= used


def test_validate_rejects_unknown_route() -> None:
    bad = [plan.Step(route_id="__evil__", payload_id=None, reason="x")]
    with pytest.raises(plan.PlanError):
        plan.validate(bad, ROUTES)


def test_validate_rejects_unknown_payload() -> None:
    bad = [plan.Step(route_id="echo", payload_id="__evil__", reason="x")]
    with pytest.raises(plan.PlanError):
        plan.validate(bad, ROUTES)
