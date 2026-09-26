"""Jev decision client for ai-plays-poke (System One).

Design borrowed from how Jev is used in real-time game loops (TypeSafe's Doom
demo: structured state in, typed decisions out, ~10 q/s) and from the
confidence-gated Jev/LLM pattern (JevLoop): *escalate decisions, not text*, and
let the failure of the last action force arbitration regardless of confidence.

This module is deliberately the FAST half only. It never calls an LLM. Its job
is to (a) answer the per-cycle action question cheaply, and (b) SELF-REPORT when
it does not have enough state to decide — so the reasoning LLM can repair the
state instead of playing the game.

Three Jev primitives used:
  noul   -> probability a statement is true  (sufficiency, ambiguity, confidence)
  choice -> pick one of a known set          (next action, phase, missing class)
  score  -> ordered rubric position          (progress toward goal)

Cost shape: ONE request answers every question (~$0.00005), 300-600ms.
Fail-closed: any transport error or malformed answer -> escalate, never guess.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from copy import deepcopy
from typing import Any

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"

# Escalation thresholds. Live in CODE, never in the model (JevLoop's rule), so
# they can be tuned against measurement without touching the questions.
ESCALATE_THRESHOLD = 0.50  # action confidence floor
AMBIGUITY_GATE = 0.40  # low confidence alone is not enough (layered gate)
SUFFICIENCY_FLOOR = 0.50  # Jev says "I lack the state to decide" below this
PROGRESS_FLOOR = 1.0  # score 0..3; below this = not making progress

BUTTONS = ["UP", "DOWN", "LEFT", "RIGHT", "A", "B", "START", "WAIT"]

MISSING_CLASSES = {
    "none": "the state is complete for this decision",
    "map_topology": "which tiles are walkable / where the exits and objects are",
    "object_purpose": "what a visible object or NPC does when interacted with",
    "quest_state": "what the current objective is and whether it is already done",
    "inventory": "what items the player holds and what they are for",
    "party_state": "the party's Pokemon, levels, HP and moves",
    "dialog_context": "what the on-screen text box is asking for",
    "mechanics": "how a game mechanic works (menus, battle flow, saving)",
    "battle_moves": "which battle moves are available and what they do",
    "unknown": "the gap cannot be classified from the state given",
}


def _questions(*, in_battle: bool = False) -> dict[str, Any]:
    """Build the batched question set.

    In battle the ACTION VOCABULARY changes: the choice is between the party's
    moves, not between overworld buttons. A button-only vocabulary cannot answer
    a battle turn, which the first live probe exposed.
    """
    if in_battle:
        action_q = {
            "type": "choice",
            "instructions": (
                "Choose this turn's battle action. Weigh the opponent's type and "
                "the available moves; a super-effective move is usually best, and "
                "keep enough PP for the rest of the fight. An incorrect pick is "
                "costly, so this decision keeps the full confidence net."
            ),
            "criteria": {
                "MOVE_1": "use move 1 (see MOVES in the state)",
                "MOVE_2": "use move 2",
                "MOVE_3": "use move 3",
                "MOVE_4": "use move 4",
                "SWITCH": "switch to another party member",
                "ITEM": "use a healing/status item",
                "RUN": "attempt to flee the battle",
            },
        }
    else:
        action_q = {
            "type": "choice",
            "instructions": (
                "Choose the single next button press most likely to make real "
                "progress toward the goal. Prefer an action that produces a state "
                "change over repeating a move that just failed. To interact with "
                "an object the player must face it and press A."
            ),
            "criteria": {
                "UP": "walk up one tile (blocked if a wall or object is above)",
                "DOWN": "walk down one tile",
                "LEFT": "walk left one tile",
                "RIGHT": "walk right one tile",
                "A": "interact with / talk to / read whatever the player faces",
                "B": "cancel or decline a prompt",
                "START": "open the pause menu",
                "WAIT": "do nothing this cycle; let the game settle",
            },
        }

    return {
        "next_action": action_q,
        "phase": {
            "type": "choice",
            "instructions": "Classify what the game is currently asking of the player.",
            "criteria": {
                "EXPLORE": "free movement toward a known or unknown destination",
                "INTERACT": "must press A on a specific object/NPC to progress",
                "DIALOG": "a text box is open and needs advancing",
                "MENU": "a menu is open and an option must be selected",
                "BATTLE": "a battle is active and a move must be chosen",
                "STUCK": "repeated actions are producing no state change",
                "GOAL": "the objective appears already complete; pick the next one",
            },
        },
        "sufficient_state": {
            "type": "noul",
            "instructions": (
                "Is there ENOUGH information in this state to choose the best "
                "action with confidence? Answer false when the state is missing "
                "facts the decision depends on."
            ),
        },
        "missing_class": {
            "type": "choice",
            "instructions": (
                "If information is missing, which CLASS of information is the "
                "blocker? Choose 'none' when nothing needed is missing."
            ),
            "criteria": MISSING_CLASSES,
        },
        "action_confidence": {
            "type": "noul",
            "instructions": (
                "Is next_action clearly the best action, with no other choice "
                "nearly as likely to advance the goal?"
            ),
        },
        "ambiguity": {
            "type": "noul",
            "instructions": (
                "Is this decision contested — i.e. do several actions look "
                "similarly reasonable from this state?"
            ),
        },
        "progress": {
            "type": "score",
            "instructions": (
                "How much progress did the last few actions make toward the goal?"
            ),
            "criteria": [
                "b0 no progress at all; repeated actions, nothing changed",
                "b1 slight progress; wandered but learned something",
                "b2 clear progress; a new area, object or milestone reached",
                "b3 major progress; a goal completed or a new objective unlocked",
            ],
        },
    }


def starter_questions(*, visible_species: str | None) -> dict[str, Any]:
    """Build the starter-specific choice vocabulary for Oak's three balls."""
    questions = _questions(in_battle=False)
    visible = visible_species or "unknown"
    questions["next_action"] = {
        "type": "choice",
        "instructions": (
            "Choose the starter species. The currently visible confirmation "
            f"dialog names {visible}; movement to another ball is handled after "
            "this species decision."
        ),
        "criteria": {
            "CHARMANDER": "choose the left ball containing the Fire-type starter",
            "SQUIRTLE": "choose the middle ball containing the Water-type starter",
            "BULBASAUR": "choose the right ball containing the Grass-type starter",
        },
    }
    questions["phase"] = {
        "type": "choice",
        "instructions": "Classify this irreversible Oak's Lab starter choice.",
        "criteria": {"STARTER": "choose one of Oak's three starter Pokemon"},
    }
    return questions


