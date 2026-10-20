# Support

AI Plays Pokémon is an experimental research and gameplay-automation project. Start with the README and the documentation under `docs/` before opening a support request.

## Before asking for help

1. Use the project virtual environment (`.venv`) and install both runtime and development requirements.
2. Run `cron_runner.py --dry-run` to check the configured paths and environment without starting a game or making model calls.
3. Confirm that you supplied your own legally obtained Pokémon ROM; ROM files are not distributed with this repository.
4. Remove API keys, tokens, save files, screenshots, and other private data from logs before sharing them.
5. Check existing GitHub issues for the same error and include the exact command and exit status if it is not already reported.

## Reporting a bug

Open a GitHub issue with:

- a short, specific title;
- the command or minimal reproduction;
- expected and actual behavior;
- the relevant error message or traceback;
- operating system, Python version, project commit, and ROM variant;
- whether the issue occurs with `cron_runner.py`, the legacy `game_loop.py` path, the dashboard, or the MCP bridge;
- a sanitized log excerpt and any test command that reproduces the problem.

Do not attach credentials, API keys, complete save files, or copyrighted ROM data.

## Security issues

Do not report security vulnerabilities in a public issue. Follow the private-reporting guidance in `SECURITY.md` instead.

## Scope and expectations

This project is maintained on a best-effort basis. Reproduction steps and small, focused pull requests are easier to review. A support request does not guarantee a particular response time or feature implementation.

## Useful checks

```bash
.venv/bin/python cron_runner.py --dry-run
.venv/bin/python -m pytest tests/ --collect-only -q
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/ --ignore-missing-imports
```
