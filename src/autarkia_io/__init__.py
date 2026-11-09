"""Autarkia-Io: atomic file I/O and resilient JSON extraction."""

from .atomic import (
    AIOFILES_AVAILABLE,
    ASYNC_RETRY_DELAYS,
    STALE_TEMP_FILE_TTL_SECONDS,
    SYNC_RETRY_DELAYS,
    async_safe_json_dump,
    async_safe_json_load,
    async_safe_read_text,
    async_safe_write_text,
    cleanup_stale_temp_files,
    dump_json_text,
    ensure_parent_dir,
    generate_temp_path,
    retry_replace,
    safe_json_dump,
    safe_json_load,
    safe_read_text,
    safe_write_text,
    should_retry_fs_error,
)
from .jsontools import (
    extract_json_block,
    extract_json_object,
    looks_like_refusal,
    unwrap_redundant_brackets,
)

__version__ = "0.1.1"

__all__ = [
    "__version__",
    "AIOFILES_AVAILABLE",
    "SYNC_RETRY_DELAYS",
    "ASYNC_RETRY_DELAYS",
    "STALE_TEMP_FILE_TTL_SECONDS",
    "should_retry_fs_error",
    "ensure_parent_dir",
    "generate_temp_path",
    "cleanup_stale_temp_files",
    "retry_replace",
    "dump_json_text",
    "safe_write_text",
    "safe_read_text",
    "safe_json_dump",
    "safe_json_load",
    "async_safe_write_text",
    "async_safe_read_text",
    "async_safe_json_dump",
    "async_safe_json_load",
    "unwrap_redundant_brackets",
    "looks_like_refusal",
    "extract_json_block",
    "extract_json_object",
]
