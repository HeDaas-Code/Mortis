"""Test provider 审计日志 (issue #87)。

验收 issue #87:
- MinimaxProvider / MockProvider 的 generate / generate_text 调用产生 DEBUG log
- log 中含 prompt_hash + resp_hash (SHA256 前 16 位), 但**不含 prompt/response 原文**
- ToolAgent._llm_generate 的 log 含 redact 标记 (默认 False, 可设 True)
- hash 可追溯: 同输入 → 同 hash
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

from mortis.provider.audit import messages_hash, sha256_prefix
from mortis.provider.base import Message
from mortis.provider.minimax import MinimaxProvider
from mortis.provider.mock import MockProvider
from mortis.toolagent.base import ToolAgent
from mortis.tools.base import ToolResult as ToolLayerResult

# 一个足够独特的"私密"字符串 — 若它出现在任何 log 中即视为原文泄漏
_SECRET_PROMPT = "TOPSECRET-prompt-do-not-log-9f3a7c1b"
_SECRET_RESPONSE = "TOPSECRET-response-do-not-log-2e8d5a44"


def _user_msg(content: str) -> list[Message]:
    return [Message(role="user", content=content)]


def _mock_urlopen_ok(content: str):
    payload = json.dumps({
        "choices": [{"message": {"content": content}}],
    }).encode("utf-8")
    mock = MagicMock()
    mock.__enter__.return_value.read.return_value = payload
    return mock


# ============================================================
# MockProvider 审计日志
# ============================================================


class TestMockProviderAudit:
    """issue #87 — MockProvider.generate / generate_text 产出审计 log。"""

    def test_generate_produces_debug_log(self, caplog):
        """generate() 调用后应产生一条 DEBUG 审计 log。"""
        p = MockProvider()
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            p.generate(_user_msg("hello world"))
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("method=generate" in r.getMessage() for r in records)

    def test_generate_text_produces_debug_log(self, caplog):
        """generate_text() 调用后应产生一条 DEBUG 审计 log。"""
        p = MockProvider()
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            p.generate_text("hello world")
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("method=generate_text" in r.getMessage() for r in records)

    def test_generate_log_contains_prompt_and_resp_hash(self, caplog):
        """generate() log 含 prompt_hash + resp_hash + elapsed。"""
        p = MockProvider()
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            result = p.generate(_user_msg("audit me"))
        expected_prompt_hash = messages_hash(_user_msg("audit me"))
        expected_resp_hash = sha256_prefix(result.content)
        msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
        # 取含 method=generate (带尾空格, 排除 generate_text) 的那条
        audit = [m for m in msgs if "method=generate " in m]
        assert audit, "应有 method=generate 的审计 log"
        line = audit[0]
        assert f"prompt_hash={expected_prompt_hash}" in line
        assert f"resp_hash={expected_resp_hash}" in line
        assert "elapsed=" in line

    def test_generate_text_log_contains_prompt_and_resp_hash(self, caplog):
        """generate_text() log 含 prompt_hash + resp_hash + elapsed。"""
        p = MockProvider()
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            out = p.generate_text("audit me")
        expected_prompt_hash = sha256_prefix("audit me")
        expected_resp_hash = sha256_prefix(out)
        msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
        audit = [m for m in msgs if "method=generate_text" in m]
        assert audit
        line = audit[0]
        assert f"prompt_hash={expected_prompt_hash}" in line
        assert f"resp_hash={expected_resp_hash}" in line
        assert "elapsed=" in line

    def test_generate_log_does_not_contain_prompt_plaintext(self, caplog):
        """generate() log 绝不含 prompt 原文 (HARNESS.md '数据不外流')。"""
        p = MockProvider()
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            p.generate(_user_msg(_SECRET_PROMPT))
        for r in caplog.records:
            assert _SECRET_PROMPT not in r.getMessage(), (
                f"prompt 原文泄漏到 log (level={r.levelname}): {r.getMessage()}"
            )

    def test_generate_text_log_does_not_contain_prompt_plaintext(self, caplog):
        """generate_text() log 绝不含 prompt 原文。"""
        p = MockProvider()
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            p.generate_text(_SECRET_PROMPT)
        for r in caplog.records:
            assert _SECRET_PROMPT not in r.getMessage()

    def test_generate_text_log_does_not_contain_response_plaintext(self, caplog):
        """generate_text(responses=[...]) log 不含 response 原文。"""
        p = MockProvider(responses=[_SECRET_RESPONSE])
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            out = p.generate_text("prompt")
        assert out == _SECRET_RESPONSE  # 行为不变
        for r in caplog.records:
            assert _SECRET_RESPONSE not in r.getMessage(), (
                f"response 原文泄漏到 log: {r.getMessage()}"
            )

    def test_hash_is_16_hex_chars(self, caplog):
        """prompt_hash / resp_hash 均为 16 位 hex。"""
        p = MockProvider()
        with caplog.at_level(logging.DEBUG, logger="mortis.provider.mock"):
            p.generate_text("hash length check")
        msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
        line = [m for m in msgs if "method=generate_text" in m][0]
        # 提取 prompt_hash=xxxxxxxxxxxxxxxx
        import re

        m = re.search(r"prompt_hash=([0-9a-f]+)", line)
        assert m, f"未找到 prompt_hash: {line}"
        assert len(m.group(1)) == 16, f"hash 应为 16 位, 实际 {len(m.group(1))}: {line}"


