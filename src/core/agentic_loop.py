"""Bounded opt-in agentic controller loop for the live Pokémon harness.

The default JEV path does not import or invoke this loop.  The live runner calls
it only for the explicit ``agentic`` decision mode, keeping benchmark history
comparable while providing real model-chosen, verified tools.
"""

from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.core.tools import parse_tool_call


_ALLOWED_ACTIONS = frozenset(
    {"UP", "DOWN", "LEFT", "RIGHT", "A", "B", "START", "SELECT"}
)
_PUBLIC_PROJECTION_FIELDS = frozenset(
    {
        "result",
        "screen_type",
        "map_id",
        "map_name",
        "player_tile_x",
        "player_tile_y",
        "player_facing",
        "text_content",
        "text_lines",
        "visible_exits",
        "adjacent",
    }
)


@dataclass(frozen=True)
class AgenticCaps:
    """All cost/growth limits for one agentic cycle and delegated call."""

    max_tool_calls: int = 2
    prompt_chars: int = 6_000
    tool_result_chars: int = 900
    delegate_wall_seconds: float = 8.0
    delegate_tool_calls: int = 1
    delegate_cost_usd: float = 0.003
    finding_chars: int = 800
    source_count: int = 3
    public_context_chars: int = 1_500


@dataclass
class BoundedAgentContext:
    """Rolling turns plus a compact summary of turns that left the window."""

    max_turns: int = 12
    summary_chars: int = 1_200
    block_chars: int = 4_000
    turns: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    delegated_findings: list[str] = field(default_factory=list)

    @staticmethod
    def _compact(value: Any, limit: int = 180) -> str:
        text = " ".join(str(value if value not in (None, "") else "none").split())
        return text[:limit]

    def _summarize(self, turn: dict[str, Any]) -> None:
        facts = "; ".join(turn.get("text_facts", [])) or "none"
        line = (
            f"cycle {turn['cycle']}: decision={turn['decision']}; "
            f"action={turn['action']}; result={turn['result']}; text={facts}"
        )
        combined = f"{self.summary}\n{line}".strip()
        self.summary = combined[-self.summary_chars :]

    def record(
        self,
        *,
        cycle: int,
        decision: Any,
        action: Any,
        result: Any,
        text_facts: list[Any] | None = None,
    ) -> dict[str, Any]:
        turn = {
            "cycle": int(cycle),
            "decision": self._compact(decision),
            "action": self._compact(action),
            "result": self._compact(result),
            "text_facts": [self._compact(fact, 120) for fact in (text_facts or [])[:3]],
        }
        self.turns.append(turn)
        while len(self.turns) > max(1, self.max_turns):
            self._summarize(self.turns.pop(0))
        return turn

    def inject_finding(self, finding: str) -> None:
        text = self._compact(finding, 400)
        if text and text not in self.delegated_findings:
            self.delegated_findings.append(text)
            del self.delegated_findings[:-4]

    def render(self) -> str:
        sections: list[str] = []
        if self.summary:
            sections.append(f"EARLIER TURN SUMMARY (capped):\n{self.summary}")
        if self.turns:
            lines = ["ROLLING PRIOR TURNS (bounded):"]
            for turn in self.turns:
                facts = "; ".join(turn["text_facts"]) or "none"
                lines.append(
                    f"- cycle {turn['cycle']} | decision={turn['decision']} | "
                    f"action={turn['action']} | result={turn['result']} | text={facts}"
                )
            sections.append("\n".join(lines))
        if self.delegated_findings:
            sections.append(
                "DELEGATED FINDINGS (persisted):\n"
                + "\n".join(f"- {item}" for item in self.delegated_findings)
            )
        return "\n\n".join(sections)[-self.block_chars :]

    def evidence(self) -> dict[str, Any]:
        block = self.render()
        return {
            "window_turns": len(self.turns),
            "window_cap": self.max_turns,
            "summary_chars": len(self.summary),
            "summary_cap": self.summary_chars,
            "context_chars": len(block),
            "context_cap": self.block_chars,
            "delegated_findings": len(self.delegated_findings),
        }


class AgentMemory(Protocol):
    def remember_finding(self, record: dict[str, Any]) -> str: ...

    def recall(
        self,
        *,
        key: str | None = None,
        labels: list[str] | None = None,
        query: str | None = None,
        limit: int = 4,
    ) -> list[dict[str, Any]]: ...


