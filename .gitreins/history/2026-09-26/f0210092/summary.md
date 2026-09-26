# Verdict: GUARD-1

**Task:** Guard fail-open on hook timeout - make the verdict load-independent
**Evaluated:** 2026-09-26T14:18:06.714993
**Result:** ✓ PASS

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ 1. .gitreins/config.yaml: guards.allow_skips=false and guards.hook_timeout raised to 900 (suite measured 368s under load vs 300s window); lsp guard resolved so ordinary green commits still pass. 2. scripts/hooks/pre-commit (tracked, executable): wraps gitreins guard fail-closed - timeout output exits 1, missing verdict exits 1, otherwise passes the guard exit code through; active in this clone via a shim in .git/hooks/pre-commit. 3. tests/test_precommit_hook.py proves wrapper behavior with a fake guard (pass-through / timeout-reject / no-verdict-reject / uninit-allow). 4. Focused tests + ruff clean.: Config: .gitreins/config.yaml:10 'hook_timeout: 900', :16 'allow_skips: false' (commit 344242a diff shows allow_skips true->false, hook_timeout added, test_command ./.venv/bin/pytest). lsp resolved: newest guard log .gitreins/logs/guard-20260926T141038.846114Z.log shows '[PASS] lsp passed=true', 'overall: PASS', 'guards: 5 (0 failed, 0 skipped)'; .venv/bin/pylsp v1.15.0 present and python-lsp-server added to requirements-dev.txt. Wrapper: scripts/hooks/pre-commit tracked (git ls-files) with git mode 100755 (executable); end-to-end fake-guard test: timeout output rc=0 -> exit 1, clean pass no verdict -> exit 1, guard rc=2 -> exit 2 (pass-through), clean pass + fresh verdict -> exit 0; shim .git/hooks/pre-commit (executable) execs the tracked wrapper. Tests: tests/test_precommit_hook.py has 7 tests covering pass-through (accepts_clean_guard_with_fresh_verdict, preserves_guard_failure_exit_code), timeout-reject (rejects_fail_open_timeout), no-verdict-reject (rejects_missing_fresh_verdict, rejects_stale_verdict), uninit-allow (allows_repo_without_gitreins_config), plus tracked_wrapper_is_executable. Verification: './.venv/bin/pytest tests/test_precommit_hook.py -v' -> '7 passed in 0.30s'; './.venv/bin/ruff check tests/test_precommit_hook.py' -> 'All checks passed!' RC=0; 'bash -n scripts/hooks/pre-commit' -> OK. [resolution 0.37; tests/test_precommit_hook.py]
All four GUARD-1 criteria verified: config fail-closed with hook_timeout=900 and lsp guard passing (5/5 guards, 0 skipped), tracked executable fail-closed wrapper with shim active, 7 passing wrapper tests, and ruff clean.

## Summary

Judge Result: GUARD-1

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ 1. .gitreins/config.yaml: guards.allow_skips=false and guards.hook_timeout raised to 900 (suite measured 368s under load vs 300s window); lsp guard resolved so ordinary green commits still pass. 2. scripts/hooks/pre-commit (tracked, executable): wraps gitreins guard fail-closed - timeout output exits 1, missing verdict exits 1, otherwise passes the guard exit code through; active in this clone via a shim in .git/hooks/pre-commit. 3. tests/test_precommit_hook.py proves wrapper behavior with a fake guard (pass-through / timeout-reject / no-verdict-reject / uninit-allow). 4. Focused tests + ruff clean.: Config: .gitreins/config.yaml:10 'hook_timeout: 900', :16 'allow_skips: false' (commit 344242a diff shows allow_skips true->false, hook_timeout added, test_command ./.venv/bin/pytest). lsp resolved: newest guard log .gitreins/logs/guard-20260926T141038.846114Z.log shows '[PASS] lsp passed=true', 'overall: PASS', 'guards: 5 (0 failed, 0 skipped)'; .venv/bin/pylsp v1.15.0 present and python-lsp-server added to requirements-dev.txt. Wrapper: scripts/hooks/pre-commit tracked (git ls-files) with git mode 100755 (executable); end-to-end fake-guard test: timeout output rc=0 -> exit 1, clean pass no verdict -> exit 1, guard rc=2 -> exit 2 (pass-through), clean pass + fresh verdict -> exit 0; shim .git/hooks/pre-commit (executable) execs the tracked wrapper. Tests: tests/test_precommit_hook.py has 7 tests covering pass-through (accepts_clean_guard_with_fresh_verdict, preserves_guard_failure_exit_code), timeout-reject (rejects_fail_open_timeout), no-verdict-reject (rejects_missing_fresh_verdict, rejects_stale_verdict), uninit-allow (allows_repo_without_gitreins_config), plus tracked_wrapper_is_executable. Verification: './.venv/bin/pytest tests/test_precommit_hook.py -v' -> '7 passed in 0.30s'; './.venv/bin/ruff check tests/test_precommit_hook.py' -> 'All checks passed!' RC=0; 'bash -n scripts/hooks/pre-commit' -> OK. [resolution 0.37; tests/test_precommit_hook.py]
All four GUARD-1 criteria verified: config fail-closed with hook_timeout=900 and lsp guard passing (5/5 guards, 0 skipped), tracked executable fail-closed wrapper with shim active, 7 passing wrapper tests, and ruff clean.

Overall: PASS ✓