# ── key handling ────────────────────────────────────────────────────────────


def _read_env(path: str, names: tuple[str, ...]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k in names and v:
                    out.append((k, v))
    except OSError:
        pass
    return out


def load_keys() -> list[tuple[str, str]]:
    """Project key first (dedicated), then the shared Jev key. Values never logged."""
    keys: list[tuple[str, str]] = []
    for path, names in (
        ("/home/kara/ai_plays_poke/.env", ("OPENROUTER_API_KEY",)),
        (os.path.expanduser("~/.hermes/.env"), ("OR_JEV", "OPENROUTER_API_KEY")),
    ):
        for k, v in _read_env(path, names):
            if (k, v) not in keys:
                keys.append((k, v))
    return keys


# ── the ask ─────────────────────────────────────────────────────────────────


def ask(
    state: str,
    *,
    in_battle: bool = False,
    timeout: int = 45,
    questions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send one batched decision request. Returns a normalized dict.

    On any failure returns {"ok": False, "error": ...} — callers must escalate.
    ``questions`` is additive for JEV-2: the normal path still uses the canonical
    set, while a teacher re-ask can supply a copied set with one instruction patch.
    """
    keys = load_keys()
    if not keys:
        return {"ok": False, "error": "no key available"}

    body = json.dumps(
        {
            "model": MODEL,
            "state": state,
            "questions": questions
            if questions is not None
            else _questions(in_battle=in_battle),
        }
    ).encode()
    last_err = "unknown"
    for name, key in keys:
        req = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last_err = f"{name}: HTTP {e.code} {e.read().decode()[:120]}"
            continue
        except Exception as e:  # noqa: BLE001
            last_err = f"{name}: {e}"
            continue

        ans = payload.get("answers") or {}
        if not ans:
            last_err = f"{name}: empty answers"
            continue

        usage = payload.get("usage") or {}
        return {
            "ok": True,
            "key_name": name,
            "model_build": payload.get("model"),
            "latency_s": round(time.time() - t0, 2),
            "cost_usd": usage.get("cost"),
            "answers": ans,
            "next_action": (ans.get("next_action") or {}).get("choice"),
            "phase": (ans.get("phase") or {}).get("choice"),
            "action_confidence": (ans.get("action_confidence") or {}).get("noul"),
            "sufficient_state": (ans.get("sufficient_state") or {}).get("noul"),
            "ambiguity": (ans.get("ambiguity") or {}).get("noul"),
            "missing_class": (ans.get("missing_class") or {}).get("choice"),
            "progress": (ans.get("progress") or {}).get("score"),
            "raw": ans,
        }
    return {"ok": False, "error": last_err}


def preflight(*, timeout: int = 15) -> dict[str, Any]:
    """Probe the real decisions endpoint once and classify startup safety.

    The request uses one minimal typed question through :func:`ask`, so it
    exercises the same key loading, endpoint, authorization header and response
    decoder as gameplay. Authentication failures are fatal to a JEV-mode run;
    network/provider failures are transient and may continue with a warning.
    """
    result = ask(
        "JEV startup preflight. Choose READY.",
        timeout=timeout,
        questions={
            "preflight": {
                "type": "choice",
                "instructions": "Confirm the decisions endpoint can answer.",
                "criteria": {"READY": "the endpoint accepted this request"},
            }
        },
    )
    if result.get("ok"):
        return {
            "status": "pass",
            "ok": True,
            "key_name": result.get("key_name"),
        }

    error = str(result.get("error", "unknown preflight failure"))[:200]
    key_name = error.partition(":")[0] if ":" in error else None
    status = (
        "auth_failure" if re.search(r"\bHTTP (?:401|403)\b", error) else "transient"
    )
    return {
        "status": status,
        "ok": False,
        "key_name": key_name,
        "error": error,
    }


# ── the gate: does Jev hand back to the reasoning LLM? ──────────────────────


def should_escalate(
    decision: dict[str, Any],
    *,
    last_action_failed: bool = False,
    act_phase: bool = False,
) -> tuple[bool, str]:
    """Decide whether to hand back to the reasoning LLM.

    Three independent triggers (any one is sufficient):
      1. FAILURE  — the last action produced no state change. Confidence is
         irrelevant: a blocked/stuck action must be arbitrated (this is the
         trigger that would have caught the frozen-dialog loop).
      2. SELF-REPORTED GAP — Jev says the state is insufficient, or names a
         missing information class. Jev is deciding to hand back.
      3. LAYERED GATE — low action confidence AND high ambiguity agree. For
         irreversible phases (battle move, menu commit) low confidence alone
         suffices, because a wrong unambiguous-looking pick is costly.
    """
    if not decision.get("ok"):
        return True, f"transport: {decision.get('error')}"

    if last_action_failed:
        return True, "failure: last action changed nothing"

    conf = decision.get("action_confidence")
    suff = decision.get("sufficient_state")
    amb = decision.get("ambiguity")
    miss = decision.get("missing_class")

    if suff is not None and suff < SUFFICIENCY_FLOOR:
        return True, f"insufficient_state ({suff:.2f}) missing={miss}"

    if miss and miss != "none" and (suff is None or suff < 0.8):
        return True, f"missing_class={miss}"

    if conf is not None and conf < ESCALATE_THRESHOLD:
        if act_phase:
            return True, f"low_confidence_act ({conf:.2f})"
        if amb is None or amb > AMBIGUITY_GATE:
            return True, f"low_confidence+ambiguous ({conf:.2f}/{amb})"

    return False, "jev_confident"


def apply_patch(
    base_questions: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """Fold a teacher heuristic into only ``next_action.instructions``.

    The input and all non-target questions remain unchanged. Escalation thresholds
    stay in code and no new JEV question type is introduced.
    """
    questions = deepcopy(base_questions)
    next_action = questions.get("next_action")
    if not isinstance(next_action, dict):
        return questions
    instruction = patch.get("instruction_patch")
    if not isinstance(instruction, str) or not instruction.strip():
        return questions
    applies_when = patch.get("applies_when")
    if not isinstance(applies_when, str) or not applies_when.strip():
        applies_when = "always"
    current = next_action.get("instructions")
    current_text = current if isinstance(current, str) else ""
    addition = (
        "Additional instruction (from a previous escalation, applies_when: "
        f"{applies_when.strip()}): {instruction.strip()}"
    )
    next_action["instructions"] = f"{current_text}\n\n{addition}".strip()
    return questions


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _sum_optional(*values: Any) -> float | None:
    numbers = [number for value in values if (number := _number(value)) is not None]
    return round(sum(numbers), 8) if numbers else None


def escalate_and_reask(
    decision: dict[str, Any],
    *,
    projection: str,
    memory: str | None = None,
    recent_events: list[dict[str, Any]] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    teacher_model: str | None = None,
    client: Any = None,
    in_battle: bool = False,
    last_action_failed: bool = False,
    act_phase: bool = False,
    max_reasks: int = 1,
    base_questions: dict[str, Any] | None = None,
    log_file: Any = None,
    cycle: int | None = None,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ask the teacher for one state patch, apply it, and return control to JEV.

    The returned record is the exact AC-6 proof triple. Every failure is data:
    ``ok=False`` and ``improved=False`` let the game loop survive and escalate on
    a later cycle. This function never performs more than ``max_reasks`` calls.
    """
    from src.core import teacher_client

    started = time.monotonic()
    pre_reason = decision.get("escalate_reason")
    if not isinstance(pre_reason, str):
        _, pre_reason = should_escalate(
            decision,
            last_action_failed=last_action_failed,
            act_phase=act_phase,
        )
    pre_ask = {
        "sufficient_state": decision.get("sufficient_state"),
        "missing_class": decision.get("missing_class"),
        "escalate_reason": pre_reason,
    }
    record: dict[str, Any] = {
        "ok": False,
        "pre_ask": pre_ask,
        "patch": None,
        "post_ask": None,
        "improved": False,
        "latency_s": 0.0,
        "cost_usd": None,
    }

    def finish() -> dict[str, Any]:
        if log_file is not None:
            row = teacher_client.write_escalation_row(
                log_file,
                cycle=cycle if cycle is not None else 0,
                record=record,
            )
            if results is not None:
                results.append(row)
        return record

    if max_reasks < 1:
        record["error"] = "max_reasks must allow one re-ask"
        return finish()

    patch = teacher_client.request_patch(
        distributions=decision,
        missing_class=(
            decision.get("missing_class")
            if isinstance(decision.get("missing_class"), str)
            else "unknown"
        ),
        projection=projection,
        recent_events=recent_events,
        milestones=milestones,
        memory=memory,
        teacher_model=teacher_model,
        client=client,
    )
    record["patch"] = patch
    if not patch.get("ok"):
        record["error"] = patch.get("error", "teacher patch failed")
        record["latency_s"] = round(time.monotonic() - started, 3)
        record["cost_usd"] = patch.get("cost_usd")
        return finish()

    questions = apply_patch(
        base_questions
        if base_questions is not None
        else _questions(in_battle=in_battle),
        patch,
    )
    post_ask = ask(projection, in_battle=in_battle, questions=questions)
    record["post_ask"] = post_ask
    record["latency_s"] = round(time.monotonic() - started, 3)
    record["cost_usd"] = _sum_optional(patch.get("cost_usd"), post_ask.get("cost_usd"))
    if not post_ask.get("ok"):
        record["error"] = post_ask.get("error", "JEV re-ask failed")
        return finish()

    escalates, reason = should_escalate(
        post_ask,
        last_action_failed=last_action_failed,
        act_phase=act_phase,
    )
    post_ask["escalate"] = escalates
    post_ask["escalate_reason"] = reason

    pre_suff = _number(decision.get("sufficient_state"))
    post_suff = _number(post_ask.get("sufficient_state"))
    pre_missing = decision.get("missing_class")
    post_missing = post_ask.get("missing_class")
    missing_narrowed = post_missing == "none" or (
        isinstance(post_missing, str)
        and post_missing in MISSING_CLASSES
        and post_missing != pre_missing
    )
    record["ok"] = True
    record["improved"] = bool(
        pre_suff is not None
        and post_suff is not None
        and post_suff >= pre_suff
        and missing_narrowed
    )
    return finish()


def decide(
    state: str,
    *,
    in_battle: bool = False,
    last_action_failed: bool = False,
    act_phase: bool = False,
    questions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full cycle: ask Jev, then apply the gate. No LLM is called here."""
    d = ask(state, in_battle=in_battle, questions=questions)
    esc, why = should_escalate(
        d, last_action_failed=last_action_failed, act_phase=act_phase
    )
    d["escalate"] = esc
    d["escalate_reason"] = why
    return d
