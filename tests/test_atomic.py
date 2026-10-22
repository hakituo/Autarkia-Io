"""Atomic text/JSON I/O tests: durability, retries, cleanup, concurrency."""

import asyncio
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from autarkia_io import (
    async_safe_json_dump,
    async_safe_json_load,
    async_safe_read_text,
    async_safe_write_text,
    cleanup_stale_temp_files,
    generate_temp_path,
    retry_replace,
    safe_json_dump,
    safe_json_load,
    safe_read_text,
    safe_write_text,
    should_retry_fs_error,
)


class TestText:
    def test_round_trip(self, tmp_path):
        target = tmp_path / "a" / "b" / "note.txt"
        safe_write_text("你好\n世界", target)
        assert safe_read_text(target) == "你好\n世界"

    def test_parent_created(self, tmp_path):
        target = tmp_path / "x" / "y" / "z.txt"
        safe_write_text("x", target)
        assert target.exists()

    def test_overwrite(self, tmp_path):
        target = tmp_path / "note.txt"
        safe_write_text("first", target)
        safe_write_text("second", target)
        assert safe_read_text(target) == "second"

    def test_missing_returns_default(self, tmp_path):
        assert safe_read_text(tmp_path / "none.txt", default="fallback") == "fallback"

    def test_unicode_encoding(self, tmp_path):
        target = tmp_path / "note.txt"
        safe_write_text("émoji 😊", target)
        assert safe_read_text(target) == "émoji 😊"

    def test_no_temp_left(self, tmp_path):
        target = tmp_path / "note.txt"
        safe_write_text("x", target)
        assert [p.name for p in tmp_path.iterdir()] == ["note.txt"]


