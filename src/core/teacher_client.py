"""Teacher escalation client for JEV-2 (PRD v3 stage 7 / AC-6).

The teacher repairs JEV's bounded STATE contract; it does not become the game
player. One escalation produces one typed patch, which the caller folds into
the existing JEV questions before re-asking JEV.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, TextIO

from src.core.jev_client import MISSING_CLASSES

MEMORY_CHAR_CAP = 1500
PROJECTION_CHAR_CAP = 2000
EVENT_LIMIT = 8
# Reasoning models spend completion tokens on private thinking before emitting
# JSON. 500 tokens starved 5/6 live teacher calls; 3,000 leaves bounded room for
# both reasoning and the small state-patch object.
TEACHER_MAX_TOKENS = 3000
TEACHER_REASONING_RETRY_LIMIT = 1
TEACHER_ESCALATION_EVENT = "teacher_escalation"

_REASONING_BLOCK_RE = re.compile(
    r"<(?:think|ildocthetag)\b[^>]*>.*?</(?:think|ildocthetag)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_END_MARKER_RE = re.compile(
    r"\|(?:end_of_(?:thought|turn)|eot(?:_id)?)\|",
    re.IGNORECASE,
)


@dataclass
class StatePatch:
    """Normalized teacher response; ``ok=False`` is the fail-closed sentinel."""

    ok: bool
    missing_facts: list[str] = field(default_factory=list)
    fact_source: list[str] = field(default_factory=list)
    instruction_patch: str = ""
    applies_when: str = "always"
    one_shot_action: str | None = None
    confidence: float = 0.0
    error: str | None = None
    latency_s: float = 0.0
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-safe shape consumed by the run log and re-ask."""
        return asdict(self)

    @classmethod
    def failed(cls, error: str, *, latency_s: float = 0.0) -> StatePatch:
        """Build a patch-shaped failure without raising into the game loop."""
        return cls(ok=False, error=error, latency_s=round(latency_s, 3))


def _bounded_text(value: Any, limit: int, absent: str = "(not captured)") -> str:
    if value is None:
        return absent
    text = str(value).strip()
    if not text:
        return absent
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _bounded_json(value: Any, limit: int, absent: str = "(not captured)") -> str:
    if value is None or value == [] or value == {}:
        return absent
    try:
        text = json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    return _bounded_text(text, limit, absent)


