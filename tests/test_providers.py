"""Test LLM providers — mock / minimax。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from mortis.provider import (
    MinimaxAPIError,
    MinimaxAuthError,
    MinimaxProvider,
    MockProvider,
    make_provider,
    Message,
)
from mortis.provider.minimax import MINIMAX_DEFAULT_BASE_URL, MINIMAX_DEFAULT_MODEL


def _user_msg(content: str) -> list[Message]:
    return [Message(role="user", content=content)]


# ----- 工厂函数 -----

def test_make_provider_mock() -> None:
    p = make_provider("mock")
    assert isinstance(p, type(p))


def test_make_provider_minimax_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(MinimaxAuthError):
        MinimaxProvider().generate(_user_msg("test"))


def test_make_provider_auto_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    p = make_provider("auto")
    assert isinstance(p, MockProvider)


def test_make_provider_auto_uses_minimax(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    p = make_provider("auto")
    assert isinstance(p, MinimaxProvider)


def test_make_provider_unknown_kind() -> None:
    with pytest.raises(ValueError):
        make_provider("bogus")


# ----- MockProvider -----

def test_mock_provider_returns_deterministic() -> None:
    p = MockProvider()
    a = p.generate(_user_msg("hello world"))
    b = p.generate(_user_msg("hello world"))
    assert a.content == b.content


def test_mock_provider_uses_first_line() -> None:
    p = MockProvider()
    out = p.generate(_user_msg("line one\nline two"))
    assert "line one" in out.content


def test_mock_provider_empty() -> None:
    p = MockProvider()
    out = p.generate(_user_msg(""))
    assert "[mock:" in out.content


def test_mock_provider_generate_text() -> None:
    p = MockProvider()
    out = p.generate_text("hello")
    assert "[mock:" in out


# ----- MinimaxProvider 配置 -----

def test_minimax_provider_default_url() -> None:
    p = MinimaxProvider(api_key="k")
    assert p._base_url == MINIMAX_DEFAULT_BASE_URL


def test_minimax_provider_strips_trailing_slash() -> None:
    p = MinimaxProvider(api_key="k", base_url="https://x.com/v1/")
    assert p._base_url == "https://x.com/v1"


def test_minimax_provider_default_model() -> None:
    p = MinimaxProvider(api_key="k")
    assert p._model == MINIMAX_DEFAULT_MODEL


def test_minimax_provider_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key")
    p = MinimaxProvider()
    assert p._api_key == "env-key"


# ----- MinimaxProvider.generate (HTTP 调用测试) -----

def _mock_urlopen_ok(content: str):
    import json
    from unittest.mock import MagicMock

    payload = json.dumps({
        "choices": [{"message": {"content": content}}],
    }).encode("utf-8")
    mock = MagicMock()
    mock.__enter__.return_value.read.return_value = payload
    return mock


def test_minimax_provider_generate_success() -> None:
    p = MinimaxProvider(api_key="k")
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("hello back")):
        result = p.generate(_user_msg("test prompt"))
    assert result.content == "hello back"


def test_minimax_provider_generate_with_system() -> None:
    import json
    from unittest.mock import MagicMock

    p = MinimaxProvider(api_key="k")
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        captured.update(body)
        payload = json.dumps({
            "choices": [{"message": {"content": "ok"}}],
        }).encode("utf-8")
        m = MagicMock()
        m.__enter__.return_value.read.return_value = payload
        return m

    msgs = [
        Message(role="system", content="sys msg"),
        Message(role="user", content="user msg"),
    ]
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        p.generate(msgs)
    msgs_sent = captured["messages"]
    assert msgs_sent[0]["role"] == "system"
    assert msgs_sent[0]["content"] == "sys msg"
    assert msgs_sent[1]["role"] == "user"
    assert msgs_sent[1]["content"] == "user msg"


def _http_error(code: int, msg: str):
    from urllib.error import HTTPError
    return HTTPError("http://x", code, msg, {}, None)


def test_minimax_provider_401_raises_auth_error() -> None:
    p = MinimaxProvider(api_key="bad")
    with patch("urllib.request.urlopen", side_effect=_http_error(401, "Unauthorized")):
        with pytest.raises(MinimaxAuthError):
            p.generate(_user_msg("x"))


def test_minimax_provider_500_raises_api_error() -> None:
    p = MinimaxProvider(api_key="k")
    with patch("urllib.request.urlopen", side_effect=_http_error(500, "Internal Server Error")):
        with pytest.raises(MinimaxAPIError):
            p.generate(_user_msg("x"))


def test_minimax_provider_network_error() -> None:
    from urllib.error import URLError

    p = MinimaxProvider(api_key="k")
    with patch("urllib.request.urlopen", side_effect=URLError("net down")):
        with pytest.raises(MinimaxAPIError):
            p.generate(_user_msg("x"))


def test_minimax_provider_malformed_response() -> None:
    import json
    from unittest.mock import MagicMock

    p = MinimaxProvider(api_key="k")
    mock = MagicMock()
    mock.__enter__.return_value.read.return_value = json.dumps({"weird": 1}).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=mock):
        with pytest.raises(MinimaxAPIError):
            p.generate(_user_msg("x"))


def test_minimax_provider_no_key_raises() -> None:
    p = MinimaxProvider(api_key="")
    with pytest.raises(MinimaxAuthError):
        p.generate(_user_msg("x"))
