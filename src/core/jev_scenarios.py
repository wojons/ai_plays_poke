"""Versioned JEV teacher-patch scenarios (PRD v3 stage 8 / AC-7).

Promotion is an explicit, offline action. Gameplay only reads the repository-owned
artifact and never writes DuckBrain data, secrets, or arbitrary teacher failures.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SCHEMA_FILENAME = "jev_promoted_patches.schema.json"
KNOWLEDGE_LAYERS = frozenset({"MECHANICS", "LEARNING"})


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _validate_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("evidence must be a non-empty list")
    evidence: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("evidence entries must be objects")
        if set(item) != {"run_id", "cycle"}:
            raise ValueError("evidence entries require only run_id and cycle")
        run_id = item.get("run_id")
        cycle = item.get("cycle")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("evidence run_id must be a non-empty string")
        if isinstance(cycle, bool) or not isinstance(cycle, int) or cycle < 1:
            raise ValueError("evidence cycle must be a positive integer")
        evidence.append({"run_id": run_id.strip(), "cycle": cycle})
    return evidence


def _validate_scenario(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("scenario entries must be objects")
    expected_fields = {
        "id",
        "knowledge_layer",
        "missing_class",
        "missing_facts",
        "fact_source",
        "instruction_patch",
        "applies_when",
        "confidence",
        "evidence",
    }
    if set(value) != expected_fields:
        raise ValueError("scenario fields do not match schema version 1")
    scenario_id = value.get("id")
    missing_class = value.get("missing_class")
    knowledge_layer = value.get("knowledge_layer")
    instruction_patch = value.get("instruction_patch")
    applies_when = value.get("applies_when")
    confidence = value.get("confidence")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise ValueError("scenario id must be a non-empty string")
    if not isinstance(missing_class, str) or not missing_class.strip():
        raise ValueError("missing_class must be a non-empty string")
    if knowledge_layer not in KNOWLEDGE_LAYERS:
        raise ValueError("knowledge_layer must be MECHANICS or LEARNING")
    if not isinstance(instruction_patch, str) or not instruction_patch.strip():
        raise ValueError("instruction_patch must be a non-empty string")
    if not isinstance(applies_when, str) or not applies_when.strip():
        raise ValueError("applies_when must be a non-empty string")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number from 0 to 1")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be a number from 0 to 1")
    return {
        "id": scenario_id.strip(),
        "knowledge_layer": knowledge_layer,
        "missing_class": missing_class.strip(),
        "missing_facts": _string_list(value.get("missing_facts"), "missing_facts"),
        "fact_source": _string_list(value.get("fact_source"), "fact_source"),
        "instruction_patch": instruction_patch.strip(),
        "applies_when": applies_when.strip(),
        "confidence": confidence,
        "evidence": _validate_evidence(value.get("evidence")),
    }


def load_scenarios(artifact_path: str | Path | None) -> list[dict[str, Any]]:
    """Load and validate a scenario artifact; an absent path means no scenarios."""
    if artifact_path is None:
        return []
    path = Path(artifact_path)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"scenario artifact schema_version must be {SCHEMA_VERSION}")
    if not set(payload) <= {"$schema", "schema_version", "scenarios"}:
        raise ValueError("scenario artifact fields do not match schema version 1")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("scenario artifact scenarios must be a list")
    validated = [_validate_scenario(scenario) for scenario in scenarios]
    ids = [scenario["id"] for scenario in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("scenario ids must be unique")
    return validated


def scenario_matches(
    scenario: dict[str, Any], *, missing_class: str, context: str
) -> bool:
    """Match class plus a conservative, deterministic ``applies_when`` clause.

    ``always`` is explicit. Every other clause must occur as a normalized,
    case-insensitive substring of the exact state projection. This deliberately
    avoids treating free-form teacher prose as executable code.
    """
    if scenario.get("missing_class") != missing_class:
        return False
    applies_when = scenario.get("applies_when")
    if not isinstance(applies_when, str):
        return False
    condition = _normalized_text(applies_when)
    return condition == "always" or bool(
        condition and condition in _normalized_text(context)
    )


def find_matching_scenario(
    artifact_path: str | Path | None, *, missing_class: str, context: str
) -> dict[str, Any] | None:
    """Return the first versioned scenario matching the current decision gap."""
    for scenario in load_scenarios(artifact_path):
        if scenario_matches(scenario, missing_class=missing_class, context=context):
            return scenario
    return None


def _scenario_id(missing_class: str, applies_when: str, instruction_patch: str) -> str:
    fingerprint = json.dumps(
        [missing_class, applies_when, instruction_patch],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    slug = re.sub(r"[^a-z0-9]+", "-", missing_class.casefold()).strip("-")
    return f"{slug}-{hashlib.sha256(fingerprint).hexdigest()[:12]}"


def promote_teacher_record(
    record: dict[str, Any],
    *,
    missing_class: str,
    knowledge_layer: str,
    run_id: str,
    cycle: int,
    artifact_path: str | Path,
) -> dict[str, Any]:
    """Explicitly promote one successful teacher record into the artifact.

    Evidence comes only from the caller. Re-promoting the same patch appends a
    distinct evidence pair instead of creating a duplicate scenario.
    """
    if not record.get("ok") or not record.get("improved"):
        raise ValueError("only a successful, improved teacher record can be promoted")
    patch = record.get("patch")
    if not isinstance(patch, dict) or not patch.get("ok"):
        raise ValueError("teacher record must contain a successful patch")
    if not isinstance(missing_class, str) or not missing_class.strip():
        raise ValueError("missing_class must be supplied by the caller")
    if knowledge_layer not in KNOWLEDGE_LAYERS:
        raise ValueError("knowledge_layer must be MECHANICS or LEARNING")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be supplied by the caller")
    if isinstance(cycle, bool) or not isinstance(cycle, int) or cycle < 1:
        raise ValueError("cycle must be a positive integer supplied by the caller")

    instruction = patch.get("instruction_patch")
    condition = patch.get("applies_when")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("successful patch has no instruction_patch")
    if not isinstance(condition, str) or not condition.strip():
        raise ValueError("successful patch has no applies_when condition")
    confidence = patch.get("confidence")
    entry = _validate_scenario(
        {
            "id": _scenario_id(missing_class, condition, instruction),
            "knowledge_layer": knowledge_layer,
            "missing_class": missing_class,
            "missing_facts": patch.get("missing_facts"),
            "fact_source": patch.get("fact_source"),
            "instruction_patch": instruction,
            "applies_when": condition,
            "confidence": confidence,
            "evidence": [{"run_id": run_id, "cycle": cycle}],
        }
    )

    path = Path(artifact_path)
    scenarios = load_scenarios(path)
    existing = next((item for item in scenarios if item["id"] == entry["id"]), None)
    if existing is None:
        scenarios.append(entry)
        promoted = entry
    else:
        evidence = entry["evidence"][0]
        if evidence not in existing["evidence"]:
            existing["evidence"].append(evidence)
        promoted = existing

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(
            {
                "$schema": SCHEMA_FILENAME,
                "schema_version": SCHEMA_VERSION,
                "scenarios": scenarios,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
    return promoted
