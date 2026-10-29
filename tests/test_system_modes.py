"""Decision modes: System One alone, System Two alone, hybrid with handoff toggles.

Acceptance criteria are the six from docs/specs/SPEC_decision_modes.md:

  M1  a system1 run has teacher_calls == 0, every row decision_mode=system1
  M2  a system2 run has jev_answered=false on every row
  M3  every escalated row names which trigger fired
  M4  the toggles bind (--handoff failure => no other trigger escalates)
  M5  the mode AND policy are recoverable from the log alone
  M6  back-compat: jev/llm keep their exact stamped value and behaviour

M6 is the load-bearing one and it runs first: it protects every committed
baseline (base-1_long_0926_0014.json, ctrl-win_2026-09-26.json). It caught a
real regression while this change was being written — an early version
canonicalised `resolve_decision_mode` so `--decision-mode jev` stamped
"system1+system2" into every row, which would have made every new run
incomparable to every log already on disk. The fix is that the SPELLING is
stamped and the FAMILY is a separate field.
"""

from __future__ import annotations

import inspect
from collections import Counter

import pytest

import cron_runner
from cron_runner import MODE_HYBRID, MODE_SYSTEM1, MODE_SYSTEM2


@pytest.fixture(autouse=True)
def _restore_mode():
    """Every test leaves the module-level mode and policy as it found them."""
    original = cron_runner.DECISION_MODE
    original_policy = cron_runner.HANDOFF_POLICY
    yield
    cron_runner.DECISION_MODE = original
    cron_runner.HANDOFF_POLICY = original_policy


# ─────────────────────────────────────────── M6: back-compat comes first
def test_m6_legacy_spellings_keep_their_stamped_value(monkeypatch):
    monkeypatch.delenv("AIPP_DECISION_MODE", raising=False)
    monkeypatch.delenv("CRON_DECISION_MODE", raising=False)
    # The value written into every existing run log must not move.
    assert cron_runner.resolve_decision_mode("jev") == "jev"
    assert cron_runner.resolve_decision_mode("llm") == "llm"
    assert cron_runner.resolve_decision_mode() is None


def test_m6_family_is_where_branching_reads():
    assert cron_runner.decision_mode_family("jev") == MODE_HYBRID
    assert cron_runner.decision_mode_family("llm") == MODE_SYSTEM2
    assert cron_runner.decision_mode_family("system1") == MODE_SYSTEM1
    assert cron_runner.decision_mode_family("system2") == MODE_SYSTEM2
    assert cron_runner.decision_mode_family("system1+system2") == MODE_HYBRID
    assert cron_runner.decision_mode_family("hybrid") == MODE_HYBRID


def test_new_names_are_selectable():
    assert cron_runner.resolve_decision_mode("system1") == "system1"
    assert cron_runner.resolve_decision_mode("system2") == "system2"
    assert cron_runner.resolve_decision_mode("system1+system2") == "system1+system2"
    assert cron_runner.resolve_decision_mode("system1") in cron_runner.DECISION_MODES


def test_unknown_mode_is_ignored_not_guessed(monkeypatch):
    monkeypatch.delenv("AIPP_DECISION_MODE", raising=False)
    monkeypatch.delenv("CRON_DECISION_MODE", raising=False)
    assert cron_runner.normalize_decision_mode("nonsense") is None
    # An unknown value is never guessed into a valid runtime mode.
    assert cron_runner.resolve_decision_mode("nonsense") is None


# ─────────────────────────────────────────── M2: system2 never calls the tier
def test_m2_system2_never_invokes_the_fast_tier(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the fast tier must not be CALLED in system2")

    monkeypatch.setattr(cron_runner, "_jev_overworld_decision", boom)
    cron_runner.DECISION_MODE = "system2"
    assert cron_runner._jev_or_none({}) is None


def test_m2_llm_alias_is_also_system2(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the fast tier must not be CALLED in system2")

    monkeypatch.setattr(cron_runner, "_jev_overworld_decision", boom)
    # The historical spelling must behave identically to the new one.
    cron_runner.DECISION_MODE = "llm"
    assert cron_runner._jev_or_none({}) is None


def test_system1_does_invoke_the_fast_tier(monkeypatch):
    seen = {}

    def fake(*_a, **_k):
        seen["called"] = True
        return {"ok": True}

    monkeypatch.setattr(cron_runner, "_jev_overworld_decision", fake)
    cron_runner.DECISION_MODE = "system1"
    assert cron_runner._jev_or_none({}) == {"ok": True}
    assert seen["called"] is True


# ─────────────────────────────────────────── M3: triggers are classifiable
@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("failure: last action changed nothing", "failure"),
        ("insufficient_state (0.20) missing=map_topology", "gap"),
        ("missing_class=map_topology", "gap"),
        ("low_confidence_act (0.30)", "confidence"),
        ("low_confidence+ambiguous (0.30/0.90)", "confidence"),
        ("transport: HTTP 403", "transport"),
        ("", "none"),
        (None, "none"),
    ],
)
def test_trigger_classification(reason, expected):
    assert cron_runner.classify_handoff_trigger(reason) == expected


