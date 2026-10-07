#!/usr/bin/env python3
# The sole URL is a fixed HTTPS endpoint and the open has a bounded timeout.
# ruff: noqa: S310

"""Measure people identification against live Gen I sprite-table cells.

Examples:
    python scripts/vision_people_probe.py
    python scripts/vision_people_probe.py --slot start --slot pallet_outside_house_20260929 --slot slot1

The first form captures the bridge's current frame. Repeated ``--slot`` arguments load
saved bridge positions before capture; the original live state is restored afterward.
Every captured frame is paired with a temporary emulator state, so ground truth comes
from that frame's wSpriteStateData1 table rather than from a whole-grid comparison.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.core.emulator import Emulator  # noqa: E402

MODEL = "openai/gpt-4o-mini"
PROMPT_PATH = REPO / "prompts/vision_people.md"
SPRITE_TABLE = 0xC100
SPRITE_COUNT = 16
SPRITE_BYTES = 16
PICTURE_OFFSET = 0
SCREEN_Y_OFFSET = 4
SCREEN_X_OFFSET = 6
FACING_OFFSET = 9
CELL_SIZE = 16
GRID_COLS = 9
GRID_ROWS = 9
PLAYER_CELL = (4, 3)
DEFAULT_TOKEN_FILE = Path.home() / ".hermes/aipp_bridge/session.token"
FACING = {0x00: "down", 0x04: "up", 0x08: "left", 0x0C: "right"}
NON_PERSON_SPRITES = frozenset({0x05, 0x09, 0x38, 0x3C})
FIRST_STILL_SPRITE = 0x3D

# pret/pokered constants/sprite_constants.asm. These are visual archetypes, not
# character identities; scoring uses their cells, never a guessed identity.
SPRITE_NAMES = {
    0x01: "red",
    0x02: "blue",
    0x03: "oak",
    0x04: "youngster",
    0x05: "monster",
    0x06: "cooltrainer_f",
    0x07: "cooltrainer_m",
    0x08: "little_girl",
    0x09: "bird",
    0x0A: "middle_aged_man",
    0x0B: "gambler",
    0x0C: "super_nerd",
    0x0D: "girl",
    0x0E: "hiker",
    0x0F: "beauty",
    0x10: "gentleman",
    0x11: "daisy",
    0x12: "biker",
    0x13: "sailor",
    0x14: "cook",
    0x15: "bike_shop_clerk",
    0x16: "mr_fuji",
    0x17: "giovanni",
    0x18: "rocket",
    0x19: "channeler",
    0x1A: "waiter",
    0x1B: "silph_worker_f",
    0x1C: "middle_aged_woman",
    0x1D: "brunette_girl",
    0x1E: "lance",
    0x1F: "unused_scientist",
    0x20: "scientist",
    0x21: "rocker",
    0x22: "swimmer",
    0x23: "safari_zone_worker",
    0x24: "gym_guide",
    0x25: "gramps",
    0x26: "clerk",
    0x27: "fishing_guru",
    0x28: "granny",
    0x29: "nurse",
    0x2A: "link_receptionist",
    0x2B: "silph_president",
    0x2C: "silph_worker_m",
    0x2D: "warden",
    0x2E: "captain",
    0x2F: "fisher",
    0x30: "koga",
    0x31: "guard",
    0x32: "unused_guard",
    0x33: "mom",
    0x34: "balding_guy",
    0x35: "little_boy",
    0x36: "unused_gameboy_kid",
    0x37: "gameboy_kid",
    0x38: "fairy",
    0x39: "agatha",
    0x3A: "bruno",
    0x3B: "lorelei",
    0x3C: "seel",
}


@dataclass(frozen=True)
class TruthPerson:
    slot: int
    sprite_id: int
    sprite_name: str
    cell: tuple[int, int]
    facing: str


@dataclass(frozen=True)
class Prediction:
    name: str
    cell: tuple[int, int]
    feature: str


@dataclass(frozen=True)
class Score:
    correct: bool
    matched: int
    failures: tuple[str, ...]
    feature_notes: tuple[str, ...]


@dataclass(frozen=True)
class FrameResult:
    label: str
    truths: tuple[TruthPerson, ...]
    predictions: tuple[Prediction, ...]
    score: Score
    raw_response: str


class BridgeClient:
    def __init__(self, port: int, token_file: Path) -> None:
        self.port = port
        self.token_file = token_file

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.token_file.exists():
            raise RuntimeError(f"bridge token is missing: {self.token_file}")
        request = dict(payload)
        request["token"] = self.token_file.read_text().strip()
        with socket.create_connection(("127.0.0.1", self.port), timeout=180) as conn:
            conn.sendall((json.dumps(request) + "\n").encode())
            chunks = b""
            while b"\n" not in chunks:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks += chunk
        raw = chunks.split(b"\n", 1)[0].decode()
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise RuntimeError("bridge returned a non-object reply")
        result = cast(dict[str, Any], loaded)
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or "bridge command failed"))
        return result


def parse_json(raw: str) -> dict[str, Any] | None:
    """Extract one JSON object from an otherwise terse model response."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match is None:
        return None
    try:
        loaded = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else None


