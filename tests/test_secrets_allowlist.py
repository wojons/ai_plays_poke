"""INT-GL-1: the .gitleaks.toml path allowlist must cover the deployment
artifacts the gitreins Tier 1 full-tree secrets scan grades.

Tier 1 grades every file in the tree — the built-in cross-check walks the
workdir and gitleaks runs ``detect --no-git`` — so neither scanner honours
.gitignore. Local env files (live keys), generated review reports (base64 image
payloads that trip the AWS-key pattern) and the dashboard's static bundle were
therefore scanned as if they were repo code; the path allowlist is what keeps
them out of the gate without silencing the rest of the tree.

The allowlist is parsed with the same ``'''...'''`` literal-string semantics both
consumers use (gitleaks compiles the entries as RE2, the built-in scanner
compiles them with Python ``re``), so these assertions fail if an entry stops
matching — or if a broad entry starts matching unrelated sources.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"


def _allowlist_patterns() -> list[str]:
    data = tomllib.loads(GITLEAKS_CONFIG.read_text(encoding="utf-8"))
    return [str(entry) for entry in data["allowlist"]["paths"]]


def _is_allowlisted(rel_path: str) -> bool:
    return any(re.search(pattern, rel_path) for pattern in _allowlist_patterns())


class TestGitleaksAllowlist:
    def test_every_pattern_compiles(self):
        for pattern in _allowlist_patterns():
            re.compile(pattern)  # re.error on a botched entry

    def test_env_files_are_allowlisted(self):
        assert _is_allowlisted(".env")
        assert _is_allowlisted(".env.bak-20260923-021900")
        assert _is_allowlisted("config/.env")
        assert _is_allowlisted("config/.env.bak-20240101-000000")

    def test_review_reports_are_allowlisted(self):
        assert _is_allowlisted("review_battlefix_win1.html")
        assert _is_allowlisted("notes/review_prd.html")

    def test_dashboard_static_bundle_is_allowlisted(self):
        assert _is_allowlisted("src/dashboard/static/index.html")

    def test_unrelated_sources_are_still_scanned(self):
        # Non-vacuity: the allowlist must not have collapsed into a blanket
        # exemption. Every path here must keep reaching both scanners.
        for path in (
            ".env.example",
            "src/dashboard/main.py",
            "src/core/game_loop.py",
            "tests/test_dashboard.py",
            "README.md",
            "cron_runner.py",
            "review_notes.txt",
        ):
            assert not _is_allowlisted(path), path

    def test_env_allowlist_does_not_swallow_prefix_matches(self):
        # An unanchored `\.env` entry would also exempt e.g. `.environment.md`.
        assert not _is_allowlisted(".environment.md")
        assert not _is_allowlisted("config/.envrc")