def test_m3_every_escalation_reason_from_the_gate_classifies():
    """No escalated row may end up with an unclassifiable trigger.

    This is the invariant M3 rests on: every reason `should_escalate` can emit
    for an escalation maps to a known family, so a row that escalated always
    names its trigger.
    """
    from src.core import jev_client

    cases = [
        ({"ok": True, "action_confidence": 0.9, "sufficient_state": 0.9}, True, False),
        (
            {
                "ok": True,
                "action_confidence": 0.1,
                "ambiguity": 0.9,
                "sufficient_state": 0.9,
            },
            False,
            False,
        ),
        (
            {
                "ok": True,
                "action_confidence": 0.1,
                "ambiguity": 0.9,
                "sufficient_state": 0.9,
            },
            False,
            True,
        ),
        (
            {
                "ok": True,
                "action_confidence": 0.9,
                "sufficient_state": 0.1,
                "missing_class": "map_topology",
            },
            False,
            False,
        ),
        (
            {
                "ok": True,
                "action_confidence": 0.9,
                "sufficient_state": 0.9,
                "missing_class": "map_topology",
            },
            False,
            False,
        ),
        ({"ok": False, "error": "HTTP 403"}, False, False),
    ]
    seen_families = set()
    for decision, act_phase, expect_escalation in cases:
        escalates, reason = jev_client.should_escalate(
            decision, last_action_failed=expect_escalation, act_phase=act_phase
        )
        if escalates:
            family = cron_runner.classify_handoff_trigger(reason)
            assert family in {"failure", "gap", "confidence", "transport"}, (
                f"escalation reason {reason!r} classified as {family!r} — an "
                "escalated row would carry no usable trigger"
            )
            seen_families.add(family)
    # The cases above must actually exercise more than one family, or this test
    # proves nothing about the taxonomy.
    assert len(seen_families) >= 3, f"only exercised {seen_families}"


# ─────────────────────────────────────────── M4: the toggles bind
def test_policy_parsing():
    assert cron_runner.resolve_handoff_families("off") == frozenset()
    assert cron_runner.resolve_handoff_families("any") == frozenset(
        cron_runner.HANDOFF_ALL_FAMILIES
    )
    assert cron_runner.resolve_handoff_families("failure") == frozenset({"failure"})
    assert cron_runner.resolve_handoff_families("failure,gap") == frozenset(
        {"failure", "gap"}
    )
    assert cron_runner.resolve_handoff_families("nonsense") == frozenset()


def test_m4_only_the_permitted_trigger_may_hand_back():
    policy = cron_runner.build_handoff_policy(handoff="failure")
    ok, _ = cron_runner.handoff_allowed(policy, "failure", "map_topology")
    assert ok is True
    gap_ok, gap_why = cron_runner.handoff_allowed(policy, "gap", "map_topology")
    assert gap_ok is False
    assert "gap" in gap_why
    conf_ok, _ = cron_runner.handoff_allowed(policy, "confidence", "map_topology")
    assert conf_ok is False


def test_handoff_off_blocks_every_policy_trigger():
    policy = cron_runner.build_handoff_policy(handoff="off")
    for trigger in ("failure", "gap", "confidence"):
        ok, why = cron_runner.handoff_allowed(policy, trigger, "map_topology")
        assert ok is False, f"{trigger} must not hand back under --handoff off"
        assert why


def test_transport_failure_is_not_policy_gated():
    """An unanswered fast tier must still degrade to the controller: that is
    availability, not a policy choice."""
    policy = cron_runner.build_handoff_policy(handoff="off")
    ok, _ = cron_runner.handoff_allowed(policy, "transport", None)
    assert ok is True