def parse_predictions(raw: str) -> tuple[list[Prediction], list[str]]:
    """Validate the people/name/cell/feature envelope without repairing it."""
    loaded = parse_json(raw)
    if loaded is None:
        return [], ["response was not a JSON object"]
    people = loaded.get("people")
    if not isinstance(people, list):
        return [], ["response did not contain a people list"]

    predictions: list[Prediction] = []
    errors: list[str] = []
    for index, item in enumerate(people):
        if not isinstance(item, dict):
            errors.append(f"people[{index}] was not an object")
            continue
        name = item.get("name")
        feature = item.get("feature")
        cell = item.get("cell")
        valid_cell = (
            isinstance(cell, list)
            and len(cell) == 2
            and all(
                isinstance(value, int) and not isinstance(value, bool) for value in cell
            )
        )
        if not isinstance(name, str) or not name.strip():
            errors.append(f"people[{index}] had no name")
            continue
        if not isinstance(feature, str) or not feature.strip():
            errors.append(f"people[{index}] had no feature")
            continue
        if not valid_cell:
            errors.append(f"people[{index}] had an invalid cell")
            continue
        assert isinstance(cell, list)
        parsed_cell = (int(cell[0]), int(cell[1]))
        if not (0 <= parsed_cell[0] < GRID_COLS and 0 <= parsed_cell[1] < GRID_ROWS):
            errors.append(
                f"people[{index}] cell {parsed_cell} was outside the 9x9 window"
            )
            continue
        predictions.append(Prediction(name.strip(), parsed_cell, feature.strip()))
    return predictions, errors


def visible_people(read_u8: Callable[[int], int]) -> list[TruthPerson]:
    """Read visible human sprite cells relative to the measured player cell (4,3)."""
    player_y = read_u8(SPRITE_TABLE + SCREEN_Y_OFFSET)
    player_x = read_u8(SPRITE_TABLE + SCREEN_X_OFFSET)
    people: list[TruthPerson] = []
    for slot in range(1, SPRITE_COUNT):
        base = SPRITE_TABLE + slot * SPRITE_BYTES
        sprite_id = read_u8(base + PICTURE_OFFSET)
        if (
            sprite_id == 0
            or sprite_id >= FIRST_STILL_SPRITE
            or sprite_id in NON_PERSON_SPRITES
        ):
            continue
        screen_y = read_u8(base + SCREEN_Y_OFFSET)
        screen_x = read_u8(base + SCREEN_X_OFFSET)
        cell = (
            PLAYER_CELL[0] + (screen_x - player_x) // CELL_SIZE,
            PLAYER_CELL[1] + (screen_y - player_y) // CELL_SIZE,
        )
        if not (0 <= cell[0] < GRID_COLS and 0 <= cell[1] < GRID_ROWS):
            continue
        facing_bits = read_u8(base + FACING_OFFSET) & 0x0C
        people.append(
            TruthPerson(
                slot=slot,
                sprite_id=sprite_id,
                sprite_name=SPRITE_NAMES.get(
                    sprite_id, f"sprite_{sprite_id:02x}"
                ).replace("_", " "),
                cell=cell,
                facing=FACING.get(facing_bits, "unknown"),
            )
        )
    return people