class TestJson:
    def test_round_trip(self, tmp_path):
        target = tmp_path / "data.json"
        payload = {"name": "小右", "values": [1, 2, 3]}
        safe_json_dump(payload, target)
        assert safe_json_load(target) == payload

    def test_non_ascii_not_escaped(self, tmp_path):
        target = tmp_path / "data.json"
        safe_json_dump({"k": "中文"}, target)
        assert "中文" in target.read_text(encoding="utf-8")

    def test_missing_returns_default(self, tmp_path):
        assert safe_json_load(tmp_path / "none.json", default={}) == {}

    def test_corrupt_returns_default(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text("{broken", encoding="utf-8")
        assert safe_json_load(target, default=None) is None

    def test_repeated_writes_valid(self, tmp_path):
        target = tmp_path / "data.json"
        for value in range(20):
            safe_json_dump({"value": value}, target)
        assert safe_json_load(target)["value"] == 19


class TestTempFiles:
    def test_unique_names(self):
        first = generate_temp_path("a.json")
        second = generate_temp_path("a.json")
        assert first != second
        assert first.startswith("a.json.tmp_")

    def test_stale_temp_removed(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text("current", encoding="utf-8")
        stale = tmp_path / "data.json.tmp_123_456_dead"
        stale.write_text("leftover", encoding="utf-8")
        old = time.time() - 10_000
        os.utime(stale, (old, old))
        cleanup_stale_temp_files(target)
        assert not stale.exists()

    def test_fresh_temp_kept(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text("current", encoding="utf-8")
        fresh = tmp_path / "data.json.tmp_123_456_live"
        fresh.write_text("in progress", encoding="utf-8")
        cleanup_stale_temp_files(target)
        assert fresh.exists()

    def test_other_prefix_not_removed(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text("x", encoding="utf-8")
        other = tmp_path / "other.json.tmp_1_2_dead"
        other.write_text("x", encoding="utf-8")
        old = time.time() - 10_000
        os.utime(other, (old, old))
        cleanup_stale_temp_files(target)
        assert other.exists()


class TestRetry:
    def test_permission_error_retryable(self):
        assert should_retry_fs_error(PermissionError()) is True

    def test_winerror_5_retryable(self):
        error = OSError()
        error.winerror = 5
        assert should_retry_fs_error(error) is True

    def test_winerror_32_retryable(self):
        error = OSError()
        error.winerror = 32
        assert should_retry_fs_error(error) is True

    def test_other_error_not_retryable(self):
        assert should_retry_fs_error(ValueError("nope")) is False

    def test_retry_succeeds_after_transient_failures(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.write_text("x", encoding="utf-8")
        calls = {"count": 0}
        real_replace = os.replace

        def flaky(a, b):
            calls["count"] += 1
            if calls["count"] < 3:
                raise PermissionError("locked")
            real_replace(a, b)

        monkeypatch.setattr("autarkia_io.atomic.os.replace", flaky)
        retry_replace(src, dst, sleep=lambda _: None)
        assert calls["count"] == 3
        assert dst.read_text(encoding="utf-8") == "x"

    def test_retry_gives_up(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        src.write_text("x", encoding="utf-8")

        def always_locked(a, b):
            raise PermissionError("locked")

        monkeypatch.setattr("autarkia_io.atomic.os.replace", always_locked)
        with pytest.raises(PermissionError):
            retry_replace(src, tmp_path / "dst", attempts=2, sleep=lambda _: None)
        assert src.exists()

    def test_non_retryable_raises_immediately(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        src.write_text("x", encoding="utf-8")
        calls = {"count": 0}

        def broken(a, b):
            calls["count"] += 1
            raise ValueError("bad")

        monkeypatch.setattr("autarkia_io.atomic.os.replace", broken)
        with pytest.raises(ValueError):
            retry_replace(src, tmp_path / "dst", sleep=lambda _: None)
        assert calls["count"] == 1


class TestConcurrency:
    def test_threads_never_see_partial_json(self, tmp_path):
        target = tmp_path / "shared.json"
        payloads = [{"thread": index, "data": "x" * 200} for index in range(20)]

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda payload: safe_json_dump(payload, target), payloads))

        loaded = safe_json_load(target)
        assert loaded in payloads
        leftovers = [p.name for p in tmp_path.iterdir() if ".tmp_" in p.name]
        assert leftovers == []

    def test_threads_write_text_atomically(self, tmp_path):
        target = tmp_path / "shared.txt"
        values = [f"value-{index}-" + "y" * 100 for index in range(20)]

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda value: safe_write_text(value, target), values))

        assert safe_read_text(target) in values


class TestAsync:
    def test_text_round_trip(self, tmp_path):
        target = tmp_path / "note.txt"

        async def main():
            await async_safe_write_text("异步", target)
            return await async_safe_read_text(target)

        assert asyncio.run(main()) == "异步"

    def test_json_round_trip(self, tmp_path):
        target = tmp_path / "data.json"

        async def main():
            await async_safe_json_dump({"a": 1}, target)
            return await async_safe_json_load(target)

        assert asyncio.run(main()) == {"a": 1}

    def test_json_default(self, tmp_path):
        assert asyncio.run(async_safe_json_load(tmp_path / "none.json", default=[])) == []

    def test_text_default(self, tmp_path):
        assert asyncio.run(async_safe_read_text(tmp_path / "none.txt", default="d")) == "d"

    def test_corrupt_json_default(self, tmp_path):
        target = tmp_path / "bad.json"
        target.write_text("{bad", encoding="utf-8")
        assert asyncio.run(async_safe_json_load(target, default=None)) is None

    def test_no_temp_left(self, tmp_path):
        target = tmp_path / "data.json"
        asyncio.run(async_safe_json_dump({"a": 1}, target))
        assert [p.name for p in tmp_path.iterdir()] == ["data.json"]

    def test_concurrent_tasks_atomic(self, tmp_path):
        target = tmp_path / "data.json"

        async def main():
            await asyncio.gather(
                *[async_safe_json_dump({"n": index}, target) for index in range(20)]
            )

        asyncio.run(main())
        assert isinstance(safe_json_load(target), dict)


def test_import_does_not_require_aiofiles():
    from autarkia_io import AIOFILES_AVAILABLE

    assert isinstance(AIOFILES_AVAILABLE, bool)
