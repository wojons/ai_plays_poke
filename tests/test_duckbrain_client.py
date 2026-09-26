"""Unit tests for duckbrain_client.py — remember, recall, list_keys."""

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

# Monkeypatch DUCKBRAIN_ROOT before importing the module
import src.core.duckbrain_client as dbc


@pytest.fixture
def duckbrain_tmp(monkeypatch, tmp_path):
    """Redirect DUCKBRAIN_ROOT to a temp dir for isolated tests."""
    monkeypatch.setattr(dbc, "DUCKBRAIN_ROOT", tmp_path)
    return tmp_path


def _write_jsonl(data_dir: Path, date_str: str, records: list[dict]) -> Path:
    """Write a JSONL file with the given records."""
    p = data_dir / f"memories-{date_str}.jsonl"
    with open(p, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return p


# ── _ensure_namespace ────────────────────────────────────────────────


class TestEnsureNamespace:
    def test_creates_data_dir(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-ns")
        assert data_dir.exists()
        assert data_dir.name == "data"

    def test_returns_correct_path(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("pokemon-global")
        expected = duckbrain_tmp / "pokemon-global" / "data"
        assert data_dir == expected

    def test_idempotent(self, duckbrain_tmp):
        d1 = dbc._ensure_namespace("ns1")
        d2 = dbc._ensure_namespace("ns1")
        assert d1 == d2


# ── remember ─────────────────────────────────────────────────────────


class TestRemember:
    def test_returns_uuid_string(self, duckbrain_tmp):
        mem_id = dbc.remember(
            key="/test/key",
            domain="concept",
            attributes={"value": 42},
            embedding_text="test memory",
        )
        assert isinstance(mem_id, str)
        assert len(mem_id) == 36  # UUID4 format
        assert mem_id.count("-") == 4

    def test_creates_jsonl_file(self, duckbrain_tmp):
        dbc.remember(
            key="/create/file",
            domain="event",
            attributes={},
            embedding_text="file test",
        )
        data_dir = duckbrain_tmp / "pokemon-global" / "data"
        files = list(data_dir.glob("memories-*.jsonl"))
        assert len(files) == 1

    def test_appends_to_existing_file(self, duckbrain_tmp):
        dbc.remember(key="/k1", domain="concept", attributes={}, embedding_text="m1")
        dbc.remember(key="/k2", domain="concept", attributes={}, embedding_text="m2")
        data_dir = duckbrain_tmp / "pokemon-global" / "data"
        files = list(data_dir.glob("memories-*.jsonl"))
        assert len(files) == 1  # same day → same file

    def test_jsonl_contains_correct_record(self, duckbrain_tmp):
        mem_id = dbc.remember(
            key="/test/jsonl",
            domain="event",
            attributes={"a": 1, "b": "two"},
            embedding_text="jsonl test",
        )
        data_dir = duckbrain_tmp / "pokemon-global" / "data"
        files = list(data_dir.glob("memories-*.jsonl"))
        lines = files[0].read_text().strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[-1])
        assert record["id"] == mem_id
        assert record["key"] == "/test/jsonl"
        assert record["domain"] == "event"
        assert record["attributes"] == {"a": 1, "b": "two"}
        assert record["embedding_text"] == "jsonl test"
        assert record["status"] == "active"

    def test_normalizes_key_without_leading_slash(self, duckbrain_tmp):
        dbc.remember(
            key="no-leading-slash",
            domain="raw_note",
            attributes={},
            embedding_text="normalize",
        )
        data_dir = duckbrain_tmp / "pokemon-global" / "data"
        files = list(data_dir.glob("memories-*.jsonl"))
        record = json.loads(files[0].read_text().strip())
        assert record["key"] == "/no-leading-slash"

    def test_custom_namespace(self, duckbrain_tmp):
        dbc.remember(
            key="/custom/ns",
            domain="config",
            attributes={},
            embedding_text="custom",
            namespace="my-ns",
        )
        data_dir = duckbrain_tmp / "my-ns" / "data"
        assert data_dir.exists()
        files = list(data_dir.glob("memories-*.jsonl"))
        assert len(files) == 1

    def test_distinct_uuids(self, duckbrain_tmp):
        id1 = dbc.remember(
            key="/u1", domain="concept", attributes={}, embedding_text="a"
        )
        id2 = dbc.remember(
            key="/u2", domain="concept", attributes={}, embedding_text="b"
        )
        assert id1 != id2

    def test_persists_optional_memory_contract_fields(self, duckbrain_tmp):
        labels = ["world", "visited"]
        evidence = {"run_id": "run-7", "cycle": 12, "tile": {"x": 3, "y": 4}}
        applies_when = {"screen": "overworld", "map_id": 1}

        dbc.remember(
            key="/world/map/1",
            domain="world/map/1",
            attributes={"exit": "north"},
            embedding_text="Pallet Town has a northern exit",
            labels=labels,
            confidence=0.875,
            evidence=evidence,
            applies_when=applies_when,
        )

        data_dir = duckbrain_tmp / "pokemon-global" / "data"
        record = json.loads(next(data_dir.glob("memories-*.jsonl")).read_text())
        assert record["labels"] == labels
        assert record["confidence"] == 0.875
        assert record["evidence"] == evidence
        assert record["applies_when"] == applies_when

    def test_omits_optional_memory_contract_fields_when_not_provided(
        self, duckbrain_tmp
    ):
        dbc.remember(
            key="/legacy/shape",
            domain="concept",
            attributes={"value": 1},
            embedding_text="legacy record",
        )

        data_dir = duckbrain_tmp / "pokemon-global" / "data"
        record = json.loads(next(data_dir.glob("memories-*.jsonl")).read_text())
        optional_fields = {"labels", "confidence", "evidence", "applies_when"}
        assert optional_fields.isdisjoint(record)


# ── recall ───────────────────────────────────────────────────────────


class TestRecall:
    def test_empty_namespace_returns_empty_list(self, duckbrain_tmp):
        results = dbc.recall(namespace="empty-ns")
        assert results == []

    def test_recall_all(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-recall")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/a",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/b",
                    "domain": "event",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        results = dbc.recall(namespace="test-recall")
        assert len(results) == 2

    def test_filter_by_key(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-key")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/exact/match",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/other",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        results = dbc.recall(key="/exact/match", namespace="test-key")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_filter_by_key_prefix(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-prefix")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/projects/mcp",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/projects/spec",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "3",
                    "key": "/other",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        results = dbc.recall(key_prefix="/projects", namespace="test-prefix")
        assert len(results) == 2

    def test_filter_by_domain(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-domain")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/a",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/b",
                    "domain": "event",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "3",
                    "key": "/c",
                    "domain": "event",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        results = dbc.recall(domain="event", namespace="test-domain")
        assert len(results) == 2

    def test_limit(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-limit")
        records = [
            {
                "id": str(i),
                "key": f"/k{i}",
                "domain": "concept",
                "attributes": {},
                "status": "active",
            }
            for i in range(10)
        ]
        _write_jsonl(data_dir, "2026-06-25", records)
        results = dbc.recall(limit=3, namespace="test-limit")
        assert len(results) == 3

    def test_skips_tombstones(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-tombstone")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/alive",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/dead",
                    "domain": "concept",
                    "attributes": {},
                    "status": "deleted",
                },
            ],
        )
        results = dbc.recall(namespace="test-tombstone")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_skips_corrupt_json(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-corrupt")
        jsonl_path = data_dir / "memories-2026-06-25.jsonl"
        jsonl_path.write_text(
            '{"id":"1","key":"/good","domain":"concept","attributes":{},"status":"active"}\n'
            "this is not json\n"
            '{"id":"2","key":"/also-good","domain":"concept","attributes":{},"status":"active"}\n'
        )
        results = dbc.recall(namespace="test-corrupt")
        assert len(results) == 2

    def test_skips_empty_lines(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-empty")
        jsonl_path = data_dir / "memories-2026-06-25.jsonl"
        jsonl_path.write_text(
            "\n"
            '{"id":"1","key":"/only","domain":"concept","attributes":{},"status":"active"}\n'
            "\n"
        )
        results = dbc.recall(namespace="test-empty")
        assert len(results) == 1

    def test_handles_missing_data_dir(self, duckbrain_tmp):
        results = dbc.recall(namespace="nonexistent-ns")
        assert results == []

    def test_key_and_key_prefix_mutually_filter(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-both")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/exact",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/exact/other",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        # key= takes priority — must be exact match
        results = dbc.recall(key="/exact", key_prefix="/exact", namespace="test-both")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_reads_multiple_jsonl_files(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-multi")
        _write_jsonl(
            data_dir,
            "2026-06-24",
            [
                {
                    "id": "1",
                    "key": "/old",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "2",
                    "key": "/new",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        results = dbc.recall(namespace="test-multi")
        assert len(results) == 2

    def test_filter_by_labels_requires_all_requested_labels(self, duckbrain_tmp):
        namespace = "test-label-and"
        dbc.remember(
            key="/both",
            domain="world/map/1",
            attributes={},
            embedding_text="both labels",
            namespace=namespace,
            labels=["world", "visited"],
        )
        dbc.remember(
            key="/world-only",
            domain="world/map/2",
            attributes={},
            embedding_text="one label",
            namespace=namespace,
            labels=["world"],
        )
        dbc.remember(
            key="/visited-only",
            domain="other",
            attributes={},
            embedding_text="other label",
            namespace=namespace,
            labels=["visited"],
        )

        results = dbc.recall(labels=["world", "visited"], namespace=namespace)
        assert [record["key"] for record in results] == ["/both"]

    def test_domain_counts_as_a_label(self, duckbrain_tmp):
        namespace = "test-domain-label"
        dbc.remember(
            key="/domain-label",
            domain="world/map/1",
            attributes={},
            embedding_text="domain label",
            namespace=namespace,
            labels=["visited"],
        )
        dbc.remember(
            key="/wrong-domain",
            domain="world/map/2",
            attributes={},
            embedding_text="wrong domain",
            namespace=namespace,
            labels=["visited"],
        )

        results = dbc.recall(labels=["visited", "world/map/1"], namespace=namespace)
        assert [record["key"] for record in results] == ["/domain-label"]

    def test_labels_none_preserves_unfiltered_recall(self, duckbrain_tmp):
        namespace = "test-label-default"
        dbc.remember(
            key="/labeled",
            domain="concept",
            attributes={},
            embedding_text="labeled",
            namespace=namespace,
            labels=["one"],
        )
        dbc.remember(
            key="/unlabeled",
            domain="concept",
            attributes={},
            embedding_text="unlabeled",
            namespace=namespace,
        )

        assert dbc.recall(namespace=namespace) == dbc.recall(
            labels=None, namespace=namespace
        )


class TestRestartSafeRetrieval:
    def test_key_label_and_similarity_retrieval_survive_restart(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        writer = """
from src.core import duckbrain_client as dbc

dbc.remember(
    key="/world/map/1",
    domain="world/map/1",
    attributes={"exit": "north"},
    embedding_text="Pallet Town northern exit reaches Route 1",
    labels=["world", "visited"],
)
"""
        subprocess.run(
            [sys.executable, "-c", writer],
            cwd=repo_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        reader = """
import json
from src.core import duckbrain_client as dbc

print(json.dumps({
    "by_key": dbc.get("/world/map/1"),
    "by_label": dbc.recall(labels=["world", "world/map/1"]),
    "by_similarity": dbc.search("northern exit"),
}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", reader],
            cwd=repo_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        retrieved = json.loads(completed.stdout)

        assert retrieved["by_key"]["key"] == "/world/map/1"
        assert [record["key"] for record in retrieved["by_label"]] == ["/world/map/1"]
        assert [record["key"] for record in retrieved["by_similarity"]] == [
            "/world/map/1"
        ]


# ── list_keys ────────────────────────────────────────────────────────


class TestListKeys:
    def test_empty_namespace_returns_empty(self, duckbrain_tmp):
        keys = dbc.list_keys(namespace="empty-keys")
        assert keys == []

    def test_lists_unique_keys(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-keys")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/a/b",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/a/c",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "3",
                    "key": "/d",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        keys = dbc.list_keys(namespace="test-keys")
        assert "/a/b" in keys
        assert "/a/c" in keys
        assert "/d" in keys

    def test_filter_by_prefix(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-prefix-keys")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/projects/a",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/projects/b",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "3",
                    "key": "/other",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        keys = dbc.list_keys(prefix="/projects", namespace="test-prefix-keys")
        assert len(keys) == 2
        assert "/projects/a" in keys
        assert "/projects/b" in keys
        assert "/other" not in keys

    def test_truncation_warns_and_logs_correct_lower_bound(self, duckbrain_tmp, caplog):
        data_dir = dbc._ensure_namespace("test-limit-keys")
        records = [
            {
                "id": str(i),
                "key": f"/k{i}",
                "domain": "concept",
                "attributes": {},
                "status": "active",
            }
            for i in range(10)
        ]
        _write_jsonl(data_dir, "2026-06-25", records)

        message = (
            "list_keys truncated: returned 3 of >= 4 matching keys (limit=3); "
            "pass a larger limit for a full census"
        )
        with pytest.warns(
            UserWarning, match=message.replace("(", r"\(").replace(")", r"\)")
        ):
            keys = dbc.list_keys(limit=3, namespace="test-limit-keys")

        assert len(keys) == 3
        assert message in caplog.messages

    def test_exact_limit_does_not_warn(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-exact-limit-keys")
        records = [
            {
                "id": str(i),
                "key": f"/k{i}",
                "domain": "concept",
                "attributes": {},
                "status": "active",
            }
            for i in range(3)
        ]
        _write_jsonl(data_dir, "2026-06-25", records)

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            keys = dbc.list_keys(limit=3, namespace="test-exact-limit-keys")

        assert keys == ["/k0", "/k1", "/k2"]
        assert not captured

    def test_one_past_cap_does_not_change_returned_keys(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-one-past-keys")
        records = [
            {
                "id": str(i),
                "key": key,
                "domain": "concept",
                "attributes": {},
                "status": "active",
            }
            for i, key in enumerate(("/b", "/c", "/a"))
        ]
        _write_jsonl(data_dir, "2026-06-25", records)

        with pytest.warns(UserWarning, match=r"returned 2 of >= 3 matching keys"):
            keys = dbc.list_keys(limit=2, namespace="test-one-past-keys")

        # The one-past key (/a) detects truncation but must not displace /b or /c.
        assert keys == ["/b", "/c"]

    def test_skips_tombstones(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-keys-tomb")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/alive",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/dead",
                    "domain": "concept",
                    "attributes": {},
                    "status": "deleted",
                },
            ],
        )
        keys = dbc.list_keys(namespace="test-keys-tomb")
        assert "/alive" in keys
        assert "/dead" not in keys

    def test_returns_sorted(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-sorted")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/z",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/a",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "3",
                    "key": "/m",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        keys = dbc.list_keys(namespace="test-sorted")
        assert keys == ["/a", "/m", "/z"]

    def test_handles_missing_data_dir(self, duckbrain_tmp):
        keys = dbc.list_keys(namespace="nonexistent-ns")
        assert keys == []

    def test_default_prefix_is_root_slash(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-default-prefix")
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "1",
                    "key": "/any",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
                {
                    "id": "2",
                    "key": "/path",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        keys = dbc.list_keys(namespace="test-default-prefix")
        assert len(keys) == 2

    def test_deduplicates_across_files(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-dedup")
        _write_jsonl(
            data_dir,
            "2026-06-24",
            [
                {
                    "id": "1",
                    "key": "/dup",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        _write_jsonl(
            data_dir,
            "2026-06-25",
            [
                {
                    "id": "2",
                    "key": "/dup",
                    "domain": "concept",
                    "attributes": {},
                    "status": "active",
                },
            ],
        )
        keys = dbc.list_keys(namespace="test-dedup")
        assert keys == ["/dup"]  # deduplicated