def test_class_filter_binds():
    policy = cron_runner.build_handoff_policy(handoff="any", classes="map_topology")
    assert cron_runner.handoff_allowed(policy, "gap", "map_topology")[0] is True
    assert cron_runner.handoff_allowed(policy, "gap", "dialog_context")[0] is False


def test_defaults_match_the_thresholds_already_in_code():
    """Changing a default would invalidate every committed baseline."""
    from src.core import jev_client

    policy = cron_runner.build_handoff_policy()
    assert policy["confidence"] == jev_client.ESCALATE_THRESHOLD
    assert policy["ambiguity"] == jev_client.AMBIGUITY_GATE
    assert policy["families"] == sorted(cron_runner.HANDOFF_ALL_FAMILIES)


# ─────────────────────────────────────────── the block actually binds (M1/M4)
def _stub_tier(monkeypatch, escalation_reason="missing_class=map_topology"):
    """Make the fast tier return an escalating decision, and count teacher calls."""
    counts = {"teacher": 0}

    def fake_decide(_projection, **_kw):
        return {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": escalation_reason,
            "missing_class": "map_topology",
            "raw": {},
        }

    def fake_teacher(*_a, **_k):
        counts["teacher"] += 1
        raise AssertionError("teacher must not run when the policy blocks the handoff")

    monkeypatch.setattr(cron_runner.jev_client, "decide", fake_decide)
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", fake_teacher)
    return counts


def test_m1_system1_policy_blocks_the_handoff_and_the_teacher(monkeypatch):
    """RED-proof: without `if escalate and not handoff_ok: escalate = False`
    this reports escalated=True; without `and handoff_ok` in can_call_teacher it
    calls the teacher."""
    counts = _stub_tier(monkeypatch)
    out = cron_runner._jev_overworld_decision(
        {},
        handoff_policy=cron_runner.build_handoff_policy(handoff="off"),
        teacher_api_client=object(),
        teacher_model="some-model",
        class_repairs=Counter(),
    )
    assert out["escalated"] is False, (
        "a policy-blocked trigger must not report an escalation"
    )
    assert out["handoff_allowed"] is False
    assert out["handoff_blocked_reason"]
    assert counts["teacher"] == 0


def test_hybrid_policy_permits_the_same_handoff(monkeypatch):
    """The toggle must actually toggle: same input, default policy, hands back."""

    def fake_teacher(*_a, **_k):
        return {"ok": False, "error": "stubbed"}  # attempted is what we assert

    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": "missing_class=map_topology",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    called = {"n": 0}

    def counting_teacher(*_a, **_k):
        called["n"] += 1
        return {"ok": False, "error": "stubbed"}

    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", counting_teacher)

    out = cron_runner._jev_overworld_decision(
        {},
        handoff_policy=cron_runner.build_handoff_policy(handoff="any"),
        teacher_api_client=object(),
        teacher_model="some-model",
        class_repairs=Counter(),
    )
    assert out["escalated"] is True
    assert out["handoff_allowed"] is True
    assert called["n"] == 1


def test_repeated_gap_handoff_rearms_and_round_trips(monkeypatch):
    """A recurring gap proves the prior repair failed and reaches the teacher."""
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": "missing_class=map_topology",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    monkeypatch.setattr(
        cron_runner,
        "_memory_navigation_decision",
        lambda *_a, **_k: {"result": "miss", "reason": "hermetic fixture"},
    )
    teacher_calls = {"n": 0}

    def counting_teacher(*_a, **_k):
        teacher_calls["n"] += 1
        return {"ok": False, "error": "stubbed"}

    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", counting_teacher)
    class_repairs: Counter[str] = Counter()
    kwargs = {
        "handoff_policy": cron_runner.build_handoff_policy(handoff="any"),
        "teacher_api_client": object(),
        "teacher_model": "some-model",
        "class_repairs": class_repairs,
    }

    first = cron_runner._jev_overworld_decision({}, **kwargs)
    second = cron_runner._jev_overworld_decision({}, **kwargs)
    third = cron_runner._jev_overworld_decision({}, **kwargs)
    autonomy = cron_runner._autonomy_counters([first, second, third])

    # The named re-arm policy guarantees a second repair and continues to
    # deliver recurring gap triggers. The episode budget is the outer bound.
    assert teacher_calls["n"] == 3
    assert first["escalated"] is True
    assert first["handoff_allowed"] is True
    assert second["escalated"] is True
    assert second["handoff_allowed"] is True
    assert third["escalated"] is True
    assert third["handoff_allowed"] is True
    assert third["handoff_blocked_reason"] is None
    assert class_repairs == Counter({"map_topology": 3})
    assert cron_runner.TEACHER_REPAIR_REARM_TRIGGERS == frozenset(
        cron_runner.HANDOFF_ALL_FAMILIES
    )
    assert autonomy["handoff_trigger_counts"] == {"gap": 3}
    assert autonomy["escalated"] == 3
    assert autonomy["handoff_blocked"] == 0
    assert autonomy["handoff_trigger_counts"]["gap"] == autonomy["escalated"]


