# Verdict: GAP-052

**Task:** LLM escape hatch: --controller-model flag + CRON_CONTROLLER_MODEL env + think-token strip + parse-failure retry
**Evaluated:** 2026-09-23T16:20:03.785312
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✗ **tier2**
  - INCOMPLETE
  ✗ with OPENROUTER_API_KEY unset/dead and --controller-model deepseek-chat, a 20-cycle run records >=15/20 successful LLM decisions in cron_logs/run_<id>.jsonl: The enabling code exists and is unit-verified, but the criterion's required end-to-end artifact does not exist. (a) Code path present: cron_runner.py:53-84 resolve_controller_model (flag > CRON_CONTROLLER_MODEL > POKE_CONTROLLER_MODEL > default), cron_runner.py:368 --controller-model argparse, cron_runner.py:1183 resolved_model -> client.chat_completion, cron_runner.py:1313-1341 _strip_model_noise + _interpret_controller_response + single retry at max_tokens+100; src/core/ai_client.py:533-536 routes any '*deepseek*' model to api.deepseek.com with DEEPSEEK_API_KEY. (b) Scripted-client probe confirms behavior: controller_plan(model='deepseek-chat') sends model=deepseek-chat/max_tokens=300, and '{"plan":["UP","RIGHT"],"intent":"head north"}<|endoftext|>' parses to a real plan (not parse_fallback); garbage-then-good triggers exactly 1 retry at max_tokens=400. (c) NO RUN ARTIFACT: `find cron_logs -name '*.jsonl' -newermt '2026-09-23 10:49'` returns EMPTY; newest jsonl is cron_logs/run_dgf_0923b.jsonl (Sep 23 05:24), predating the GAP-052 commit d5919fb (Sep 23 10:49). grep for 'deepseek-chat' across all 617 cron_logs files matches only run_20260724_123131.jsonl (a July run that errored with OpenRouter 400 'you passed deepseek-chat'). No cron_logs/run_<id>.jsonl from a --controller-model deepseek-chat run exists. (d) NO TEST asserts the >=15/20 outcome: `./venv/bin/pytest tests/test_gap052_controller_model.py tests/test_gap053_decision_intent_summary.py -q` -> exit_code 0, '50 passed in 0.85s', but all 50 are scripted-client unit tests (model precedence, strip/extract, retry, intent classification) with no 20-cycle run and no JSONL decision count; grep for 'cron_runner.main|subprocess.*cron_runner' in tests/ returns nothing. (e) docs/dogfood/2026-09-09b-integration.md:40 documents only the pre-fix state ('20 cycle rows with zero llm_status fields ... No successful LLM call'); no post-fix dogfood run exists. The criterion demands a recorded 20-cycle run with >=15/20 successful LLM decisions; that evidence is absent, so the criterion is not met.
The --controller-model/CRON_CONTROLLER_MODEL escape hatch, think-token strip and parse-failure retry are implemented and pass 50 scripted unit tests, but no 20-cycle run artifact (or test) demonstrating >=15/20 successful LLM decisions with a dead OpenRouter key exists in cron_logs/, so the sole criterion fails.

## Summary

Judge Result: GAP-052

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: FAIL
  INCOMPLETE
  ✗ with OPENROUTER_API_KEY unset/dead and --controller-model deepseek-chat, a 20-cycle run records >=15/20 successful LLM decisions in cron_logs/run_<id>.jsonl: The enabling code exists and is unit-verified, but the criterion's required end-to-end artifact does not exist. (a) Code path present: cron_runner.py:53-84 resolve_controller_model (flag > CRON_CONTROLLER_MODEL > POKE_CONTROLLER_MODEL > default), cron_runner.py:368 --controller-model argparse, cron_runner.py:1183 resolved_model -> client.chat_completion, cron_runner.py:1313-1341 _strip_model_noise + _interpret_controller_response + single retry at max_tokens+100; src/core/ai_client.py:533-536 routes any '*deepseek*' model to api.deepseek.com with DEEPSEEK_API_KEY. (b) Scripted-client probe confirms behavior: controller_plan(model='deepseek-chat') sends model=deepseek-chat/max_tokens=300, and '{"plan":["UP","RIGHT"],"intent":"head north"}<|endoftext|>' parses to a real plan (not parse_fallback); garbage-then-good triggers exactly 1 retry at max_tokens=400. (c) NO RUN ARTIFACT: `find cron_logs -name '*.jsonl' -newermt '2026-09-23 10:49'` returns EMPTY; newest jsonl is cron_logs/run_dgf_0923b.jsonl (Sep 23 05:24), predating the GAP-052 commit d5919fb (Sep 23 10:49). grep for 'deepseek-chat' across all 617 cron_logs files matches only run_20260724_123131.jsonl (a July run that errored with OpenRouter 400 'you passed deepseek-chat'). No cron_logs/run_<id>.jsonl from a --controller-model deepseek-chat run exists. (d) NO TEST asserts the >=15/20 outcome: `./venv/bin/pytest tests/test_gap052_controller_model.py tests/test_gap053_decision_intent_summary.py -q` -> exit_code 0, '50 passed in 0.85s', but all 50 are scripted-client unit tests (model precedence, strip/extract, retry, intent classification) with no 20-cycle run and no JSONL decision count; grep for 'cron_runner.main|subprocess.*cron_runner' in tests/ returns nothing. (e) docs/dogfood/2026-09-09b-integration.md:40 documents only the pre-fix state ('20 cycle rows with zero llm_status fields ... No successful LLM call'); no post-fix dogfood run exists. The criterion demands a recorded 20-cycle run with >=15/20 successful LLM decisions; that evidence is absent, so the criterion is not met.
The --controller-model/CRON_CONTROLLER_MODEL escape hatch, think-token strip and parse-failure retry are implemented and pass 50 scripted unit tests, but no 20-cycle run artifact (or test) demonstrating >=15/20 successful LLM decisions with a dead OpenRouter key exists in cron_logs/, so the sole criterion fails.

Overall: FAIL ✗