# ============================================================
# MinimaxProvider 审计日志
# ============================================================


class TestMinimaxProviderAudit:
    """issue #87 — MinimaxProvider.generate / generate_text 产出审计 log。"""

    def test_generate_produces_debug_log(self, caplog):
        """generate() 成功后产生 DEBUG 审计 log。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("hello back")):
            with caplog.at_level(logging.DEBUG, logger="mortis.provider.minimax"):
                p.generate(_user_msg("test prompt"))
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("method=generate" in r.getMessage() for r in records)

    def test_generate_text_produces_debug_log(self, caplog):
        """generate_text() 成功后产生 DEBUG 审计 log。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("hello back")):
            with caplog.at_level(logging.DEBUG, logger="mortis.provider.minimax"):
                p.generate_text("test prompt")
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        # generate_text 会调 generate, 故 method=generate_text 与 method=generate 都应有
        methods = {r.getMessage() for r in records}
        assert any("method=generate_text" in m for m in methods)

    def test_generate_log_contains_hashes(self, caplog):
        """generate() log 含 prompt_hash + resp_hash + elapsed。"""
        p = MinimaxProvider(api_key="k")
        msgs = _user_msg("audit minimax")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("resp content")):
            with caplog.at_level(logging.DEBUG, logger="mortis.provider.minimax"):
                result = p.generate(msgs)
        expected_prompt_hash = messages_hash(msgs)
        expected_resp_hash = sha256_prefix(result.content)
        lines = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
        gen_lines = [ln for ln in lines if "method=generate " in ln]
        assert gen_lines, "应有 method=generate 审计 log"
        line = gen_lines[0]
        assert f"prompt_hash={expected_prompt_hash}" in line
        assert f"resp_hash={expected_resp_hash}" in line
        assert "elapsed=" in line

    def test_generate_text_log_contains_hashes(self, caplog):
        """generate_text() log 含 prompt_hash + resp_hash + elapsed。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("resp content")):
            with caplog.at_level(logging.DEBUG, logger="mortis.provider.minimax"):
                out = p.generate_text("audit minimax")
        expected_prompt_hash = sha256_prefix("audit minimax")
        expected_resp_hash = sha256_prefix(out)
        lines = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
        gt_lines = [ln for ln in lines if "method=generate_text" in ln]
        assert gt_lines
        line = gt_lines[0]
        assert f"prompt_hash={expected_prompt_hash}" in line
        assert f"resp_hash={expected_resp_hash}" in line
        assert "elapsed=" in line

    def test_generate_log_does_not_contain_prompt_plaintext(self, caplog):
        """generate() log 绝不含 prompt 原文。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("ok")):
            with caplog.at_level(logging.DEBUG, logger="mortis.provider.minimax"):
                p.generate(_user_msg(_SECRET_PROMPT))
        for r in caplog.records:
            assert _SECRET_PROMPT not in r.getMessage(), (
                f"prompt 原文泄漏: {r.getMessage()}"
            )

    def test_generate_text_log_does_not_contain_plaintext(self, caplog):
        """generate_text() log 不含 prompt / response 原文。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok(_SECRET_RESPONSE)):
            with caplog.at_level(logging.DEBUG, logger="mortis.provider.minimax"):
                out = p.generate_text(_SECRET_PROMPT)
        assert out == _SECRET_RESPONSE
        for r in caplog.records:
            assert _SECRET_PROMPT not in r.getMessage()
            assert _SECRET_RESPONSE not in r.getMessage()


# ============================================================
# ToolAgent._llm_generate 审计日志 (redact 标记)
# ============================================================


class _FakeTool:
    """最小 ToolProtocol — 测试用。"""

    def __init__(self, name: str = "fake:tool"):
        self.name = name

    @property
    def description(self) -> str:
        return "fake tool"

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolLayerResult:
        return ToolLayerResult.ok(self.name, "ok")


class TestLlmGenerateAudit:
    """issue #87 — _llm_generate 成功路径 DEBUG log 含 hash + redact 标记。"""

    def _build(self, provider):
        return ToolAgent(tool=_FakeTool(), provider=provider)

    def test_success_produces_debug_log(self, caplog):
        """成功路径产生 DEBUG 审计 log。"""
        mock = MockProvider(responses=["ok"])
        agent = self._build(provider=mock)
        with caplog.at_level(logging.DEBUG, logger="mortis.toolagent.base"):
            agent._llm_generate("hello")
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("method=_llm_generate" in r.getMessage() for r in records)

    def test_log_contains_prompt_hash(self, caplog):
        """DEBUG log 含 prompt_hash (SHA256 前 16 位)。"""
        mock = MockProvider(responses=["ok"])
        agent = self._build(provider=mock)
        with caplog.at_level(logging.DEBUG, logger="mortis.toolagent.base"):
            agent._llm_generate("hash me")
        expected = sha256_prefix("hash me")
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any(f"prompt_hash={expected}" in r.getMessage() for r in records)

    def test_log_contains_redact_default_false(self, caplog):
        """默认 redact=False, log 应含 redact=False。"""
        mock = MockProvider(responses=["ok"])
        agent = self._build(provider=mock)
        with caplog.at_level(logging.DEBUG, logger="mortis.toolagent.base"):
            agent._llm_generate("hello")
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("redact=False" in r.getMessage() for r in records), (
            "默认 redact 应为 False 并出现在 log 中"
        )

    def test_log_contains_redact_true_when_set(self, caplog):
        """显式传 redact=True 时 log 应含 redact=True。"""
        mock = MockProvider(responses=["ok"])
        agent = self._build(provider=mock)
        with caplog.at_level(logging.DEBUG, logger="mortis.toolagent.base"):
            agent._llm_generate("hello", redact=True)
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("redact=True" in r.getMessage() for r in records), (
            "redact=True 应透传到 log"
        )

    def test_log_does_not_contain_prompt_plaintext(self, caplog):
        """DEBUG log 绝不含 prompt 原文。"""
        mock = MockProvider(responses=["ok"])
        agent = self._build(provider=mock)
        with caplog.at_level(logging.DEBUG, logger="mortis.toolagent.base"):
            agent._llm_generate(_SECRET_PROMPT)
        for r in caplog.records:
            assert _SECRET_PROMPT not in r.getMessage(), (
                f"prompt 原文泄漏: {r.getMessage()}"
            )

    def test_failure_log_contains_hash_and_redact(self, caplog):
        """失败路径 WARNING log 也含 prompt_hash + redact (审计连续性)。"""

        class BadProvider:
            def generate_text(self, prompt, system="", **kwargs):
                raise RuntimeError("provider error")

        agent = self._build(provider=BadProvider())
        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.base"):
            result = agent._llm_generate(_SECRET_PROMPT, redact=True)
        assert result is None
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warns
        expected_hash = sha256_prefix(_SECRET_PROMPT)
        msg = warns[0].getMessage()
        assert f"prompt_hash={expected_hash}" in msg
        assert "redact=True" in msg
        # 原文不应出现在 warning 中
        assert _SECRET_PROMPT not in msg

    def test_redact_not_passed_to_provider(self):
        """redact 是审计标记, 不应透传给 provider.generate_text。"""
        received_kwargs: dict = {}

        class InspectProvider:
            def generate_text(self, prompt, system="", **kwargs):
                received_kwargs.update(kwargs)
                return "ok"

        agent = self._build(provider=InspectProvider())
        agent._llm_generate("hi", redact=True, temperature=0.5)
        assert "redact" not in received_kwargs, "redact 不应透传给 provider"
        assert received_kwargs.get("temperature") == 0.5


# ============================================================
# hash 可追溯性 — 同输入同 hash
# ============================================================


class TestAuditHashTraceability:
    """issue #87 — hash 可追溯: 同输入永远产生同 hash。"""

    def test_same_prompt_same_hash(self):
        assert sha256_prefix("abc") == sha256_prefix("abc")

    def test_different_prompt_different_hash(self):
        assert sha256_prefix("abc") != sha256_prefix("abd")

    def test_hash_length_16(self):
        assert len(sha256_prefix("anything")) == 16

    def test_messages_hash_stable(self):
        msgs = [Message(role="user", content="hello"), Message(role="system", content="s")]
        assert messages_hash(msgs) == messages_hash(msgs)

    def test_messages_hash_differs_by_role(self):
        """role 不同 → hash 不同 (审计可区分)。"""
        a = [Message(role="user", content="x")]
        b = [Message(role="system", content="x")]
        assert messages_hash(a) != messages_hash(b)