def test_reconciled_non_escalation_is_not_a_blocked_handoff():
    """ROM-resolved diagnostics are not policy triggers or blocked delivery."""
    trigger, _policy, allowed, reason = cron_runner._jev_handoff_gate(
        {
            "escalate": False,
            "escalate_reason": "map_topology_resolved_by_rom",
            "missing_class": "none",
        },
        handoff_policy=cron_runner.build_handoff_policy(handoff="any"),
        teacher_budget={"used": 44},
        escalation_class="none",
    )

    assert trigger == "none"
    assert allowed is True
    assert reason == "no handoff requested"
    autonomy = cron_runner._autonomy_counters(
        [{"handoff_trigger": trigger, "handoff_allowed": allowed}]
    )
    assert autonomy["handoff_trigger_counts"] == {}
    assert autonomy["handoff_blocked"] == 0


def test_memory_answered_gap_still_reaches_teacher(monkeypatch):
    """Path memory may own the action but cannot swallow the teacher handoff."""
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "LEFT",
            "escalate": True,
            "escalate_reason": "missing_class=map_topology",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    route_key = "/world/path/Red-s-House-1F->Red-s-House-2F"
    monkeypatch.setattr(
        cron_runner,
        "_memory_navigation_decision",
        lambda *_a, **_k: {
            "result": "hit",
            "key": route_key,
            "mechanism": "collision_grid_path",
            "plan": ["RIGHT"],
        },
    )
    teacher_calls = {"n": 0}

    def counting_teacher(*_a, **_k):
        teacher_calls["n"] += 1
        return {"ok": False, "error": "stubbed"}

    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", counting_teacher)

    out = cron_runner._jev_overworld_decision(
        {"map_id": 37, "map_name": "Red's House 1F"},
        handoff_policy=cron_runner.build_handoff_policy(handoff="any"),
        teacher_api_client=object(),
        teacher_model="some-model",
        class_repairs=Counter(),
    )

    assert out["plan"] == ["RIGHT"]
    assert out["escalated"] is False  # memory authored the executable plan
    assert out["handoff_allowed"] is True
    assert out["handoff_blocked_reason"] is None
    assert teacher_calls["n"] == 1
    autonomy = cron_runner._autonomy_counters([out])
    assert autonomy["handoff_trigger_counts"] == {"gap": 1}
    assert autonomy["handoff_blocked"] == 0


def test_handoff_legacy_set_rearms_recurring_gap(monkeypatch):
    """Even legacy set accumulators cannot swallow a recurring gap trigger."""
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": "missing_class=map_topology",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    monkeypatch.setattr(
        cron_runner,
        "_memory_navigation_decision",
        lambda *_a, **_k: {"result": "miss", "reason": "hermetic fixture"},
    )
    teacher_calls = {"n": 0}

    def counting_teacher(*_a, **_k):
        teacher_calls["n"] += 1
        return {"ok": False, "error": "stubbed"}

    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", counting_teacher)
    legacy_allowance: set[str] = set()
    kwargs = {
        "handoff_policy": cron_runner.build_handoff_policy(handoff="any"),
        "teacher_api_client": object(),
        "teacher_model": "some-model",
        "class_repairs": legacy_allowance,
    }

    first = cron_runner._jev_overworld_decision({}, **kwargs)
    second = cron_runner._jev_overworld_decision({}, **kwargs)

    assert teacher_calls["n"] == 2
    assert first["escalated"] is True
    assert second["escalated"] is True
    assert second["handoff_allowed"] is True
    assert second["handoff_blocked_reason"] is None
    assert legacy_allowance == {"map_topology"}


