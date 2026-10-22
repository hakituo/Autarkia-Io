<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/hakituo/Autarkia-Io/main/autarkia-dark.svg">
    <img src="https://raw.githubusercontent.com/hakituo/Autarkia-Io/main/autarkia.svg" alt="Autarkia" width="300">
  </picture>
</p>

<p align="center">
  <b>Autarkia-Io</b><br>
  <sub>长跑程序的原子文件 IO · Atomic file I/O for long-running agents</sub>
</p>

<p align="center">
  <a href="https://pypi.org/project/Autarkia-Io/"><img alt="PyPI" src="https://img.shields.io/pypi/v/autarkia-io.svg"></a>
  <a href="https://pypi.org/project/Autarkia-Io/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/autarkia-io.svg"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
</p>

<p align="center">
  <a href="#中文">简体中文</a> · <a href="#english">English</a>
</p>

---

## 中文

**崩溃安全的写入、Windows 文件占用重试、可选 fsync、sync/async 双套 API，以及从 LLM 输出里抠 JSON。**

来自在单台 Windows 机器上持续持久化状态数月的 [Autarkia](https://qishihao.icu/projects/autarkia) agent 运行时。整个系列见[组件库路线图](https://github.com/hakituo/Autarkia-tool/blob/main/ROADMAP.md)。

### 为什么

`open(path, "w")` 不是一种持久化策略：

- **截断窗口**：以写模式打开会先清空文件，新字节还没落盘，崩溃或断电就留下一个空文件。
- **临时名竞争**：固定的 `.tmp` 名字在线程和 asyncio 任务之间撞车，两个写入方替换同一个临时文件，其中一个的数据就没了。
- **Windows 文件锁**：杀毒软件和搜索索引器会短暂占用文件，`os.replace` 抛 `WinError 5` 或 `32`——重试一次就能过。
- **缓冲区会骗你**：没有 `fsync`，操作系统可能确认了一次其实没到磁盘的写入。
- **模型会给 JSON 包壳**：代码块、解释文字、模板里带出来的双层花括号，甚至直接拒答。

### 安装

```bash
pip install autarkia-io
# 可选的异步文件后端
pip install "autarkia-io[async]"
```

没装 `aiofiles` 时，异步函数在工作线程里跑同步实现。

### 快速开始

```python
from autarkia_io import safe_json_dump, safe_json_load, safe_write_text

safe_json_dump({"mood": "calm"}, "data/state.json")
state = safe_json_load("data/state.json", default={})

safe_write_text("line 1\nline 2", "data/notes.txt", use_fsync=True)
```

异步：

```python
from autarkia_io import async_safe_json_dump, async_safe_json_load

await async_safe_json_dump({"a": 1}, "data/state.json")
state = await async_safe_json_load("data/state.json", default={})
```

从模型回复里取 JSON：

```python
from autarkia_io import extract_json_object, looks_like_refusal, unwrap_redundant_brackets

extract_json_object('好的：```json\n{"mood": "happy"}\n```')
# {"mood": "happy"}

extract_json_object('{{"people": [{{"name": "a"}}]}}')
# 整串都被包了一层时，先 unwrap_redundant_brackets

looks_like_refusal("抱歉，我无法完成这个请求")  # True
```

### 接口一览

| 函数 | 保证 |
| --- | --- |
| `safe_write_text` / `safe_json_dump` | 临时文件 + `os.replace`，每次调用唯一 |
| `retry_replace` | `WinError 5/32` / `EACCES` 的指数退避重试 |
| `cleanup_stale_temp_files` | 清理 5 分钟以上的孤儿临时文件 |
| `safe_read_text` / `safe_json_load` | 缺失或损坏时返回默认值 |
| `async_*` | 同样的保证，`aiofiles` 或线程回退 |
| `extract_json_object` | 第一个配平的 object，否则第一个数组 |
| `unwrap_redundant_brackets` | 剥掉从提示模板抄来的 `{{...}}` |
| `looks_like_refusal` | 区分「拒答」与「JSON 写坏了」 |

### 设计说明

- **重试有上限**：同步约 25 秒、异步约 2 秒，之后错误照常抛出。
- **最终还是 `PermissionError` 时回退**：同步写入退回直接写，避免数据丢失；这是文档化的行为，不是静默降级。
- **没有全局状态**：路径全是参数，不 import 任何配置。
- **测试确定性**：`retry_replace` 接受 `sleep=`，重试路径测试瞬间跑完。

### 系列与链接

- 项目页：<https://qishihao.icu/projects/autarkia>
- 运行时仓库：<https://github.com/hakituo/Autarkia>
- 本包：<https://github.com/hakituo/Autarkia-Io>
- 组件库路线图：<https://github.com/hakituo/Autarkia-tool/blob/main/ROADMAP.md>
- 作者：Shihao Qi — <https://qishihao.icu>

### 许可

MIT

---

## English

**Crash-safe writes, Windows lock retries, optional fsync, sync + async APIs, and resilient JSON extraction from LLM output.**

Extracted from the [Autarkia](https://qishihao.icu/projects/autarkia) agent runtime, which has persisted state on a single Windows machine for months. See the [component roadmap](https://github.com/hakituo/Autarkia-tool/blob/main/ROADMAP.md).

### Why

Naive `open(path, "w")` is not a persistence strategy:

- **Truncation window.** Opening for write empties the file before new bytes land. A crash or power loss leaves an empty file.
- **Temp-name races.** A fixed `.tmp` name collides between threads and asyncio tasks. Two writers replace the same temp file and one loses its data.
- **Windows locks.** Antivirus and the search indexer briefly hold files. `os.replace` fails with `WinError 5` or `32`, which a retry resolves.
- **Buffers lie.** Without `fsync`, the OS may acknowledge a write that never reaches disk.
- **Models wrap JSON.** LLMs return JSON inside fences, prose, doubled template braces, or a refusal.

### Install

```bash
pip install autarkia-io
# optional async file backend
pip install "autarkia-io[async]"
```

Without `aiofiles`, async functions run the sync implementation in a worker thread.

### Quick start

```python
from autarkia_io import safe_json_dump, safe_json_load, safe_write_text

safe_json_dump({"mood": "calm"}, "data/state.json")
state = safe_json_load("data/state.json", default={})

safe_write_text("line 1\nline 2", "data/notes.txt", use_fsync=True)
```

#### Async

```python
from autarkia_io import async_safe_json_dump, async_safe_json_load

await async_safe_json_dump({"a": 1}, "data/state.json")
state = await async_safe_json_load("data/state.json", default={})
```

#### JSON from an LLM reply

```python
from autarkia_io import extract_json_object, looks_like_refusal, unwrap_redundant_brackets

extract_json_object('好的：```json\n{"mood": "happy"}\n```')
# {"mood": "happy"}

extract_json_object('{{"people": [{{"name": "a"}}]}}')
# ... use unwrap_redundant_brackets first if the whole string is doubled

looks_like_refusal("抱歉，我无法完成这个请求")  # True
```

### Concepts

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

### Design notes

- **Retry is bounded.** Sync waits about 25 seconds total; async about 2 seconds. After that, errors surface.
- **Fallback on final `PermissionError`.** The sync write falls back to a direct write so data is not lost when replacement is impossible; this is documented, not silent.
- **No global state.** All paths are arguments; no configuration import.
- **Deterministic tests.** `retry_replace` accepts `sleep=` so retry tests run instantly.

### The bigger picture

- Project page: <https://qishihao.icu/projects/autarkia>
- Runtime repository: <https://github.com/hakituo/Autarkia>
- This package: <https://github.com/hakituo/Autarkia-Io>
- Roadmap: <https://github.com/hakituo/Autarkia-tool/blob/main/ROADMAP.md>
- Author: Shihao Qi — <https://qishihao.icu>

### License

MIT