def build_teacher_prompt(
    *,
    distributions: dict[str, Any] | None,
    missing_class: str | None,
    projection: str | None,
    recent_events: list[dict[str, Any]] | None,
    milestones: list[dict[str, Any]] | None,
    memory: str | None,
) -> str:
    """Render one bounded, honest teacher request.

    Empty DuckBrain layers are explicitly ``(not captured)``. Event history is
    capped at the same eight rows as the state projection.
    """
    missing_name = missing_class if missing_class in MISSING_CLASSES else "unknown"
    missing_description = MISSING_CLASSES[missing_name]
    events = list(recent_events or [])[-EVENT_LIMIT:]
    milestone_rows = list(milestones or [])[-EVENT_LIMIT:]
    return (
        "Repair the decision STATE for a typed JEV re-ask. Do not play the game, "
        "do not return a plan array, and do not change confidence thresholds.\n\n"
        "Return ONLY one JSON object with exactly this state-patch contract:\n"
        "{\n"
        '  "missing_facts": ["facts absent from the supplied state"],\n'
        '  "fact_source": ["RAM | must-interact | memory key | mechanics rule"],\n'
        '  "instruction_patch": "applies_when: <condition>; <state heuristic>",\n'
        '  "one_shot_action": null,\n'
        '  "confidence": 0.0\n'
        "}\n"
        "instruction_patch is the primary contract. one_shot_action is optional "
        "and only for a time-critical case where state cannot be repaired first.\n\n"
        f"FAILING MISSING CLASS: {missing_name}\n"
        f"CLASS DESCRIPTION: {missing_description}\n\n"
        "JEV DISTRIBUTIONS AND SCALARS:\n"
        f"{_bounded_json(distributions, 3000)}\n\n"
        "RECENT EVENTS (last 8):\n"
        f"{_bounded_json(events, 1800)}\n\n"
        "MILESTONES (last 8):\n"
        f"{_bounded_json(milestone_rows, 1200)}\n\n"
        "MEMORY (DuckBrain):\n"
        f"{_bounded_text(memory, MEMORY_CHAR_CAP)}\n\n"
        "CURRENT PROJECTION (the exact bounded state JEV saw):\n"
        f"{_bounded_text(projection, PROJECTION_CHAR_CAP)}"
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Take the first balanced JSON object after stripping reasoning markers."""
    cleaned = _END_MARKER_RE.sub("", _REASONING_BLOCK_RE.sub("", text)).strip()
    start = cleaned.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(cleaned[start : index + 1])
                    except (json.JSONDecodeError, ValueError):
                        break
                    return parsed if isinstance(parsed, dict) else None
        start = cleaned.find("{", start + 1)
    return None


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _instruction_parts(payload: dict[str, Any]) -> tuple[str, str]:
    instruction = payload.get("instruction_patch")
    applies_when = payload.get("applies_when")
    if isinstance(instruction, dict):
        applies_when = instruction.get("applies_when", applies_when)
        instruction = instruction.get("text") or instruction.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("instruction_patch must be a non-empty string")
    text = instruction.strip()
    if not isinstance(applies_when, str) or not applies_when.strip():
        match = re.match(r"applies_when\s*:\s*([^;]+);\s*(.+)", text, re.IGNORECASE)
        if match:
            applies_when, text = match.group(1).strip(), match.group(2).strip()
        else:
            applies_when = "always"
    return text, applies_when.strip()


def _normalize_patch(
    payload: dict[str, Any], *, latency_s: float, cost_usd: float | None
) -> StatePatch:
    missing_facts = _string_list(payload.get("missing_facts"), "missing_facts")
    fact_source = _string_list(payload.get("fact_source"), "fact_source")
    instruction, applies_when = _instruction_parts(payload)
    one_shot = payload.get("one_shot_action")
    if one_shot is not None and not isinstance(one_shot, str):
        raise ValueError("one_shot_action must be a string or null")
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number from 0 to 1")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be a number from 0 to 1")
    return StatePatch(
        ok=True,
        missing_facts=missing_facts,
        fact_source=fact_source,
        instruction_patch=instruction,
        applies_when=applies_when,
        one_shot_action=one_shot.strip() if isinstance(one_shot, str) else None,
        confidence=confidence,
        latency_s=round(latency_s, 3),
        cost_usd=cost_usd,
    )


def _response_parts(
    response: Any,
) -> tuple[str | None, str | None, dict[str, Any], float | None]:
    """Normalize both client and raw provider response envelopes.

    OpenRouter/DeepSeek may expose private reasoning beside ``message.content``
    (``reasoning``/``reasoning_content``). Those fields are deliberately ignored:
    only public content can satisfy the typed patch contract.
    """
    if not isinstance(response, dict):
        return None, None, {}, None

    content = response.get("content")
    finish_reason = response.get("finish_reason")
    usage = response.get("usage")
    cost = response.get("cost_usd")

    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]
        if finish_reason is None:
            finish_reason = choice.get("finish_reason")
        message = choice.get("message")
        if isinstance(message, dict) and content is None:
            content = message.get("content")

    normalized_usage = usage if isinstance(usage, dict) else {}
    if cost is None:
        cost = normalized_usage.get("cost")
    cost_usd = float(cost) if isinstance(cost, (int, float)) else None
    return (
        content if isinstance(content, str) else None,
        finish_reason if isinstance(finish_reason, str) else None,
        normalized_usage,
        cost_usd,
    )


def request_patch(
    *,
    distributions: dict[str, Any] | None = None,
    missing_class: str | None = None,
    projection: str | None = None,
    recent_events: list[dict[str, Any]] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    memory: str | None = None,
    teacher_model: str | None = None,
    client: Any = None,
    max_tokens: int = TEACHER_MAX_TOKENS,
) -> dict[str, Any]:
    """Request and normalize one teacher patch; never raise to the caller.

    An empty length-limited response gets one bounded retry at twice the caller's
    budget. ``max_tokens`` is injectable so unit tests and probes can stay cheap.
    """
    started = time.monotonic()
    try:
        if client is None:
            raise ValueError("teacher client was not supplied")
        if not teacher_model:
            raise ValueError("teacher model was not supplied")
        if max_tokens < 1:
            raise ValueError("teacher max_tokens must be positive")
        prompt = build_teacher_prompt(
            distributions=distributions,
            missing_class=missing_class,
            projection=projection,
            recent_events=recent_events,
            milestones=milestones,
            memory=memory,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the teacher escalation layer. Repair the supplied "
                    "state contract and return typed JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        content: str | None = None
        finish_reason: str | None = None
        cost_usd: float | None = None
        budget = max_tokens
        for attempt in range(TEACHER_REASONING_RETRY_LIMIT + 1):
            response = client.chat_completion(
                model=teacher_model,
                messages=messages,
                max_tokens=budget,
                temperature=0.2,
            )
            content, finish_reason, _usage, cost_usd = _response_parts(response)
            if (content is None or not content.strip()) and finish_reason == "length":
                if attempt < TEACHER_REASONING_RETRY_LIMIT:
                    budget *= 2
                    continue
                raise ValueError(
                    "teacher token budget exhausted by reasoning tokens "
                    "(finish_reason=length)"
                )
            break

        if not isinstance(content, str) or not content.strip():
            raise ValueError("teacher response has no text content")
        payload = _extract_json(content)
        if payload is None:
            raise ValueError("teacher response contained no JSON object")
        patch = _normalize_patch(
            payload,
            latency_s=time.monotonic() - started,
            cost_usd=cost_usd,
        )
        return patch.to_dict()
    except Exception as exc:  # noqa: BLE001 - fail-closed API boundary
        return StatePatch.failed(
            str(exc), latency_s=time.monotonic() - started
        ).to_dict()


def write_escalation_row(
    log_file: TextIO,
    *,
    cycle: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Write AC-6's grep-able pre-ask / patch / post-ask proof row."""
    row = {
        "cycle": cycle,
        "event": TEACHER_ESCALATION_EVENT,
        "pre_ask": record.get("pre_ask"),
        "patch": record.get("patch"),
        "post_ask": record.get("post_ask"),
        "improved": bool(record.get("improved", False)),
        "latency_s": record.get("latency_s"),
        "cost_usd": record.get("cost_usd"),
    }
    if not record.get("ok", False):
        row["ok"] = False
        row["error"] = record.get("error")
    log_file.write(json.dumps(row, default=str) + "\n")
    log_file.flush()
    return row
