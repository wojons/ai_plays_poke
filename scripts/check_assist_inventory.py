#!/usr/bin/env python3
"""Fail when press_button call sites drift from the declared assist inventory."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TextIO


DEFAULT_INVENTORY = Path("config/assist_inventory.json")
REQUIRED_FIELDS = ("file", "context", "button", "call", "reason")


class GuardError(RuntimeError):
    """Raised when source or inventory data cannot be checked safely."""


@dataclass(frozen=True)
class CallSite:
    """One source-level press_button call."""

    file: str
    context: str
    button: str
    call: str
    line: int

    @property
    def key(self) -> tuple[str, str, str]:
        """Stable identity: file, enclosing context, and normalized call shape."""
        return (self.file, self.context, self.call)


@dataclass(frozen=True)
class InventorySite:
    """One declared call site from config/assist_inventory.json."""

    file: str
    context: str
    button: str
    call: str
    reason: str
    allow_stale: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.file, self.context, self.call)


class PressButtonVisitor(ast.NodeVisitor):
    """Collect press_button calls while tracking class/function context."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.scope: list[str] = []
        self.sites: list[CallSite] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        is_press_button = (
            isinstance(node.func, ast.Attribute) and node.func.attr == "press_button"
        ) or (isinstance(node.func, ast.Name) and node.func.id == "press_button")
        if is_press_button:
            self.sites.append(
                CallSite(
                    file=self.relative_path,
                    context=".".join(self.scope) if self.scope else "<module>",
                    button=_button_expression(node),
                    call=_normalized_call(node),
                    line=node.lineno,
                )
            )
        self.generic_visit(node)


def _button_node(call: ast.Call) -> ast.expr | None:
    if call.args:
        return call.args[0]
    return next(
        (keyword.value for keyword in call.keywords if keyword.arg == "button"),
        None,
    )


def _button_expression(call: ast.Call) -> str:
    node = _button_node(call)
    if node is None:
        return "<missing>"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node)


def _normalized_call(call: ast.Call) -> str:
    """Normalize formatting while preserving press arguments and keyword names."""
    arguments = [ast.unparse(argument) for argument in call.args]
    arguments.extend(
        (
            f"{keyword.arg}={ast.unparse(keyword.value)}"
            if keyword.arg is not None
            else f"**{ast.unparse(keyword.value)}"
        )
        for keyword in call.keywords
    )
    return f"press_button({', '.join(arguments)})"


def _normalize_inventory_call(value: str, index: int) -> tuple[str, str]:
    try:
        expression = ast.parse(value, mode="eval").body
    except SyntaxError as exc:
        raise GuardError(
            f"inventory site {index}: invalid call expression: {exc}"
        ) from exc
    if not (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, (ast.Name, ast.Attribute))
        and (
            (
                isinstance(expression.func, ast.Name)
                and expression.func.id == "press_button"
            )
            or (
                isinstance(expression.func, ast.Attribute)
                and expression.func.attr == "press_button"
            )
        )
    ):
        raise GuardError(
            f"inventory site {index}: call must be a press_button(...) expression"
        )
    return _normalized_call(expression), _button_expression(expression)


def source_files(root: Path) -> Iterable[Path]:
    """Yield the exact production scope: cron_runner.py and Python under src/."""
    cron_runner = root / "cron_runner.py"
    if cron_runner.is_file():
        yield cron_runner
    src = root / "src"
    if src.is_dir():
        yield from sorted(src.rglob("*.py"))


def enumerate_sites(root: Path) -> list[CallSite]:
    """Parse production sources with AST, naturally excluding comments/tests/scripts."""
    sites: list[CallSite] = []
    files = list(source_files(root))
    if not files:
        raise GuardError(f"no guarded source files found under {root}")
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise GuardError(f"cannot parse {relative_path}: {exc}") from exc
        visitor = PressButtonVisitor(relative_path)
        visitor.visit(tree)
        sites.extend(visitor.sites)
    return sorted(
        sites, key=lambda site: (site.file, site.line, site.context, site.call)
    )