@dataclass
class InMemoryAgentMemory:
    """Deterministic local adapter used by tests and offline harnesses."""

    records: list[dict[str, Any]] = field(default_factory=list)

    def remember_finding(self, record: dict[str, Any]) -> str:
        stored = dict(record)
        stored.setdefault("id", f"local-{len(self.records) + 1}")
        self.records.append(stored)
        return str(stored["id"])

    def recall(
        self,
        *,
        key: str | None = None,
        labels: list[str] | None = None,
        query: str | None = None,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        matches = self.records
        if key:
            matches = [record for record in matches if record.get("key") == key]
        if labels:
            matches = [
                record
                for record in matches
                if all(label in record.get("labels", []) for label in labels)
            ]
        if query:
            needle = query.lower()
            matches = [
                record for record in matches if needle in json.dumps(record).lower()
            ]
        return [dict(record) for record in matches[-max(1, min(limit, 4)) :]]


class DuckBrainAgentMemory:
    """Adapter over the repository's restart-durable DuckBrain abstraction."""

    def __init__(self, namespace: str = "pokemon-global") -> None:
        self.namespace = namespace

    def remember_finding(self, record: dict[str, Any]) -> str:
        from src.core import duckbrain_client

        return duckbrain_client.remember(
            key=str(record["key"]),
            domain=str(record["domain"]),
            attributes={"finding": record["finding"], "sources": record["sources"]},
            embedding_text=str(record["finding"]),
            namespace=self.namespace,
            labels=list(record.get("labels", [])),
            confidence=float(record["confidence"]),
            evidence=dict(record.get("evidence", {})),
            applies_when=dict(record.get("applies_when", {})),
        )

    def recall(
        self,
        *,
        key: str | None = None,
        labels: list[str] | None = None,
        query: str | None = None,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        from src.core import duckbrain_client

        bounded_limit = max(1, min(int(limit), 4))
        if query:
            return duckbrain_client.search(
                query, namespace=self.namespace, limit=bounded_limit
            )
        return duckbrain_client.recall(
            key=key,
            labels=labels,
            namespace=self.namespace,
            limit=bounded_limit,
        )


class ResearchDelegate(Protocol):
    def research(
        self,
        *,
        question: str,
        public_context: dict[str, Any],
        caps: AgenticCaps,
    ) -> dict[str, Any]: ...


class ModelResearchDelegate:
    """One-call research worker with a hard caller-visible wall-clock bound.

    No tools or ambient context are passed.  The daemon worker receives only the
    declared public context.  If the provider outlives the wall cap the parent
    immediately receives a timeout failure; at most one provider request exists.
    """

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def research(
        self,
        *,
        question: str,
        public_context: dict[str, Any],
        caps: AgenticCaps,
    ) -> dict[str, Any]:
        if caps.delegate_tool_calls < 1 or caps.delegate_cost_usd <= 0:
            raise RuntimeError("delegation budget does not permit a research call")
        prompt = (
            "Answer one bounded public-game research question. No tools, private "
            "data, credentials, or follow-up calls. Return JSON with finding, "
            "sources (public source names only), and confidence (0..1).\n"
            f"QUESTION: {question}\nPUBLIC CONTEXT: "
            f"{json.dumps(public_context, ensure_ascii=False)}"
        )
        # Derive the one-call token ceiling from the repository's public sticker
        # prices. Byte length is a conservative token upper bound for UTF-8 model
        # inputs, so the admitted request cannot exceed the declared dollar cap.
        from src.core.ai_client import get_model_pricing

        input_price, output_price = get_model_pricing(self.model)
        input_token_ceiling = len(prompt.encode("utf-8"))
        input_cost_ceiling = input_token_ceiling * input_price / 1_000_000
        remaining_cost = caps.delegate_cost_usd - input_cost_ceiling
        if remaining_cost <= 0:
            raise RuntimeError("delegation input exceeds cost cap")
        max_tokens = min(240, int(remaining_cost * 1_000_000 / output_price))
        if max_tokens < 1:
            raise RuntimeError("delegation cost cap leaves no output budget")
        cost_ceiling = input_cost_ceiling + max_tokens * output_price / 1_000_000
        output: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def _call() -> None:
            try:
                response = self.client.chat_completion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=0.1,
                    thinking={"type": "disabled"},
                )
                output.put((True, response))
            except Exception as exc:  # provider error is returned to the parent model
                output.put((False, exc))

        started = time.monotonic()
        worker = threading.Thread(target=_call, daemon=True, name="agentic-research")
        worker.start()
        worker.join(max(0.01, caps.delegate_wall_seconds))
        elapsed = time.monotonic() - started
        if worker.is_alive():
            raise TimeoutError(
                f"delegation exceeded wall-clock cap {caps.delegate_wall_seconds:.2f}s"
            )
        ok, value = output.get_nowait()
        if not ok:
            raise RuntimeError(f"delegation provider failed: {value}")
        raw = value.get("content", "") if isinstance(value, dict) else ""
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("delegation returned invalid JSON") from exc
        if not isinstance(parsed, dict) or not str(parsed.get("finding", "")).strip():
            raise RuntimeError("delegation returned no finding")
        return {
            "finding": str(parsed["finding"]),
            "sources": parsed.get("sources", []),
            "confidence": parsed.get("confidence", 0.0),
            "cost_usd": cost_ceiling,
            "tool_calls": 1,
            "elapsed_s": elapsed,
        }


AGENTIC_TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "walk",
            "description": "Walk 1-3 tiles and verify that map/tile position changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                    },
                    "tiles": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["direction", "tiles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "interact",
            "description": "Press A once and verify text, screen, map, or tile state changed.",
            "parameters": {
                "type": "object",
                "properties": {"target": {"type": "string", "maxLength": 80}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_dialogue",
            "description": "Read current dialogue text without pressing a button.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Recall durable game memory by exact key, labels, or text query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "maxLength": 160},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 80},
                        "maxItems": 3,
                    },
                    "query": {"type": "string", "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 4},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_research",
            "description": (
                "Ask one bounded research worker a public game-mechanics question. "
                "The finding is persisted and added to later-cycle context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "minLength": 3, "maxLength": 300}
                },
                "required": ["question"],
            },
        },
    },
]


