PYTHON ?= $(firstword $(wildcard venv/bin/python .venv/bin/python) python3)

.PHONY: docs-check qa-console qa-console-dry-run

docs-check:
	$(PYTHON) tools/check_docs.py README.md

qa-console:
	$(PYTHON) tools/console/run_qa.py

qa-console-dry-run:
	$(PYTHON) tools/console/run_qa.py --dry-run
