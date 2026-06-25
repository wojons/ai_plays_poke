"""Unit tests for duckbrain_client.py — remember, recall, list_keys."""

import json
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
        mem_id = dbc.remember(
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
        id1 = dbc.remember(key="/u1", domain="concept", attributes={}, embedding_text="a")
        id2 = dbc.remember(key="/u2", domain="concept", attributes={}, embedding_text="b")
        assert id1 != id2


# ── recall ───────────────────────────────────────────────────────────

class TestRecall:
    def test_empty_namespace_returns_empty_list(self, duckbrain_tmp):
        results = dbc.recall(namespace="empty-ns")
        assert results == []

    def test_recall_all(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-recall")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/a", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/b", "domain": "event", "attributes": {}, "status": "active"},
        ])
        results = dbc.recall(namespace="test-recall")
        assert len(results) == 2

    def test_filter_by_key(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-key")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/exact/match", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/other", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        results = dbc.recall(key="/exact/match", namespace="test-key")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_filter_by_key_prefix(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-prefix")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/projects/mcp", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/projects/spec", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "3", "key": "/other", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        results = dbc.recall(key_prefix="/projects", namespace="test-prefix")
        assert len(results) == 2

    def test_filter_by_domain(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-domain")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/a", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/b", "domain": "event", "attributes": {}, "status": "active"},
            {"id": "3", "key": "/c", "domain": "event", "attributes": {}, "status": "active"},
        ])
        results = dbc.recall(domain="event", namespace="test-domain")
        assert len(results) == 2

    def test_limit(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-limit")
        records = [
            {"id": str(i), "key": f"/k{i}", "domain": "concept", "attributes": {}, "status": "active"}
            for i in range(10)
        ]
        _write_jsonl(data_dir, "2026-06-25", records)
        results = dbc.recall(limit=3, namespace="test-limit")
        assert len(results) == 3

    def test_skips_tombstones(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-tombstone")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/alive", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/dead", "domain": "concept", "attributes": {}, "status": "deleted"},
        ])
        results = dbc.recall(namespace="test-tombstone")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_skips_corrupt_json(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-corrupt")
        jsonl_path = data_dir / "memories-2026-06-25.jsonl"
        jsonl_path.write_text(
            '{"id":"1","key":"/good","domain":"concept","attributes":{},"status":"active"}\n'
            'this is not json\n'
            '{"id":"2","key":"/also-good","domain":"concept","attributes":{},"status":"active"}\n'
        )
        results = dbc.recall(namespace="test-corrupt")
        assert len(results) == 2

    def test_skips_empty_lines(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-empty")
        jsonl_path = data_dir / "memories-2026-06-25.jsonl"
        jsonl_path.write_text(
            '\n'
            '{"id":"1","key":"/only","domain":"concept","attributes":{},"status":"active"}\n'
            '\n'
        )
        results = dbc.recall(namespace="test-empty")
        assert len(results) == 1

    def test_handles_missing_data_dir(self, duckbrain_tmp):
        results = dbc.recall(namespace="nonexistent-ns")
        assert results == []

    def test_key_and_key_prefix_mutually_filter(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-both")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/exact", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/exact/other", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        # key= takes priority — must be exact match
        results = dbc.recall(key="/exact", key_prefix="/exact", namespace="test-both")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_reads_multiple_jsonl_files(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-multi")
        _write_jsonl(data_dir, "2026-06-24", [
            {"id": "1", "key": "/old", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "2", "key": "/new", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        results = dbc.recall(namespace="test-multi")
        assert len(results) == 2


# ── list_keys ────────────────────────────────────────────────────────

class TestListKeys:
    def test_empty_namespace_returns_empty(self, duckbrain_tmp):
        keys = dbc.list_keys(namespace="empty-keys")
        assert keys == []

    def test_lists_unique_keys(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-keys")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/a/b", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/a/c", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "3", "key": "/d", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        keys = dbc.list_keys(namespace="test-keys")
        assert "/a/b" in keys
        assert "/a/c" in keys
        assert "/d" in keys

    def test_filter_by_prefix(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-prefix-keys")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/projects/a", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/projects/b", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "3", "key": "/other", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        keys = dbc.list_keys(prefix="/projects", namespace="test-prefix-keys")
        assert len(keys) == 2
        assert "/projects/a" in keys
        assert "/projects/b" in keys
        assert "/other" not in keys

    def test_respects_limit(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-limit-keys")
        records = [
            {"id": str(i), "key": f"/k{i}", "domain": "concept", "attributes": {}, "status": "active"}
            for i in range(10)
        ]
        _write_jsonl(data_dir, "2026-06-25", records)
        keys = dbc.list_keys(limit=3, namespace="test-limit-keys")
        assert len(keys) == 3

    def test_skips_tombstones(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-keys-tomb")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/alive", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/dead", "domain": "concept", "attributes": {}, "status": "deleted"},
        ])
        keys = dbc.list_keys(namespace="test-keys-tomb")
        assert "/alive" in keys
        assert "/dead" not in keys

    def test_returns_sorted(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-sorted")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/z", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/a", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "3", "key": "/m", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        keys = dbc.list_keys(namespace="test-sorted")
        assert keys == ["/a", "/m", "/z"]

    def test_handles_missing_data_dir(self, duckbrain_tmp):
        keys = dbc.list_keys(namespace="nonexistent-ns")
        assert keys == []

    def test_default_prefix_is_root_slash(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-default-prefix")
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "1", "key": "/any", "domain": "concept", "attributes": {}, "status": "active"},
            {"id": "2", "key": "/path", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        keys = dbc.list_keys(namespace="test-default-prefix")
        assert len(keys) == 2

    def test_deduplicates_across_files(self, duckbrain_tmp):
        data_dir = dbc._ensure_namespace("test-dedup")
        _write_jsonl(data_dir, "2026-06-24", [
            {"id": "1", "key": "/dup", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        _write_jsonl(data_dir, "2026-06-25", [
            {"id": "2", "key": "/dup", "domain": "concept", "attributes": {}, "status": "active"},
        ])
        keys = dbc.list_keys(namespace="test-dedup")
        assert keys == ["/dup"]  # deduplicated