@dataclass(frozen=True)
class AgenticCycleResult:
    decision: dict[str, Any]
    events: list[dict[str, Any]]
    context_evidence: dict[str, Any]


def _public_context(projection: dict[str, Any], cap: int) -> dict[str, Any]:
    public = {
        key: projection[key]
        for key in _PUBLIC_PROJECTION_FIELDS
        if key in projection and projection[key] not in (None, "", [])
    }
    # Normalize the two screen spellings into one explicit public field.
    public["screen"] = public.pop("result", public.pop("screen_type", "unknown"))
    if "text_content" in public or "text_lines" in public:
        public["text"] = public.pop("text_content", public.pop("text_lines", []))
    encoded = json.dumps(public, ensure_ascii=False)
    if len(encoded) <= cap:
        return public
    return {"screen": public.get("screen", "unknown"), "summary": encoded[:cap]}


def _position(observation: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        observation.get("map_id"),
        observation.get("player_tile_x"),
        observation.get("player_tile_y"),
    )


def _state_signature(observation: dict[str, Any]) -> tuple[Any, ...]:
    return (
        observation.get("result") or observation.get("screen_type"),
        observation.get("map_id"),
        observation.get("player_tile_x"),
        observation.get("player_tile_y"),
        tuple(observation.get("text_content") or observation.get("text_lines") or []),
    )


