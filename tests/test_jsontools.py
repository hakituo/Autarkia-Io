"""JSON extraction from messy LLM output."""

from autarkia_io import (
    extract_json_block,
    extract_json_object,
    looks_like_refusal,
    unwrap_redundant_brackets,
)


class TestExtractObject:
    def test_bare_object(self):
        assert extract_json_object('{"a": 1}') == {"a": 1}

    def test_bare_array(self):
        assert extract_json_object("[1, 2]") == [1, 2]

    def test_fenced_json(self):
        text = '说明如下：\n```json\n{"name": "小右", "age": 3}\n```\n完毕'
        assert extract_json_object(text) == {"name": "小右", "age": 3}

    def test_fenced_without_language(self):
        assert extract_json_object('```\n{"a": 1}\n```') == {"a": 1}

    def test_prose_around_object(self):
        text = '好的，我整理好了：{"mood": "happy"} 希望有帮助'
        assert extract_json_object(text) == {"mood": "happy"}

    def test_nested_object(self):
        text = 'prefix {"outer": {"inner": [1, 2]}} suffix'
        assert extract_json_object(text) == {"outer": {"inner": [1, 2]}}

    def test_braces_inside_string_ignored(self):
        text = 'note {"text": "a } brace", "n": 1} tail'
        assert extract_json_object(text) == {"text": "a } brace", "n": 1}

    def test_prefers_object_over_earlier_array(self):
        text = '先给数组 [1, 2]，再给对象 {"a": 1}'
        assert extract_json_object(text) == {"a": 1}

    def test_returns_first_array_when_no_object(self):
        assert extract_json_object("前缀 [1, 2] 后缀") == [1, 2]

    def test_invalid_returns_none(self):
        assert extract_json_object("完全不是 JSON") is None
        assert extract_json_object("") is None

    def test_bom_stripped(self):
        assert extract_json_object('\ufeff{"a": 1}') == {"a": 1}

    def test_double_serialized_string(self):
        assert extract_json_object('"{\\"a\\": 1}"') == {"a": 1}

    def test_thinking_prefix(self):
        text = '思考中……\n{"answer": "好"}'
        assert extract_json_object(text) == {"answer": "好"}

    def test_multiple_objects_returns_first(self):
        text = '{"a": 1} and {"b": 2}'
        assert extract_json_object(text) == {"a": 1}


class TestExtractBlock:
    def test_fenced_block(self):
        text = '```json\n{"a": 1}\n```'
        assert extract_json_block(text) == '{"a": 1}'

    def test_unfenced_block(self):
        assert extract_json_block('pre {"a": {"b": 2}} post') == '{"a": {"b": 2}}'

    def test_no_object_returns_input(self):
        assert extract_json_block("plain") == "plain"

    def test_empty(self):
        assert extract_json_block("") == ""


class TestUnwrap:
    def test_double_braces(self):
        text = '{{"people": [{{"name": "a"}}]}}'
        assert unwrap_redundant_brackets(text) == '{"people": [{"name": "a"}]}'

    def test_valid_nested_not_touched(self):
        assert unwrap_redundant_brackets('{"a": {"b": 1}}') == '{"a": {"b": 1}}'

    def test_invalid_after_unwrap_returns_original(self):
        text = "{{broken}}"
        assert unwrap_redundant_brackets(text) == text

    def test_short_text(self):
        assert unwrap_redundant_brackets("{{") == "{{"

    def test_non_brace_text(self):
        assert unwrap_redundant_brackets("hello") == "hello"


class TestRefusal:
    def test_english_refusal(self):
        assert looks_like_refusal("I'm sorry, I can't help with that.") is True

    def test_chinese_refusal(self):
        assert looks_like_refusal("抱歉，我无法完成这个请求") is True

    def test_json_containing_refusal_phrase_is_not_refusal(self):
        assert looks_like_refusal('{"text": "I cannot help"}') is False

    def test_empty(self):
        assert looks_like_refusal("") is False

    def test_normal_text(self):
        assert looks_like_refusal("今天天气不错") is False
