from __future__ import annotations

from dataclasses import dataclass

from . import payloads

# The planning layer. Think of `propose` as the seam where an LLM would sit: it
# takes a natural-language goal plus the menu of routes the gateway PUBLISHED,
# and returns only symbolic choices -- an existing route_id and an existing
# payload_id. It never builds a URL, sets a header, or sees the API key.
#
# The point (see docs/adr/0002): even a prompt-injected planner can do no more
# than pick items off a menu it did not write. `validate` enforces that
# invariant regardless of who produced the steps, so a real LLM can be dropped
# in later without weakening the guarantee.


@dataclass(frozen=True)
class Step:
    route_id: str
    payload_id: str | None
    reason: str


class PlanError(ValueError):
    """A proposed step referenced something outside the allowed menus."""


# Goal keyword -> ordered payload ids to try on writable (POST) routes. Every id
# here must exist in payloads.PAYLOADS; validate() re-checks at runtime.
_THEMES: dict[tuple[str, ...], list[str]] = {
    ("empty", "missing", "blank"): ["empty-string", "empty-object", "null"],
    ("type", "wrong", "coercion"): [
        "wrong-type-int",
        "wrong-type-bool",
        "wrong-type-list-for-object",
    ],
    ("boundary", "number", "numeric", "range", "overflow"): [
        "int-max",
        "int-min",
        "negative",
        "zero",
        "float-tiny",
    ],
    ("unicode", "encoding", "charset", "special"): [
        "unicode",
        "special-chars",
        "whitespace",
    ],
    ("length", "long", "size", "large"): ["long-string", "nested"],
}

# Default mix when no theme matches: one representative from each family.
_DEFAULT_PAYLOADS = ["empty-string", "wrong-type-int", "long-string", "special-chars"]


def _payloads_for_goal(goal: str) -> list[str]:
    lowered = goal.lower()
    chosen: list[str] = []
    for keywords, ids in _THEMES.items():
        if any(k in lowered for k in keywords):
            chosen.extend(ids)
    if not chosen:
        chosen = list(_DEFAULT_PAYLOADS)
    # De-duplicate while preserving order.
    seen: set[str] = set()
    return [p for p in chosen if not (p in seen or seen.add(p))]


def propose(goal: str, routes: list[dict[str, str]]) -> list[Step]:
    """Deterministically turn a goal + published routes into symbolic steps."""
    wants_timeout = any(k in goal.lower() for k in ("timeout", "slow", "resilience", "latency"))
    payload_ids = _payloads_for_goal(goal)

    steps: list[Step] = []
    for route in routes:
        rid, method = route["id"], route["method"].upper()
        if method == "GET":
            # The /slow route is only worth probing when the goal is about
            # timeouts; otherwise it just burns the gateway's deadline.
            if rid == "slow" and not wants_timeout:
                continue
            reason = "observe timeout handling" if rid == "slow" else "read-only reachability check"
            steps.append(Step(route_id=rid, payload_id=None, reason=reason))
        elif method == "POST":
            for pid in payload_ids:
                steps.append(
                    Step(route_id=rid, payload_id=pid, reason=f"exercise input handling with {pid!r}")
                )
    return steps


def validate(steps: list[Step], routes: list[dict[str, str]]) -> None:
    """Reject any step referencing an unknown route_id or payload_id.

    This is the hard boundary: no matter how the steps were produced (rules
    today, an LLM tomorrow), they may only name things that already exist.
    """
    known_routes = {r["id"] for r in routes}
    known_payloads = set(payloads.ids())
    for step in steps:
        if step.route_id not in known_routes:
            raise PlanError(f"unknown route_id: {step.route_id!r}")
        if step.payload_id is not None and step.payload_id not in known_payloads:
            raise PlanError(f"unknown payload_id: {step.payload_id!r}")
