"""Resilient JSON extraction from LLM output.

Models wrap JSON in fences, prefix it with prose, double the braces copied from
prompt templates, or return a refusal instead of JSON. These helpers recover
the useful object when one exists and decline to guess when it does not.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, Optional, Union

JsonValue = Union[Dict[str, Any], list]


def _loads_json_candidate(text: str) -> Optional[JsonValue]:
    """Parse JSON, unwrapping one level of a re-serialized JSON string."""
    raw = str(text or "").lstrip("\ufeff").strip()
    if not raw:
        return None

    current = raw
    for _ in range(2):
        try:
            parsed = json.loads(current)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed, str):
            nested = parsed.lstrip("\ufeff").strip()
            if nested and nested != current and nested[:1] in {"{", "["}:
                current = nested
                continue

        if isinstance(parsed, (dict, list)):
            return parsed
        return None

    return None


_BRACE_PAIRS = {"{{": "}}", "[[": "]]"}

_REFUSAL_HINTS = (
    "i can't help",
    "i can’t help",
    "i cannot help",
    "i can't assist",
    "i cannot assist",
    "i can’t assist",
    "i won't",
    "i will not",
    "i'm unable to",
    "i am unable to",
    "i'm not able to",
    "as an ai language model",
    "i do not feel comfortable",
    "抱歉，我不能",
    "抱歉，我无法",
    "对不起，我不能",
    "对不起，我无法",
    "我无法帮助",
    "我不能帮",
    "无法为您提取",
)


def unwrap_redundant_brackets(text: str) -> str:
    """Strip doubled braces copied from a prompt template.

    Only touches text that is not already valid JSON, so ordinary nested
    objects are never altered.
    """
    raw = str(text or "").strip()
    if len(raw) < 4:
        return raw
    closer = _BRACE_PAIRS.get(raw[:2])
    if not closer or not raw.endswith(closer):
        return raw
    try:
        json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    else:
        return raw
    unwrapped = re.sub(r"\}\}", "}", re.sub(r"\{\{", "{", raw)).strip()
    try:
        json.loads(unwrapped)
    except (json.JSONDecodeError, ValueError):
        return raw
    return unwrapped


def looks_like_refusal(text: str) -> bool:
    """Whether the text is a refusal rather than JSON.

    Only applies when the text contains neither ``{`` nor ``[``, so valid JSON
    that happens to quote "I can't" is not misclassified.
    """
    raw = str(text or "").strip()
    if not raw:
        return False
    if "{" in raw or "[" in raw:
        return False
    lowered = raw.lower()
    return any(hint in lowered for hint in _REFUSAL_HINTS)


def _iter_balanced_json_candidates(text: str) -> Iterator[str]:
    """Yield balanced ``{...}`` / ``[...]`` fragments, ignoring braces in strings."""
    source = str(text or "")
    total = len(source)

    for start_index, start_char in enumerate(source):
        if start_char not in "{[":
            continue

        stack = [start_char]
        in_string = False
        escape = False

        for index in range(start_index + 1, total):
            char = source[index]

            if escape:
                escape = False
                continue
            if in_string:
                if char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char in "{[":
                stack.append(char)
                continue
            if char in "}]":
                if not stack:
                    break
                last = stack[-1]
                if (char == "}" and last != "{") or (char == "]" and last != "["):
                    break
                stack.pop()
                if not stack:
                    yield source[start_index : index + 1]
                    break


def extract_json_block(text: str) -> str:
    """Extract the first JSON object string; returns the input if none is found."""
    raw = str(text or "").strip()
    if not raw:
        return ""

    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines:
            first = lines[0].strip().lower()
            if first in {"```", "```json", "```jsonc"}:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

    fenced = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        return str(fenced.group(1) or "").strip()

    start = raw.find("{")
    if start != -1:
        stack = []
        for index, char in enumerate(raw[start:], start=start):
            if char == "{":
                stack.append(char)
            elif char == "}":
                if stack:
                    stack.pop()
                    if not stack:
                        return raw[start : index + 1]

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return raw[start : end + 1]

    return raw


def extract_json_object(text: str) -> Optional[JsonValue]:
    """Extract and parse the first object (or, failing that, the first array)."""
    text = str(text or "").lstrip("\ufeff").strip()
    if not text:
        return None

    parsed = _loads_json_candidate(text)
    if parsed is not None:
        return parsed

    block = extract_json_block(text)
    if block and block != text:
        parsed = _loads_json_candidate(block)
        if parsed is not None:
            return parsed

    first_list: Optional[list] = None
    for candidate in _iter_balanced_json_candidates(text):
        parsed = _loads_json_candidate(candidate)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and first_list is None:
            first_list = parsed

    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if code_block:
        parsed = _loads_json_candidate(code_block.group(1))
        if parsed is not None:
            return parsed

    return first_list


__all__ = [
    "unwrap_redundant_brackets",
    "looks_like_refusal",
    "extract_json_block",
    "extract_json_object",
]


def is_json_array(text: str) -> bool:
    """判断文本整体是否为合法 JSON 数组。"""
    try:
        return isinstance(json.loads(text), list)
    except (TypeError, ValueError):
        return False
