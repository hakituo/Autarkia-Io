"""Atomic writes with retry for Windows locks.

Why this exists:

- A plain ``open(path, "w")`` truncates the file first; a crash leaves it empty.
- A fixed temp name ``path.tmp`` races between threads and coroutines. This
  module uses thread + process + UUID in the temp name.
- On Windows, antivirus/indexers briefly lock files; ``os.replace`` fails with
  ``WinError 5`` (access denied) or ``32`` (sharing violation). Retrying with
  exponential backoff covers a scan window.
- ``fsync`` is optional because not every sandbox exposes a usable descriptor.

The async variants use ``aiofiles`` when installed and fall back to
``asyncio.to_thread`` otherwise.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Union

logger = logging.getLogger(__name__)

try:  # optional dependency
    import aiofiles
    import aiofiles.os

    AIOFILES_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    aiofiles = None  # type: ignore[assignment]
    AIOFILES_AVAILABLE = False

PathLike = Union[str, Path]

# About 25 seconds of cumulative wait: enough for antivirus scans and the
# Windows search indexer to release a file.
SYNC_RETRY_DELAYS: Sequence[float] = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4, 6.4, 6.4)
ASYNC_RETRY_DELAYS: Sequence[float] = (0.03, 0.06, 0.12, 0.24, 0.48, 0.96)
STALE_TEMP_FILE_TTL_SECONDS = 300


def should_retry_fs_error(error: Exception) -> bool:
    """Whether the error is a transient lock worth retrying."""
    if isinstance(error, PermissionError):
        return True
    if isinstance(error, OSError):
        if getattr(error, "winerror", None) in {5, 32}:
            return True
        if getattr(error, "errno", None) == 13:
            return True
    return False


def ensure_parent_dir(file_path: PathLike) -> None:
    parent = os.path.dirname(str(file_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def generate_temp_path(file_path: PathLike) -> str:
    """A temp path unique per thread, process and call."""
    return (
        f"{file_path}.tmp_{threading.get_ident()}_{os.getpid()}_"
        f"{uuid.uuid4().hex}"
    )


def cleanup_stale_temp_files(
    file_path: PathLike,
    *,
    ttl_seconds: float = STALE_TEMP_FILE_TTL_SECONDS,
) -> None:
    """Remove leftover ``<name>.tmp_*`` files older than ``ttl_seconds``."""
    try:
        parent = os.path.dirname(str(file_path))
        if not parent:
            return
        prefix = f"{os.path.basename(str(file_path))}.tmp_"
        now = time.time()
        for entry in os.listdir(parent):
            if not entry.startswith(prefix):
                continue
            entry_path = os.path.join(parent, entry)
            try:
                if now - os.path.getmtime(entry_path) > ttl_seconds:
                    os.remove(entry_path)
                    logger.debug("Removed stale temp file: %s", entry_path)
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - cleanup must never break the write
        return


def retry_replace(
    src: PathLike,
    dst: PathLike,
    *,
    attempts: Optional[int] = None,
    use_fsync: bool = False,
    delays: Sequence[float] = SYNC_RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """``os.replace`` with exponential backoff for transient lock errors."""
    max_attempts = max(1, int(attempts if attempts is not None else len(delays)))
    last_error: Optional[Exception] = None

    for index in range(max_attempts):
        try:
            if use_fsync:
                try:
                    descriptor = os.open(str(src), os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                except OSError as fsync_error:
                    logger.debug("Pre-replace fsync failed (ignored): %s", fsync_error)
            os.replace(str(src), str(dst))
            return
        except Exception as error:  # noqa: BLE001
            last_error = error
            if index >= len(delays) or not should_retry_fs_error(error):
                raise
            sleep(delays[index])

    if last_error is not None:
        raise last_error


def _write_text_payload(
    text: str, file_path: PathLike, encoding: str, use_fsync: bool
) -> None:
    path = str(file_path)
    ensure_parent_dir(path)
    cleanup_stale_temp_files(path)
    temp_path = generate_temp_path(path)
    try:
        with open(temp_path, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError as fsync_error:
                logger.debug("fsync failed (ignored): %s", fsync_error)
        retry_replace(temp_path, path, use_fsync=use_fsync)
    except PermissionError:
        # Last resort: direct write. Non-atomic, but losing the data is worse.
        try:
            with open(path, "w", encoding=encoding) as handle:
                handle.write(text)
            _remove_if_exists(temp_path)
        except Exception:
            _remove_if_exists(temp_path)
            raise
    except Exception:
        _remove_if_exists(temp_path)
        raise


def _remove_if_exists(path: str) -> None:
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:  # noqa: BLE001
            pass


def safe_write_text(
    text: str,
    file_path: PathLike,
    encoding: str = "utf-8",
    use_fsync: bool = False,
) -> None:
    """Atomically write text (temp file + replace + retry)."""
    _write_text_payload(str(text), file_path, encoding, use_fsync)


def safe_read_text(
    file_path: PathLike,
    encoding: str = "utf-8",
    default: str = "",
) -> str:
    """Read text, returning ``default`` for missing/unreadable files."""
    path = str(file_path)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding=encoding) as handle:
            return handle.read()
    except OSError:
        return default


def safe_json_dump(
    data: Any,
    file_path: PathLike,
    encoding: str = "utf-8",
    use_fsync: bool = False,
) -> None:
    """Atomically write pretty JSON (``ensure_ascii=False``)."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    _write_text_payload(payload, file_path, encoding, use_fsync)


