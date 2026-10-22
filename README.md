# Autarkia-Io

**Atomic file I/O for long-running agents** — crash-safe writes, Windows lock retries, optional fsync, sync + async APIs, and resilient JSON extraction from LLM output.

Extracted from the [Autarkia](https://qishihao.icu/projects/autarkia) agent runtime, which has persisted state on a single Windows machine for months. See the [component roadmap](https://github.com/hakituo/Autarkia-tool/blob/main/ROADMAP.md).

## Why

Naive `open(path, "w")` is not a persistence strategy:

- **Truncation window.** Opening for write empties the file before new bytes land. A crash or power loss leaves an empty file.
- **Temp-name races.** A fixed `.tmp` name collides between threads and asyncio tasks. Two writers replace the same temp file and one loses its data.
- **Windows locks.** Antivirus and the search indexer briefly hold files. `os.replace` fails with `WinError 5` or `32`, which a retry resolves.
- **Buffers lie.** Without `fsync`, the OS may acknowledge a write that never reaches disk.
- **Models wrap JSON.** LLMs return JSON inside fences, prose, doubled template braces, or a refusal.

## Install

```bash
pip install autarkia-io
# optional async file backend
pip install "autarkia-io[async]"
```

Without `aiofiles`, async functions run the sync implementation in a worker thread.

## Quick start

```python
from autarkia_io import safe_json_dump, safe_json_load, safe_write_text

safe_json_dump({"mood": "calm"}, "data/state.json")
state = safe_json_load("data/state.json", default={})

safe_write_text("line 1\nline 2", "data/notes.txt", use_fsync=True)
```

### Async

```python
from autarkia_io import async_safe_json_dump, async_safe_json_load

await async_safe_json_dump({"a": 1}, "data/state.json")
state = await async_safe_json_load("data/state.json", default={})
```

### JSON from an LLM reply

```python
from autarkia_io import extract_json_object, looks_like_refusal, unwrap_redundant_brackets

extract_json_object('好的：```json\n{"mood": "happy"}\n```')
# {"mood": "happy"}

extract_json_object('{{"people": [{{"name": "a"}}]}}')
# ... use unwrap_redundant_brackets first if the whole string is doubled

looks_like_refusal("抱歉，我无法完成这个请求")  # True
```

## Concepts

| Function | What it guarantees |
| --- | --- |
| `safe_write_text` / `safe_json_dump` | temp file + `os.replace`, unique per call |
| `retry_replace` | exponential backoff for `WinError 5/32` / `EACCES` |
| `cleanup_stale_temp_files` | removes orphaned temp files older than 5 minutes |
| `safe_read_text` / `safe_json_load` | default value for missing/corrupt data |
| `async_*` | same guarantees, `aiofiles` or thread fallback |
| `extract_json_object` | first balanced object, else first array |
| `unwrap_redundant_brackets` | strips `{{...}}` copied from prompt templates |
| `looks_like_refusal` | distinguishes a refusal from malformed JSON |

## Design notes

- **Retry is bounded.** Sync waits about 25 seconds total; async about 2 seconds. After that, errors surface.
- **Fallback on final `PermissionError`.** The sync write falls back to a direct write so data is not lost when replacement is impossible; this is documented, not silent.
- **No global state.** All paths are arguments; no configuration import.
- **Deterministic tests.** `retry_replace` accepts `sleep=` so retry tests run instantly.

## The bigger picture

- Project page: <https://qishihao.icu/projects/autarkia>
- Runtime repository: <https://github.com/hakituo/Autarkia>
- This package: <https://github.com/hakituo/Autarkia-Io>
- Roadmap: <https://github.com/hakituo/Autarkia-tool/blob/main/ROADMAP.md>
- Author: Shihao Qi — <https://qishihao.icu>

## License

MIT