def load_inventory(path: Path) -> list[InventorySite]:
    """Load and validate the machine-readable declared assist set."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GuardError(f"cannot load inventory {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sites"), list):
        raise GuardError("inventory root must be an object containing a sites list")

    inventory: list[InventorySite] = []
    for index, raw in enumerate(payload["sites"], start=1):
        if not isinstance(raw, dict):
            raise GuardError(f"inventory site {index}: expected an object")
        missing = [field for field in REQUIRED_FIELDS if not raw.get(field)]
        if missing:
            raise GuardError(
                f"inventory site {index}: missing non-empty fields {', '.join(missing)}"
            )
        if any(not isinstance(raw[field], str) for field in REQUIRED_FIELDS):
            raise GuardError(f"inventory site {index}: required fields must be strings")
        allow_stale = raw.get("allow_stale", False)
        if not isinstance(allow_stale, bool):
            raise GuardError(f"inventory site {index}: allow_stale must be boolean")
        normalized_call, call_button = _normalize_inventory_call(raw["call"], index)
        if raw["button"] != call_button:
            raise GuardError(
                f"inventory site {index}: button {raw['button']!r} does not match "
                f"call button {call_button!r}"
            )
        inventory.append(
            InventorySite(
                file=raw["file"],
                context=raw["context"],
                button=raw["button"],
                call=normalized_call,
                reason=raw["reason"],
                allow_stale=allow_stale,
            )
        )
    return inventory


def _write_table(
    actual: list[CallSite],
    declared: list[InventorySite],
    stream: TextIO,
) -> tuple[int, int]:
    declared_by_key: dict[tuple[str, str, str], list[InventorySite]] = defaultdict(list)
    actual_by_key: dict[tuple[str, str, str], list[CallSite]] = defaultdict(list)
    for declared_site in declared:
        declared_by_key[declared_site.key].append(declared_site)
    for actual_site in actual:
        actual_by_key[actual_site.key].append(actual_site)

    declared_counts = Counter(declared_site.key for declared_site in declared)
    seen_counts: Counter[tuple[str, str, str]] = Counter()
    new_count = 0

    stream.write(
        "STATUS    LOCATION                         CONTEXT                         BUTTON       CALL\n"
    )
    stream.write(
        "--------  -------------------------------  ------------------------------  -----------  ----\n"
    )
    for actual_site in actual:
        seen_counts[actual_site.key] += 1
        is_declared = seen_counts[actual_site.key] <= declared_counts[actual_site.key]
        status = "DECLARED" if is_declared else "NEW"
        if not is_declared:
            new_count += 1
        location = f"{actual_site.file}:{actual_site.line}"
        stream.write(
            f"{status:<8}  {location:<31.31}  {actual_site.context:<30.30}  "
            f"{actual_site.button:<11.11}  {actual_site.call}\n"
        )

    stale_count = 0
    for key, entries in sorted(declared_by_key.items()):
        actual_count = len(actual_by_key.get(key, []))
        required_entries = [entry for entry in entries if not entry.allow_stale]
        missing_required = max(0, len(required_entries) - actual_count)
        for entry in required_entries[-missing_required:] if missing_required else []:
            stale_count += 1
            stream.write(
                f"{'STALE':<8}  {entry.file:<31.31}  {entry.context:<30.30}  "
                f"{entry.button:<11.11}  {entry.call}\n"
            )
    return new_count, stale_count


def run_guard(root: Path, inventory_path: Path, stream: TextIO = sys.stdout) -> int:
    """Run the inventory comparison and return a process-style exit code."""
    try:
        resolved_root = root.resolve()
        actual = enumerate_sites(resolved_root)
        declared = load_inventory(inventory_path.resolve())
    except GuardError as exc:
        stream.write(f"FAIL: assist inventory guard error: {exc}\n")
        return 1

    new_count, stale_count = _write_table(actual, declared, stream)
    if new_count or stale_count:
        stream.write(
            "FAIL: assist inventory mismatch "
            f"({new_count} new, {stale_count} stale; {len(actual)} source sites, "
            f"{len(declared)} declarations).\n"
        )
        return 1
    stream.write(
        f"PASS: assist inventory matches {len(actual)} press_button call sites.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--inventory", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    inventory = args.inventory or root / DEFAULT_INVENTORY
    return run_guard(root, inventory)


if __name__ == "__main__":
    raise SystemExit(main())