def safe_json_load(
    file_path: PathLike,
    encoding: str = "utf-8",
    default: Any = None,
) -> Any:
    """Read JSON, returning ``default`` for missing/corrupt files."""
    path = str(file_path)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding=encoding) as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default


async def _async_retry_replace(
    src: PathLike,
    dst: PathLike,
    *,
    attempts: Optional[int] = None,
    use_fsync: bool = False,
    delays: Sequence[float] = ASYNC_RETRY_DELAYS,
) -> None:
    if not os.path.exists(str(src)):
        raise FileNotFoundError(f"temp file does not exist: {src}")
    max_attempts = max(1, int(attempts if attempts is not None else len(delays)))
    last_error: Optional[Exception] = None

    for index in range(max_attempts):
        try:
            if use_fsync:
                try:
                    descriptor = os.open(str(src), os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                except OSError as fsync_error:
                    logger.debug("Pre-replace fsync failed (ignored): %s", fsync_error)
            await asyncio.to_thread(os.replace, str(src), str(dst))
            return
        except Exception as error:  # noqa: BLE001
            last_error = error
            if index >= len(delays) or not should_retry_fs_error(error):
                raise
            await asyncio.sleep(delays[index])

    if last_error is not None:
        raise last_error


async def _async_write_text_payload(
    text: str, file_path: PathLike, encoding: str, use_fsync: bool
) -> None:
    path = str(file_path)
    ensure_parent_dir(path)
    cleanup_stale_temp_files(path)
    temp_path = generate_temp_path(path)

    if AIOFILES_AVAILABLE:
        try:
            async with aiofiles.open(temp_path, "w", encoding=encoding) as handle:
                await handle.write(text)
                await handle.flush()
                if use_fsync:
                    sync_file = getattr(handle, "_file", None)
                    descriptor = sync_file.fileno() if sync_file is not None else handle.fileno()
                    os.fsync(descriptor)
            await _async_retry_replace(temp_path, path, use_fsync=use_fsync)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    await aiofiles.os.remove(temp_path)
                except Exception:  # noqa: BLE001
                    pass
            raise
    else:
        await asyncio.to_thread(_write_text_payload, text, path, encoding, use_fsync)


async def async_safe_write_text(
    text: str,
    file_path: PathLike,
    encoding: str = "utf-8",
    use_fsync: bool = False,
) -> None:
    """Async atomic text write."""
    await _async_write_text_payload(str(text), file_path, encoding, use_fsync)


async def async_safe_read_text(
    file_path: PathLike,
    encoding: str = "utf-8",
    default: str = "",
) -> str:
    """Async text read with a default."""
    path = str(file_path)
    if not os.path.exists(path):
        return default
    try:
        if AIOFILES_AVAILABLE:
            async with aiofiles.open(path, "r", encoding=encoding) as handle:
                return await handle.read()
        return await asyncio.to_thread(safe_read_text, path, encoding, default)
    except OSError:
        return default


async def async_safe_json_dump(
    data: Any,
    file_path: PathLike,
    encoding: str = "utf-8",
    use_fsync: bool = False,
) -> None:
    """Async atomic JSON write."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    await _async_write_text_payload(payload, file_path, encoding, use_fsync)


async def async_safe_json_load(
    file_path: PathLike,
    encoding: str = "utf-8",
    default: Any = None,
) -> Any:
    """Async JSON read with a default."""
    path = str(file_path)
    if not os.path.exists(path):
        return default
    try:
        if AIOFILES_AVAILABLE:
            async with aiofiles.open(path, "r", encoding=encoding) as handle:
                content = await handle.read()
            return json.loads(content.lstrip("\ufeff"))
        return await asyncio.to_thread(safe_json_load, path, encoding, default)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default


__all__ = [
    "AIOFILES_AVAILABLE",
    "SYNC_RETRY_DELAYS",
    "ASYNC_RETRY_DELAYS",
    "STALE_TEMP_FILE_TTL_SECONDS",
    "should_retry_fs_error",
    "ensure_parent_dir",
    "generate_temp_path",
    "cleanup_stale_temp_files",
    "retry_replace",
    "safe_write_text",
    "safe_read_text",
    "safe_json_dump",
    "safe_json_load",
    "async_safe_write_text",
    "async_safe_read_text",
    "async_safe_json_dump",
    "async_safe_json_load",
]
