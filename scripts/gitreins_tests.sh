#!/usr/bin/env bash
# Tier-1 / guard test runner for this repo — resolves a REAL pytest in whatever
# checkout it lands in (operator clone, CI, or a fresh gitreins judge worktree).
#
# Why this exists (INT-GL-3 mode b): `.gitreins/config.yaml` pointed both
# `guards.test_command` and the tier-1 `tests` step at `./venv/bin/pytest`.
# That path only exists where someone has run `uv venv venv && uv pip install -e
# '.[dev]'`; a judge worktree is a bare checkout of a commit, so the cell died
# with "test runner './venv/bin/pytest' not found" and the engine recorded the
# lane as SKIPPED (DF-GITREINS-POC-51) — a judge run that graded no tests and
# still reported tier1 green (verdict 2026-10-30/126d061b).
#
# Resolution order (first candidate that PROVES it can run pytest wins; each is
# probed with `--version`, so a stale shebang or a half-built venv falls through
# instead of dying mid-suite):
#   1. ./venv/bin/pytest                — the operator/CI interpreter (CPython 3.11)
#   2. ./.venv/bin/python -m pytest     — a uv-created worktree venv
#   3. python -m pytest                 — any PATH interpreter with pytest importable
#      (python3 is tried when `python` is absent; minimal images ship only python3)
# Nothing resolvable is a HARD, LOUD failure (exit 127): an unprovisioned
# environment must never read as a green cell. The message names every candidate
# that was tried and how to fix it, and carries a GITREINS_SKIP-style marker so a
# reader can grep the verdict for the gap.
#
# Args are passed straight through to pytest, e.g.
#   ./scripts/gitreins_tests.sh -x --tb=short
#   ./scripts/gitreins_tests.sh tests/test_secrets_allowlist.py -q
#
# Contract notes for whoever edits this:
#   * Exit 0/1/2/5 etc. are pytest's own — never remapped here.
#   * Exit 127 is reserved for "no usable runner" (the shell's own
#     command-not-found code), so a caller can tell environment from code.
#   * Do not add `|| true` / `exit 0` fallbacks: a silent pass is the defect this
#     file removes.
set -u

# Self-location uses ONLY shell builtins: a mangled PATH (the case this script
# must diagnose) has no dirname/head, and dying on those would report the wrong
# cause — the gap is the missing runner, not the missing coreutils.
case "$0" in
  */*) _script_rel="${0%/*}" ;;
  *) _script_rel="." ;;
esac
SCRIPT_DIR="$(CDPATH= cd -- "$_script_rel" && pwd)" || {
  echo "gitreins_tests: FATAL: cannot resolve this script's own directory" >&2
  exit 127
}
case "$SCRIPT_DIR" in
  */*) REPO_ROOT="${SCRIPT_DIR%/*}" ;;
  *) REPO_ROOT="/" ;;
esac
cd "$REPO_ROOT" || {
  echo "gitreins_tests: FATAL: cannot cd to repo root '$REPO_ROOT'" >&2
  exit 127
}

TRIED=""

note_tried() {
  TRIED="${TRIED}        $1 -> $2
"
}

probe() {
  # probe <label> <cmd...> — prints the version line on success, nothing on
  # failure (and records the attempt for the final report). First line is taken
  # with pure-bash expansion, not `head`, so a PATH-less environment still gets
  # the honest "no runner" verdict instead of a coreutils error.
  local label="$1"
  shift
  local out
  out="$("$@" --version 2>/dev/null)"
  out="${out%%$'\n'*}"
  if [ -n "$out" ]; then
    printf '%s\n' "$out"
    return 0
  fi
  note_tried "$label" "found but not runnable (--version failed)"
  return 1
}

# 1. The operator/CI interpreter.
if [ -x "./venv/bin/pytest" ]; then
  if v="$(probe './venv/bin/pytest' ./venv/bin/pytest)"; then
    echo "gitreins_tests: runner=./venv/bin/pytest ($v) cwd=$REPO_ROOT"
    exec ./venv/bin/pytest "$@"
  fi
else
  note_tried "./venv/bin/pytest" "missing"
fi

# 2. A uv-created worktree venv.
if [ -x "./.venv/bin/python" ]; then
  if v="$(probe './.venv/bin/python -m pytest' ./.venv/bin/python -m pytest)"; then
    echo "gitreins_tests: runner=./.venv/bin/python -m pytest ($v) cwd=$REPO_ROOT"
    exec ./.venv/bin/python -m pytest "$@"
  fi
else
  note_tried "./.venv/bin/python -m pytest" "missing (no ./.venv/bin/python)"
fi

# 3. Any PATH interpreter that can import pytest.
for interp in python python3; do
  if ! command -v "$interp" >/dev/null 2>&1; then
    note_tried "$interp -m pytest" "no '$interp' on PATH"
    continue
  fi
  if v="$(probe "$interp -m pytest" "$interp" -m pytest)"; then
    echo "gitreins_tests: runner=$interp -m pytest ($v) cwd=$REPO_ROOT"
    exec "$interp" -m pytest "$@"
  fi
done

# The failure report uses printf ONLY (a shell builtin): a checkout whose PATH
# is so broken that even `cat` is missing must still get the honest verdict
# instead of a "command not found" from this script.
{
  printf '%s\n' "gitreins_tests: FATAL: no usable pytest runner in this checkout ($REPO_ROOT)."
  printf '%s\n' "gitreins_tests: looked for, in order:"
  printf '%s' "$TRIED"
  printf '%s\n' "gitreins_tests: GITREINS_SKIP-style gap: the tests cell graded NOTHING here."
  printf '%s\n' "gitreins_tests: provision one of: ./venv (uv venv venv && uv pip install -e '.[dev]'),"
  printf '%s\n' "gitreins_tests:   ./.venv (same, uv's default name), or a PATH interpreter with pytest"
  printf '%s\n' "gitreins_tests:   (python -m pip install pytest) — a judge worktree needs the repo's"
  printf '%s\n' "gitreins_tests:   test deps too, not just pytest."
  printf '%s\n' "gitreins_tests: exit 127 (environment gap — deliberately NOT a pass)"
} >&2
exit 127
