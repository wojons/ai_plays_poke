PYTHON ?= $(firstword $(wildcard venv/bin/python .venv/bin/python) python3)

.PHONY: qa-console qa-console-dry-run

qa-console:
	$(PYTHON) tools/console/run_qa.py

qa-console-dry-run:
	$(PYTHON) tools/console/run_qa.py --dry-run