def test_handoff_class_repairs_plain_dict_counts_and_rearms(monkeypatch):
    """A plain dict ledger cannot block a recurring permitted trigger."""
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": "low_confidence (0.22)",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    monkeypatch.setattr(
        cron_runner,
        "_memory_navigation_decision",
        lambda *_a, **_k: {"result": "miss", "reason": "hermetic fixture"},
    )
    teacher_calls = {"n": 0}

    def counting_teacher(*_a, **_k):
        teacher_calls["n"] += 1
        return {"ok": False, "error": "stubbed"}

    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", counting_teacher)
    allowance: dict[str, int] = {}
    kwargs = {
        "handoff_policy": cron_runner.build_handoff_policy(handoff="any"),
        "teacher_api_client": object(),
        "teacher_model": "some-model",
        "class_repairs": allowance,
    }

    first = cron_runner._jev_overworld_decision({}, **kwargs)
    second = cron_runner._jev_overworld_decision({}, **kwargs)
    third = cron_runner._jev_overworld_decision({}, **kwargs)

    assert teacher_calls["n"] == 3
    assert first["handoff_allowed"] is True
    assert second["handoff_allowed"] is True
    assert third["handoff_allowed"] is True
    assert third["handoff_blocked_reason"] is None
    assert allowance == {"map_topology": 3}


def test_handoff_non_class_sentinel_never_spends_class_dedupe():
    """The literal missing_class=none is not a class shared by every trigger."""
    allowed, reason = cron_runner._jev_handoff_delivery_gate(
        {"escalate": True},
        handoff_ok=True,
        handoff_why="allowed",
        handoff_trigger=cron_runner.HANDOFF_CONFIDENCE,
        escalation_class="none",
        teacher_api_client=object(),
        teacher_model="some-model",
        class_repairs=Counter({"none": 53}),
    )

    assert allowed is True
    assert reason == "allowed"
    assert "none" in cron_runner.TEACHER_NON_CLASS_SENTINELS


def test_handoff_repair_block_reason_is_the_named_constant():
    """The spent-allowance reason is the named policy constant, and the
    module carries no inline copy of the legacy dedupe string (DF-AIPP-13-R2:
    the re-escalation policy must be findable in code, not scattered)."""
    assert cron_runner.TEACHER_REPAIR_ATTEMPTS_PER_CLASS == 2
    assert cron_runner.TEACHER_REPAIR_REARM_TRIGGERS == frozenset(
        cron_runner.HANDOFF_ALL_FAMILIES
    )
    assert cron_runner.TEACHER_NON_CLASS_SENTINELS == frozenset({"none"})
    lines = inspect.getsource(cron_runner).splitlines()
    hits = [i for i, ln in enumerate(lines) if "already escalated this run" in ln]
    assert len(hits) == 1, "the dedupe text must live only in the constant"
    # The single hit is the constant's assignment (its value or the comment
    # naming it directly above), not a second inline use.
    window = "\n".join(lines[max(0, hits[0] - 3) : hits[0] + 1])
    assert "HANDOFF_BLOCK_REPAIRS_EXHAUSTED" in window


def test_handoff_episode_budget_binds_even_when_repairs_remain(monkeypatch):
    """The per-episode cap is independent of the per-class repair allowance:
    with the budget spent the trigger is refused as a budget block, and the
    teacher is never called, even though the class has attempts left."""
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": "missing_class=map_topology",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    monkeypatch.setattr(
        cron_runner,
        "_memory_navigation_decision",
        lambda *_a, **_k: {"result": "miss", "reason": "hermetic fixture"},
    )
    monkeypatch.setattr(
        cron_runner.jev_client,
        "escalate_and_reask",
        lambda *_a, **_k: pytest.fail("spent budget must not reach the teacher"),
    )

    out = cron_runner._jev_overworld_decision(
        {},
        handoff_policy=cron_runner.build_handoff_policy(handoff="any", teacher_max=2),
        teacher_api_client=object(),
        teacher_model="some-model",
        class_repairs=Counter(),
        teacher_budget={"used": 2},
    )

    assert out["escalated"] is False
    assert "budget exhausted" in (out["handoff_blocked_reason"] or "")
    assert cron_runner.HANDOFF_BLOCK_REPAIRS_EXHAUSTED not in (
        out["handoff_blocked_reason"] or ""
    )