def people_from_state(state_path: Path, rom_path: Path) -> list[TruthPerson]:
    emulator = Emulator(str(rom_path))
    try:
        emulator.load_state(str(state_path))
        return visible_people(emulator.read_u8)
    finally:
        emulator.stop()


def _distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def score_predictions(
    truths: list[TruthPerson],
    predictions: list[Prediction],
    parse_errors: list[str] | None = None,
) -> Score:
    """Score only sprite-cell presence; names/features remain diagnostics."""
    predictions_by_cell: dict[tuple[int, int], list[Prediction]] = {}
    for prediction in predictions:
        predictions_by_cell.setdefault(prediction.cell, []).append(prediction)

    matched = 0
    unmatched_truths: list[TruthPerson] = []
    unmatched_predictions: list[Prediction] = []
    feature_notes: list[str] = []
    for person in truths:
        candidates = predictions_by_cell.get(person.cell, [])
        if not candidates:
            unmatched_truths.append(person)
            continue
        prediction = candidates.pop(0)
        matched += 1
        facing_match = re.search(
            r"\b(?:facing|faces?)\s+(up|down|left|right)\b",
            prediction.feature.lower(),
        )
        if facing_match and facing_match.group(1) != person.facing:
            feature_notes.append(
                f"wrong feature at {person.cell}: model {facing_match.group(1)}, "
                f"RAM facing {person.facing} (not scored)"
            )

    for candidates in predictions_by_cell.values():
        unmatched_predictions.extend(candidates)

    failures = list(parse_errors or [])
    while unmatched_truths and unmatched_predictions:
        best = min(
            (
                (_distance(truth.cell, prediction.cell), truth_index, prediction_index)
                for truth_index, truth in enumerate(unmatched_truths)
                for prediction_index, prediction in enumerate(unmatched_predictions)
            ),
            key=lambda item: item[0],
        )
        _, truth_index, prediction_index = best
        truth = unmatched_truths.pop(truth_index)
        prediction = unmatched_predictions.pop(prediction_index)
        failures.append(
            f"wrong cell for {prediction.name}: model {prediction.cell}, "
            f"RAM {truth.cell} ({truth.sprite_name})"
        )

    failures.extend(
        f"missed person at {truth.cell} ({truth.sprite_name})"
        for truth in unmatched_truths
    )
    failures.extend(
        f"hallucinated {prediction.name} at {prediction.cell}"
        for prediction in unmatched_predictions
    )
    correct = not failures and matched == len(truths) == len(predictions)
    return Score(correct, matched, tuple(failures), tuple(feature_notes))


def _image_data_url(frame_path: Path) -> str:
    """Match the existing vision probes' x6 upscale before OpenRouter."""
    with Image.open(frame_path) as opened:
        image = opened.convert("RGB")
        if 0 < image.width < 1024:
            image = image.resize(
                (image.width * 6, image.height * 6), Image.Resampling.LANCZOS
            )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def call_openrouter(frame_path: Path, prompt: str, api_key: str) -> str:
    body = {
        "model": MODEL,
        "max_tokens": 400,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(frame_path)},
                    },
                ],
            }
        ],
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:  # nosec B310
            loaded = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {error.code}: {detail}") from error
    if not isinstance(loaded, dict):
        raise RuntimeError("OpenRouter returned a non-object response")
    choices = loaded.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("OpenRouter response had no choices")
    first = choices[0]
    if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
        raise RuntimeError("OpenRouter response had no message")
    content = first["message"].get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenRouter returned no text content")
    return content


def analyze_frame(
    label: str,
    frame_path: Path,
    state_path: Path,
    rom_path: Path,
    prompt: str,
    api_key: str,
) -> FrameResult:
    truths = people_from_state(state_path, rom_path)
    raw_response = call_openrouter(frame_path, prompt, api_key)
    predictions, parse_errors = parse_predictions(raw_response)
    score = score_predictions(truths, predictions, parse_errors)
    return FrameResult(
        label=label,
        truths=tuple(truths),
        predictions=tuple(predictions),
        score=score,
        raw_response=raw_response,
    )


def _format_truths(truths: tuple[TruthPerson, ...]) -> str:
    if not truths:
        return "none"
    return ", ".join(
        f"{person.sprite_name}@{person.cell}/{person.facing}" for person in truths
    )


