"""Portable runtime-path resolvers must keep resolving (RELEASE-009-R1).

``7d44673`` (RELEASE-009) replaced absolute operator-home paths inside the scripts and
Console tools with env-overridable resolvers: each one reads ``AIPP_<NAME>`` and falls
back to a documented default derived from ``__file__`` or ``Path.home()``. Nothing
guarded those expressions, so an edit to a default (or a rename of the override) would
break a runtime path silently — a wrong ROM path, a wrong ``.env``, no interpreter.

Three things are asserted per resolver:

* the documented default, with ``HOME`` pinned to ``tmp_path`` so the assertion is
  about the expression rather than about this operator's home directory;
* the override winning when ``AIPP_<NAME>`` names a sentinel path under ``tmp_path``;
* for the shell wrapper, the fail-closed branch (exit 2, ``no interpreter found``).

WHY THE SOURCE IS PARSED INSTEAD OF IMPORTED
--------------------------------------------
Every tool under ``tools/console/`` is an operator SCRIPT with no ``if __name__``
guard: importing ``tools/console/test_pass.py`` runs a full live pass against
``http://127.0.0.1:8899``, and ``tools/console/test_auto_vision.py`` presses RIGHT
twice at module level. A test that imported them would drive the live emulator, so
each resolver's module-level assignment is evaluated from the parsed AST instead —
the real expression, read out of the real file. ``__name__`` is set to a non-main
sentinel and every statement that is not an import or the target assignment(s) is
dropped, so nothing in the module body can run.

The ``exec``-tee restriction also means a resolver is expected to be assigned
EXACTLY once at module level; a second assignment (which would silently win over the
one under test) fails the load helper rather than being ignored.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# ── the resolvers under test (from 7d44673) ────────────────────────────────────

CHECKOUT_REPO_FILES = (
    "scripts/perception_diff.py",
    "scripts/run_base1_baseline.py",
    "scripts/benchmark_llm_vs_jev.py",
)
AIPP_REPO_FILES = (
    "tools/console/test_auto_vision.py",
    "tools/console/test_pass.py",
)
CANONICAL_ENV_FILES = (
    "scripts/perception_diff.py",
    "scripts/run_base1_baseline.py",
    "scripts/benchmark_llm_vs_jev.py",
)
AIPP_CONSOLE_HOME_FILES = (
    "tools/console/test_controls.py",
    "tools/console/test_pass.py",
)
PY_FILES = (
    "tools/console/test_auto_vision.py",
    "tools/console/test_pass.py",
)

ROM_FILENAME = "Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"

# Every file whose absolute host path 7d44673 removed. capture.py is included: it is
# part of the same commit and resolves its root the same way.
HOST_PATH_FILES = (
    "capture.py",
    "scripts/perception_diff.py",
    "scripts/run_base1_baseline.py",
    "scripts/benchmark_llm_vs_jev.py",
    "scripts/aipp-mcp-wrapper.sh",
    "docs/handbook/sheet_style.py",
    "tools/console/test_auto_vision.py",
    "tools/console/test_controls.py",
    "tools/console/test_pass.py",
)

RESOLVER_ENV_VARS = {
    "scripts/perception_diff.py": ("AIPP_CANONICAL_ENV",),
    "scripts/run_base1_baseline.py": ("AIPP_CANONICAL_ENV",),
    "scripts/benchmark_llm_vs_jev.py": ("AIPP_CANONICAL_ENV",),
    "scripts/aipp-mcp-wrapper.sh": ("AIPP_PYTHON",),
    "docs/handbook/sheet_style.py": ("AIPP_HANDBOOK_RENDER",),
    "tools/console/test_auto_vision.py": ("AIPP_REPO",),
    "tools/console/test_controls.py": ("AIPP_CONSOLE_HOME",),
    "tools/console/test_pass.py": ("AIPP_REPO", "AIPP_CONSOLE_HOME"),
}

ALL_AIPP_ENV_VARS = (
    "AIPP_CANONICAL_ENV",
    "AIPP_CONSOLE_HOME",
    "AIPP_HANDBOOK_RENDER",
    "AIPP_REPO",
    "AIPP_PYTHON",
)


@pytest.fixture(autouse=True)
def _clean_resolver_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ambient AIPP_* may leak in and make a 'default' look overridden."""
    for name in ALL_AIPP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _eval_module_constants(rel_path: str, names: tuple[str, ...]) -> dict[str, Any]:
    """Evaluate the named module-level assignments of ``rel_path``.

    Only imports and the target assignments are compiled, so a module whose body
    drives a live console cannot run from here. An import that cannot be satisfied in
    isolation is skipped rather than propagated: the resolvers are stdlib-only
    (``os`` / ``pathlib`` / ``sys``) and some sibling imports are actively unsafe in a
    test process — ``scripts/vision_blueprint_probe.py`` reads the checkout's ``.env``
    into ``os.environ`` at import time. A resolver that genuinely needs a skipped name
    still fails, as a NameError, below.
    """
    path = REPO_ROOT / rel_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[ast.stmt] = []
    assignments: dict[str, list[ast.stmt]] = {}

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.setdefault(target.id, []).append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments.setdefault(node.target.id, []).append(node)

    unassigned = sorted(name for name in names if name not in assignments)
    assert not unassigned, (
        f"{rel_path}: no module-level assignment for {unassigned} "
        "— the resolver was moved or renamed"
    )

    # A resolver may be built from another module-level constant (PY reads REPO), so
    # walk the dependencies of each requested assignment and take them in an order
    # that evaluates the dependencies first.
    order: list[str] = []
    duplicated: dict[str, int] = {}

    def visit(name: str, stack: frozenset[str]) -> None:
        if name in order:
            return
        assert name not in stack, f"{rel_path}: {name} depends on itself"
        nodes = assignments[name]
        if len(nodes) != 1:
            duplicated[name] = len(nodes)
            return
        value = nodes[0].value  # type: ignore[attr-defined]
        deps = sorted(
            {
                n.id
                for n in ast.walk(value)
                if isinstance(n, ast.Name) and n.id in assignments
            }
        )
        for dep in deps:
            visit(dep, stack | {name})
        order.append(name)

    for name in names:
        visit(name, frozenset())

    assert not duplicated, (
        f"{rel_path}: {sorted(duplicated)} assigned {duplicated} times at module "
        "level; a second assignment masks the one this test pins"
    )

    namespace: dict[str, Any] = {
        "__file__": str(path),
        "__name__": "aipp_path_resolver_probe",  # never "__main__"
    }
    for node in imports:
        try:
            exec(  # noqa: S102
                compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"),
                namespace,
            )
        except Exception:  # noqa: BLE001 - an unusable sibling import is not the subject
            continue
    body = [assignments[name][0] for name in order]
    exec(  # noqa: S102
        compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return {name: namespace[name] for name in names}


def _constant(rel_path: str, name: str) -> Any:
    return _eval_module_constants(rel_path, (name,))[name]


# ── CANONICAL_ENV: the canonical checkout's .env ──────────────────────────────


@pytest.mark.parametrize("rel_path", CANONICAL_ENV_FILES)
def test_canonical_env_override_wins(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "sentinel.env"
    sentinel.write_text("OPENROUTER_API_KEY=placeholder\n", encoding="utf-8")
    monkeypatch.setenv("AIPP_CANONICAL_ENV", str(sentinel))

    assert _constant(rel_path, "CANONICAL_ENV") == sentinel


@pytest.mark.parametrize("rel_path", CANONICAL_ENV_FILES)
def test_canonical_env_defaults_to_the_canonical_checkout_dotenv(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    resolved = _constant(rel_path, "CANONICAL_ENV")

    assert resolved == home / "ai_plays_poke" / ".env"
    assert resolved.name == ".env"


# ── REPO: the checkout a script lives in ──────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path", CHECKOUT_REPO_FILES + AIPP_REPO_FILES, ids=lambda p: p
)
def test_repo_defaults_to_the_checkout_that_holds_the_file(
    rel_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AIPP_REPO", raising=False)

    assert _constant(rel_path, "REPO") == REPO_ROOT


@pytest.mark.parametrize("rel_path", AIPP_REPO_FILES)
def test_aipp_repo_override_wins(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "elsewhere"
    sentinel.mkdir()
    monkeypatch.setenv("AIPP_REPO", str(sentinel))

    assert _constant(rel_path, "REPO") == sentinel


def test_perception_diff_rom_is_repo_relative() -> None:
    """ROM used to be a fixed home path; it must now hang off the resolved REPO."""
    consts = _eval_module_constants("scripts/perception_diff.py", ("REPO", "ROM"))

    assert consts["ROM"] == consts["REPO"] / "data" / "rom" / ROM_FILENAME
    assert consts["ROM"].is_relative_to(consts["REPO"])


# ── RENDER_SH: the handbook renderer (a skill path, not a repo path) ─────────


def test_handbook_render_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "render.sh"
    sentinel.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    monkeypatch.setenv("AIPP_HANDBOOK_RENDER", str(sentinel))

    assert _constant("docs/handbook/sheet_style.py", "RENDER_SH") == sentinel


def test_handbook_render_defaults_to_the_skill_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    resolved = _constant("docs/handbook/sheet_style.py", "RENDER_SH")

    assert resolved == Path(
        home, ".hermes", "skills", "nasa-handbook", "scripts", "render.sh"
    )


# ── CONSOLE: the external operator console checkout ──────────────────────────


@pytest.mark.parametrize("rel_path", AIPP_CONSOLE_HOME_FILES)
def test_console_home_override_wins(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "console-checkout"
    sentinel.mkdir()
    monkeypatch.setenv("AIPP_CONSOLE_HOME", str(sentinel))

    assert _constant(rel_path, "CONSOLE") == sentinel


@pytest.mark.parametrize("rel_path", AIPP_CONSOLE_HOME_FILES)
def test_console_home_defaults_to_the_sibling_checkout(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    assert _constant(rel_path, "CONSOLE") == home / "aipp-console"


# ── PY: the checkout's own interpreter, whichever venv it carries ────────────


def _touch_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.mark.parametrize("rel_path", PY_FILES)
def test_python_uses_the_dot_venv_interpreter(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "checkout"
    interp = _touch_executable(root / ".venv" / "bin" / "python")
    monkeypatch.setenv("AIPP_REPO", str(root))

    assert _constant(rel_path, "PY") == str(interp)


@pytest.mark.parametrize("rel_path", PY_FILES)
def test_python_falls_back_to_the_py311_venv(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "checkout"
    interp = _touch_executable(root / "venv" / "bin" / "python")
    monkeypatch.setenv("AIPP_REPO", str(root))

    assert _constant(rel_path, "PY") == str(interp)


@pytest.mark.parametrize("rel_path", PY_FILES)
def test_python_prefers_dot_venv_when_both_exist(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "checkout"
    dot_venv = _touch_executable(root / ".venv" / "bin" / "python")
    _touch_executable(root / "venv" / "bin" / "python")
    monkeypatch.setenv("AIPP_REPO", str(root))

    assert _constant(rel_path, "PY") == str(dot_venv)


@pytest.mark.parametrize("rel_path", PY_FILES)
def test_python_last_resort_is_the_running_interpreter(
    rel_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bare-checkout"
    root.mkdir()
    monkeypatch.setenv("AIPP_REPO", str(root))

    assert _constant(rel_path, "PY") == sys.executable


# ── scripts/aipp-mcp-wrapper.sh: interpreter + fail-closed branch ────────────

WRAPPER_REL = "scripts/aipp-mcp-wrapper.sh"
_NO_INTERPRETER = "no interpreter found"


def _stub_interpreter(path: Path) -> Path:
    """An interpreter stand-in that reports its own path and its first argument."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '#!/bin/sh\nprintf \'%s\\t%s\\n\' "$0" "$1"\nexit 0\n', encoding="utf-8"
    )
    path.chmod(0o755)
    return path


def _wrapper_checkout(tmp_path: Path, *venv_dirs: str) -> Path:
    """A hermetic copy of the wrapper and the file it execs.

    The venv interpreters are reporting stubs, not real pythons: the assertion is which
    path the wrapper exec'd, and a stub makes that observable while running nothing.
    """
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / WRAPPER_REL, root / "scripts" / "aipp-mcp-wrapper.sh")
    (root / "scripts" / "aipp_mcp.py").write_text("", encoding="utf-8")
    for venv in venv_dirs:
        _stub_interpreter(root / venv / "bin" / "python")
    return root


def _run_wrapper(
    root: Path, env_extra: dict[str, str] | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.defpath, "HOME": str(root.parent / "home")}
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(root / "scripts" / "aipp-mcp-wrapper.sh")],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd or root.parent),
        timeout=60,
    )


def test_wrapper_fails_closed_when_no_interpreter_is_found(tmp_path: Path) -> None:
    root = _wrapper_checkout(tmp_path)

    proc = _run_wrapper(root)

    assert proc.returncode == 2, proc.stderr
    assert _NO_INTERPRETER in proc.stderr
    assert "AIPP_PYTHON" in proc.stderr
    assert proc.stdout == ""  # nothing was exec'd


def test_wrapper_aipp_python_override_wins(tmp_path: Path) -> None:
    root = _wrapper_checkout(tmp_path, "venv")
    stub = _stub_interpreter(tmp_path / "stub" / "python")

    proc = _run_wrapper(root, {"AIPP_PYTHON": str(stub)})

    assert proc.returncode == 0, proc.stderr
    reported, script = proc.stdout.strip().split("\t")
    assert reported == str(stub)
    assert script == str(root / "scripts" / "aipp_mcp.py")


def test_wrapper_uses_the_checkouts_own_venv(tmp_path: Path) -> None:
    root = _wrapper_checkout(tmp_path, "venv")

    proc = _run_wrapper(root)

    assert proc.returncode == 0, proc.stderr
    reported, script = proc.stdout.strip().split("\t")
    assert reported == str(root / "venv" / "bin" / "python")
    assert script == str(root / "scripts" / "aipp_mcp.py")


def test_wrapper_falls_back_to_the_dot_venv(tmp_path: Path) -> None:
    root = _wrapper_checkout(tmp_path, ".venv")

    proc = _run_wrapper(root)

    assert proc.returncode == 0, proc.stderr
    reported, _script = proc.stdout.strip().split("\t")
    assert reported == str(root / ".venv" / "bin" / "python")


def test_wrapper_prefers_the_complete_py311_venv(tmp_path: Path) -> None:
    """Wrapper order is ``venv/`` then ``.venv/`` — the opposite of the Python tools.

    Deliberate, per the wrapper's own comment: the py3.11 ``venv/`` is the complete
    environment the MCP server needs, ``.venv/`` the held py3.13 one. The console tools
    (``PY``, below) resolve ``.venv/`` first. Pinned as-is rather than "made
    consistent", because changing one of the two orders changes what runs in production.
    """
    root = _wrapper_checkout(tmp_path, "venv", ".venv")

    proc = _run_wrapper(root)

    assert proc.returncode == 0, proc.stderr
    reported, _script = proc.stdout.strip().split("\t")
    assert reported == str(root / "venv" / "bin" / "python")


def test_wrapper_resolves_the_checkout_from_its_own_location(tmp_path: Path) -> None:
    """Run from an unrelated cwd: the target must follow the wrapper, not the cwd."""
    root = _wrapper_checkout(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    stub = _stub_interpreter(tmp_path / "stub" / "python")

    proc = _run_wrapper(root, {"AIPP_PYTHON": str(stub)}, cwd=elsewhere)

    assert proc.returncode == 0, proc.stderr
    _reported, script = proc.stdout.strip().split("\t")
    assert script == str(root / "scripts" / "aipp_mcp.py")
    assert not Path(script).is_relative_to(elsewhere)


# ── AC3: no absolute host path may come back ─────────────────────────────────

HOST_PATH_MARKERS = ("/home/", "C:\\Users\\")


def find_host_path_literals(source: str) -> list[int]:
    """Line numbers carrying an absolute host path literal."""
    return [
        number
        for number, line in enumerate(source.splitlines(), 1)
        if any(marker in line for marker in HOST_PATH_MARKERS)
    ]


def test_host_path_detector_flags_a_reintroduced_literal() -> None:
    """The guard below is only worth its assertion if it can actually fire."""
    assert find_host_path_literals('REPO = Path("/home/kara/ai_plays_poke")\n') == [1]
    assert find_host_path_literals('X = 1\nSH = "/home/someone/x.sh"\n') == [2]
    # …and it stays quiet on every form 7d44673 put in place instead.
    assert find_host_path_literals("REPO = Path(__file__).resolve().parents[1]\n") == []
    assert find_host_path_literals('SH = Path.home() / ".hermes" / "render.sh"\n') == []
    assert find_host_path_literals('PY = "${AIPP_PYTHON:-}"\n') == []


@pytest.mark.parametrize("rel_path", HOST_PATH_FILES)
def test_no_absolute_host_path_literal_in_source(rel_path: str) -> None:
    source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")

    assert source.strip(), f"{rel_path} is empty — the guard would be vacuous"
    hits = find_host_path_literals(source)
    assert hits == [], (
        f"{rel_path}: absolute host path literal reintroduced on line(s) {hits} — "
        "resolve it from __file__/Path.home() or an AIPP_* override instead"
    )


# ── the env-var names themselves are load-bearing (AC2) ──────────────────────


@pytest.mark.parametrize(
    ("rel_path", "env_vars"),
    sorted(RESOLVER_ENV_VARS.items()),
    ids=sorted(RESOLVER_ENV_VARS),
)
def test_resolver_reads_its_named_override(
    rel_path: str, env_vars: tuple[str, ...]
) -> None:
    source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")

    for name in env_vars:
        assert name in source, f"{rel_path} no longer reads {name}"
