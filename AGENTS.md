# AGENTS.md — Autarkia-Io（Autarkia 组件库系列）

给改动本仓库的 agent 看的说明书。读完应该能回答：这是什么、语义以谁为准、怎么验证、怎么发布。

## 这是什么

Autarkia 运行时组件库系列的第 5 个库：原子文件 IO——临时文件 + 指数退避重试（Windows winerror 5/32）+ 可选 fsync + sync/async 双版本 + JSON 工具（从 LLM 输出中提取/修复 JSON）。

- PyPI：<https://pypi.org/project/Autarkia-Io/>
- 系列路线图：<https://github.com/hakituo/Autarkia-tool/blob/main/ROADMAP.md>（**先读它**）
- 主运行时（语义权威源）：本地 `D:\AI\xiaoyou-public`，GitHub <https://github.com/hakituo/Autarkia>
- 作者站点：<https://qishihao.icu/projects/autarkia>

## 了解背景：先看主仓库的哪些文件

| 本库模块 | 主仓库源头（D:\AI\xiaoyou-public\） |
| --- | --- |
| `src/autarkia_io/atomic.py` | `core\utils\atomic_io.py` |
| `src/autarkia_io/jsontools.py` | `core\utils\json_utils.py` |

抽取时做过的通用化改造（不要再改回去）：
- `core.utils.logger` → stdlib `logging`。
- `aiofiles` 硬依赖 → 可选 extra；未安装时异步路径走 `asyncio.to_thread`。
- host 私有常量保持语义；新增 `sleep=` 注入便于测试重试（生产默认 `time.sleep`）。
- 公开 API 保持 host 名称（`safe_json_dump` / `safe_json_load` / `safe_write_text` / `safe_read_text` / `async_*`）。

## 本仓库结构

```text
AGENTS.md                 本文件
src/autarkia_io/          包本体（import 名 autarkia_io）
tests/                    行为测试（含并发/重试/临时文件清理）
pyproject.toml            hatchling；零必需依赖；可选 extra: aiofiles
```

## 硬规则

1. **零必需运行时依赖**；`aiofiles` 只能做 optional extra，异步路径必须有线程回退。
2. **宿主 import 一个不许进 src/**：`config.*`、`core.*`、`clients.*` 一律禁止。
3. 临时文件名必须保持 thread + pid + uuid 唯一；禁止退回固定 `.tmp`。
4. 行为变更先改/加测试，全绿再提交。
5. **每次 `twine upload` 前必须递增 `pyproject.toml` 的 version**。
6. PyPI token 不进 git；只存在于 `%USERPROFILE%\.pypirc`。

## 命令（本机环境）

venv 与主库共用：`D:\AI\autarkia\.venv\`（Python 3.10）。

| 用途 | 命令 |
| --- | --- |
| 测试 | `$env:PYTHONPATH="src"; D:\AI\autarkia\.venv\Scripts\python -m pytest -q` |
| 构建 | `D:\AI\autarkia\.venv\Scripts\python -m build --no-isolation` |
| 发布检查 | `D:\AI\autarkia\.venv\Scripts\python -m twine check dist\*` |
| 发布 | `$env:HTTP_PROXY="http://127.0.0.1:7897"; $env:HTTPS_PROXY=$env:HTTP_PROXY; D:\AI\autarkia\.venv\Scripts\python -m twine upload dist\* --non-interactive` |

**本机 pip 坑**：不加 `-i https://pypi.org/simple --proxy http://127.0.0.1:7897` 会报 `from versions: none`。**twine 坑**：不认 `--proxy`，走环境变量。

## 提交

- commit message 中文一句话；Windows 下写进临时文件用 `git commit -F` 防乱码。
- 改完自己提交并推送 `origin main`，不要停在"改好了"等确认。
- 推送前 `git status --porcelain` 确认只含本次任务涉及的文件。