def _format_predictions(predictions: tuple[Prediction, ...]) -> str:
    if not predictions:
        return "none"
    return ", ".join(
        f"{person.name}@{person.cell}/{person.feature}" for person in predictions
    )


def print_results(results: list[FrameResult]) -> None:
    print("\nPER-FRAME PEOPLE MEASUREMENT")
    print("frame | RAM sprite people | model people | result")
    print("--- | --- | --- | ---")
    for result in results:
        verdict = "CORRECT" if result.score.correct else "MISS"
        print(
            f"{result.label} | {_format_truths(result.truths)} | "
            f"{_format_predictions(result.predictions)} | {verdict}"
        )
        for failure in result.score.failures:
            print(f"  failure: {failure}")
        for note in result.score.feature_notes:
            print(f"  diagnostic: {note}")

    failed = sum(not result.score.correct for result in results)
    total = len(results)
    correct = total - failed
    true_people = sum(len(result.truths) for result in results)
    matched_people = sum(result.score.matched for result in results)
    failure_rate = 100.0 * failed / total if total else 0.0
    print("\nSUMMARY")
    print(f"model: {MODEL}")
    print(f"frames correct: {correct}/{total}")
    print(f"frames failed: {failed}/{total} ({failure_rate:.1f}% failure rate)")
    print(f"RAM person cells matched: {matched_people}/{true_people}")
    print("score basis: exact RAM sprite cells only; no whole-grid percentage")


def _cleanup_bridge_slot(client: BridgeClient, slot: str) -> None:
    try:
        client.call({"cmd": "delete_save", "slot": slot})
    except Exception as error:  # noqa: BLE001
        print(
            f"warning: could not delete temporary bridge slot {slot}: {error}",
            file=sys.stderr,
        )


def _cleanup_frame(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        print(
            f"warning: could not delete temporary frame {path}: {error}",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slot",
        action="append",
        default=[],
        help="bridge save slot to load and measure; repeat for 3-5 different spots",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AIPP_BRIDGE_PORT", "8770")),
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path(os.environ.get("AIPP_BRIDGE_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))),
    )
    parser.add_argument("--keep-frames", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 2
    prompt = PROMPT_PATH.read_text().strip()
    client = BridgeClient(args.port, args.token_file)
    health = client.call({"cmd": "health"})
    rom_path = Path(str(health["rom"]))

    nonce = f"{os.getpid()}_{time.time_ns()}"
    restore_slot = f"vis_people_restore_{nonce}"
    temporary_slots: list[str] = []
    temporary_frames: list[Path] = []
    results: list[FrameResult] = []
    slots: list[str | None] = list(args.slot) if args.slot else [None]
    needs_restore = bool(args.slot)

    try:
        if needs_restore:
            client.call({"cmd": "save", "slot": restore_slot})
            temporary_slots.append(restore_slot)
        for index, slot in enumerate(slots, start=1):
            label = slot or "current"
            if slot is not None:
                client.call({"cmd": "load", "slot": slot})
            snapshot_slot = f"vis_people_snapshot_{nonce}_{index}"
            saved = client.call({"cmd": "save", "slot": snapshot_slot})
            temporary_slots.append(snapshot_slot)
            frame_label = f"VIS_PEOPLE_{nonce}_{index}"
            captured = client.call({"cmd": "frame", "label": frame_label})
            frame_path = Path(str(captured["frame"]))
            temporary_frames.append(frame_path)
            print(f"measuring {label}: {frame_path.name}", flush=True)
            results.append(
                analyze_frame(
                    label=label,
                    frame_path=frame_path,
                    state_path=Path(str(saved["saved"])),
                    rom_path=rom_path,
                    prompt=prompt,
                    api_key=api_key,
                )
            )
    finally:
        if needs_restore:
            try:
                client.call({"cmd": "load", "slot": restore_slot})
            except Exception as error:  # noqa: BLE001
                print(
                    f"warning: could not restore live bridge state: {error}",
                    file=sys.stderr,
                )
        for slot in reversed(temporary_slots):
            _cleanup_bridge_slot(client, slot)
        if not args.keep_frames:
            for frame_path in temporary_frames:
                _cleanup_frame(frame_path)

    print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