def _tool_result(
    *,
    name: str,
    arguments: dict[str, Any],
    emulator: Any,
    observe: Any,
    memory: AgentMemory,
    delegate: ResearchDelegate | None,
    context: BoundedAgentContext,
    projection: dict[str, Any],
    caps: AgenticCaps,
    cycle: int,
) -> tuple[bool, bool, str, bool]:
    """Return ``ok, verified, result, is_delegation`` for one safe tool."""
    try:
        if name == "walk":
            direction = str(arguments.get("direction", "")).lower()
            tiles = arguments.get("tiles")
            if direction not in {"up", "down", "left", "right"}:
                return (
                    False,
                    False,
                    f"Error: invalid walk direction {direction!r}",
                    False,
                )
            if not isinstance(tiles, int) or not 1 <= tiles <= 3:
                return (
                    False,
                    False,
                    "Error: walk tiles must be an integer in 1..3",
                    False,
                )
            before = observe()
            before_pos = _position(before)
            for _ in range(tiles):
                emulator.press_button(direction, frames=5)
                emulator.fast_forward(15)
            after = observe()
            after_pos = _position(after)
            if None in before_pos or None in after_pos:
                return False, False, "Error: movement verification unavailable", False
            if after_pos == before_pos:
                return False, True, "Error: position did not change after walk", False
            return (
                True,
                True,
                f"Walked {direction} {tiles} tile(s): {before_pos} -> {after_pos}",
                False,
            )

        if name == "interact":
            before = observe()
            emulator.press_button("a", frames=5)
            emulator.fast_forward(30)
            after = observe()
            if _state_signature(after) == _state_signature(before):
                return (
                    False,
                    True,
                    "Error: interaction produced no observable state change",
                    False,
                )
            text = after.get("text_content") or after.get("text_lines") or []
            return True, True, f"Interaction changed state; text={text}", False

        if name == "read_dialogue":
            current = observe()
            text = current.get("text_content") or current.get("text_lines") or []
            if not text:
                return (
                    False,
                    True,
                    "Error: no dialogue text is currently visible",
                    False,
                )
            return (
                True,
                True,
                "Dialogue: " + " | ".join(str(item) for item in text),
                False,
            )

        if name == "recall":
            key = arguments.get("key")
            labels = arguments.get("labels")
            query_text = arguments.get("query")
            if not any((key, labels, query_text)):
                return (
                    False,
                    False,
                    "Error: recall requires key, labels, or query",
                    False,
                )
            records = memory.recall(
                key=str(key) if key else None,
                labels=[str(item) for item in labels[:3]]
                if isinstance(labels, list)
                else None,
                query=str(query_text) if query_text else None,
                limit=max(1, min(int(arguments.get("limit", 4)), 4)),
            )
            return (
                True,
                True,
                f"Recalled {len(records)} record(s): {json.dumps(records, default=str)}",
                False,
            )

        if name == "delegate_research":
            if delegate is None:
                return (
                    False,
                    False,
                    "Error: delegation is unavailable in this run",
                    True,
                )
            question = " ".join(str(arguments.get("question", "")).split())[:300]
            if len(question) < 3:
                return (
                    False,
                    False,
                    "Error: delegate_research requires a question",
                    True,
                )
            delegated = delegate.research(
                question=question,
                public_context=_public_context(projection, caps.public_context_chars),
                caps=caps,
            )
            tool_calls = int(delegated.get("tool_calls", 0))
            elapsed = float(delegated.get("elapsed_s", 0.0))
            cost = float(delegated.get("cost_usd", 0.0))
            if tool_calls > caps.delegate_tool_calls:
                return False, False, "Error: delegate exceeded tool-call cap", True
            if elapsed > caps.delegate_wall_seconds:
                return False, False, "Error: delegate exceeded wall-clock cap", True
            if cost > caps.delegate_cost_usd:
                return False, False, "Error: delegate exceeded cost cap", True
            finding = " ".join(str(delegated.get("finding", "")).split())[
                : caps.finding_chars
            ]
            if not finding:
                return False, False, "Error: delegate returned no finding", True
            raw_sources = delegated.get("sources", [])
            sources = (
                [str(source)[:160] for source in raw_sources[: caps.source_count]]
                if isinstance(raw_sources, list)
                else []
            )
            confidence = max(0.0, min(float(delegated.get("confidence", 0.0)), 1.0))
            digest = hashlib.sha256(question.encode()).hexdigest()[:16]
            record = {
                "key": f"/world/research/{digest}",
                "domain": "world/mechanics/research",
                "labels": ["world/mechanics", "delegated"],
                "finding": finding,
                "sources": sources,
                "confidence": confidence,
                "evidence": {"cycle": cycle, "source": "delegate_research"},
                "applies_when": {"question": question},
            }
            memory_id = memory.remember_finding(record)
            context.inject_finding(finding)
            return (
                True,
                True,
                f"Persisted delegated finding {memory_id}: {finding}; sources={sources}; confidence={confidence:.2f}",
                True,
            )

        return False, False, f"Error: unknown agentic tool {name!r}", False
    except Exception as exc:
        return False, False, f"Error: {name} failed: {exc}", name == "delegate_research"


def _final_decision(raw: str, max_actions: int = 6) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("plan"), list):
        return None
    plan = [
        str(item).upper()
        for item in payload["plan"][:max_actions]
        if str(item).upper() in _ALLOWED_ACTIONS
    ]
    return {
        "plan": plan,
        "intent": str(payload.get("intent", "agentic controller decision"))[:240],
        "raw_response": raw,
    }