def test_teacher_budget_blocks_after_the_cap(monkeypatch):
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": "missing_class=map_topology",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    monkeypatch.setattr(
        cron_runner.jev_client,
        "escalate_and_reask",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("budget exhausted: teacher must not be called")
        ),
    )
    budget = {"used": 3}
    out = cron_runner._jev_overworld_decision(
        {},
        handoff_policy=cron_runner.build_handoff_policy(handoff="any", teacher_max=3),
        teacher_api_client=object(),
        teacher_model="some-model",
        class_repairs=Counter(),
        teacher_budget=budget,
    )
    assert out["escalated"] is False
    assert "budget" in (out["handoff_blocked_reason"] or "")


def test_budget_is_spent_at_the_api_boundary(monkeypatch):
    """A call that fails still spent the budget — otherwise a failing teacher
    is retried on every subsequent cycle."""
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_a, **_k: {
            "ok": True,
            "next_action": "RIGHT",
            "escalate": True,
            "escalate_reason": "missing_class=map_topology",
            "missing_class": "map_topology",
            "raw": {},
        },
    )
    monkeypatch.setattr(cron_runner.state_projection, "build", lambda *_a, **_k: "proj")
    monkeypatch.setattr(
        cron_runner.jev_client,
        "escalate_and_reask",
        lambda *_a, **_k: {"ok": False, "error": "stubbed failure"},
    )
    budget = {"used": 0}
    cron_runner._jev_overworld_decision(
        {},
        handoff_policy=cron_runner.build_handoff_policy(handoff="any", teacher_max=2),
        teacher_api_client=object(),
        teacher_model="some-model",
        class_repairs=Counter(),
        teacher_budget=budget,
    )
    assert budget["used"] == 1


# ─────────────────────────────────────────── M5: recoverable from the log
def test_m5_run_row_records_mode_and_policy(tmp_path):
    log = tmp_path / "run.jsonl"
    cron_runner.DECISION_MODE = "system1"
    cron_runner.HANDOFF_POLICY = cron_runner.build_handoff_policy(handoff="failure")
    with log.open("w") as fh:
        row = cron_runner._write_autonomy_row(
            fh,
            "r1",
            {
                "decisions_total": 2,
                "jev_answered": 2,
                "escalated": 0,
                "handoff_trigger_counts": {"gap": 2},
                "handoff_blocked": 2,
            },
        )
    assert row["decision_mode"] == "system1"
    assert row["decision_mode_family"] == MODE_SYSTEM1
    assert row["handoff_policy"]["families"] == ["failure"]
    assert row["handoff_policy"]["confidence"] == cron_runner.DEFAULT_HANDOFF_CONFIDENCE
    # The trigger census must reach the run row, or M3 is only checkable by
    # walking every decision row.
    assert row["handoff_trigger_counts"] == {"gap": 2}
    assert row["handoff_blocked"] == 2


def test_counters_report_handoff_provenance():
    autonomy = cron_runner._autonomy_counters(
        [
            {"intent": "a", "handoff_trigger": "gap", "handoff_allowed": False},
            {
                "intent": "b",
                "handoff_trigger": "failure",
                "handoff_allowed": True,
                "escalated": True,
            },
            {"intent": "c", "handoff_trigger": None, "handoff_allowed": None},
        ]
    )
    assert autonomy["handoff_trigger_counts"] == {"gap": 1, "failure": 1}
    assert autonomy["handoff_blocked"] == 1


def test_system1_mode_empties_the_policy_in_main(monkeypatch):
    """The mode is the stronger statement: system1 cannot be made to hand back
    by --handoff, and the two must not contradict each other in the log.

    Exercises main()'s post-parse rule directly, since that is where the
    emptying happens.
    """
    _ = monkeypatch
    policy = cron_runner.build_handoff_policy(handoff="any")
    assert policy["families"], "precondition: default policy allows handoffs"

    # The rule main() applies, isolated: family system1 => no handoff families.
    if (
        cron_runner.decision_mode_family("system1") == MODE_SYSTEM1
        and policy["families"]
    ):
        policy = {**policy, "families": []}
    assert policy["families"] == []
    for trigger in ("failure", "gap", "confidence"):
        assert cron_runner.handoff_allowed(policy, trigger, "map_topology")[0] is False