def run_agentic_cycle(
    *,
    client: Any,
    emulator: Any,
    observe: Any,
    projection: dict[str, Any],
    context: BoundedAgentContext,
    memory: AgentMemory,
    delegate: ResearchDelegate | None,
    model: str,
    cycle: int,
    decision_mode: str,
    decision_mode_family: str,
    caps: AgenticCaps | None = None,
) -> AgenticCycleResult:
    """Run a bounded model→tool→result loop and return a movement decision."""
    active_caps = caps or AgenticCaps()
    public_projection = _public_context(projection, active_caps.public_context_chars)
    context_block = context.render()
    prompt = (
        "You control a Pokémon emulator through a small verified tool surface. "
        'Choose one tool or return JSON {"plan": [...], "intent": "..."}. '
        "Tool failures are evidence: inspect the returned error and do not replace "
        "it with a blind A press. All calls are bounded and audited.\n"
        f"DECISION MODE: {decision_mode} ({decision_mode_family}); agentic_tools=true\n"
        f"BOUNDS: max_tool_calls={active_caps.max_tool_calls}; "
        f"delegate_wall_s={active_caps.delegate_wall_seconds}; "
        f"delegate_tool_calls={active_caps.delegate_tool_calls}; "
        f"delegate_cost_usd={active_caps.delegate_cost_usd}\n"
        f"CONTEXT:\n{context_block or '(no prior turns)'}\n"
        "observation: " + json.dumps(public_projection, ensure_ascii=False, default=str)
    )
    prompt = prompt[-active_caps.prompt_chars :]
    events: list[dict[str, Any]] = []

    for call_index in range(max(0, active_caps.max_tool_calls)):
        raw = client.send_tool_request(
            prompt,
            AGENTIC_TOOL_SCHEMA,
            model=model,
            max_tokens=300,
            temperature=0.1,
        )
        final = _final_decision(raw)
        if final is not None:
            final["agentic_tool_calls"] = len(events)
            return AgenticCycleResult(final, events, context.evidence())
        requested = parse_tool_call(raw)
        if not requested:
            decision = {
                "plan": [],
                "intent": "agentic_response_unreadable",
                "raw_response": raw,
                "agentic_tool_calls": len(events),
            }
            return AgenticCycleResult(decision, events, context.evidence())
        arguments = requested.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        name = str(requested.get("name", ""))
        ok, verified, result_text, delegation = _tool_result(
            name=name,
            arguments=arguments,
            emulator=emulator,
            observe=observe,
            memory=memory,
            delegate=delegate,
            context=context,
            projection=projection,
            caps=active_caps,
            cycle=cycle,
        )
        result_text = result_text[: active_caps.tool_result_chars]
        event = {
            "cycle": cycle,
            "event": "agent_tool_call",
            "decision_mode": decision_mode,
            "decision_mode_family": decision_mode_family,
            "agentic_tools_enabled": True,
            "tool_call_index": call_index + 1,
            "tool_call_cap": active_caps.max_tool_calls,
            "tool_name": name,
            "arguments": arguments,
            "ok": ok,
            "verified": verified,
            "result": result_text,
            "delegation": delegation,
            "caps": (
                {
                    "wall_seconds": active_caps.delegate_wall_seconds,
                    "tool_calls": active_caps.delegate_tool_calls,
                    "cost_usd": active_caps.delegate_cost_usd,
                }
                if delegation
                else None
            ),
            "context_evidence": context.evidence(),
        }
        events.append(event)
        context.record(
            cycle=cycle,
            decision=f"tool:{name}",
            action=json.dumps(arguments, sort_keys=True, default=str),
            result=result_text,
            text_facts=(projection.get("text_content") or [])[:3],
        )
        result_envelope = json.dumps(
            {"tool": name, "ok": ok, "verified": verified, "result": result_text},
            ensure_ascii=False,
        )
        prompt = (
            f"{prompt}\nTOOL RESULT {call_index + 1}/{active_caps.max_tool_calls}: "
            f"{result_envelope}\nChoose another tool or return the final plan JSON."
        )[-active_caps.prompt_chars :]

    decision = {
        "plan": [],
        "intent": "agentic_tool_cap_reached",
        "raw_response": "",
        "agentic_tool_calls": len(events),
    }
    return AgenticCycleResult(decision, events, context.evidence())
