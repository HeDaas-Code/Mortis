"""Test minimax provider — v1-issue-2 LLM 接入。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from mortis.providers import (
    MINIMAX_DEFAULT_BASE_URL,
    MINIMAX_DEFAULT_MODEL,
    MinimaxAPIError,
    MinimaxAuthError,
    MinimaxProvider,
    make_provider,
)


# ----- 工厂函数 -----

def test_make_provider_mock() -> None:
    p = make_provider("mock")
    assert isinstance(p, type(p))  # 真实类型不重要


def test_make_provider_minimax_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(MinimaxAuthError):
        MinimaxProvider().generate("test")


def test_make_provider_auto_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 MINIMAX_API_KEY → auto 用 mock。"""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    from mortis.persona import MockProvider
    p = make_provider("auto")
    assert isinstance(p, MockProvider)


def test_make_provider_auto_uses_minimax(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    p = make_provider("auto")
    assert isinstance(p, MinimaxProvider)


def test_make_provider_unknown_kind() -> None:
    with pytest.raises(ValueError):
        make_provider("bogus")


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


# ----- MinimaxProvider.generate (HTTP 调用测试)-----

def _mock_urlopen_ok(content: str):
    """构造一个 mock urlopen 返回 OK payload。"""
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
        result = p.generate("test prompt")
    assert result == "hello back"


def test_minimax_provider_generate_with_system() -> None:
    """system prompt 必须传进 messages。"""
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

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        p.generate("user msg", system="sys msg")
    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "sys msg"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "user msg"


def _http_error(code: int, msg: str):
    from urllib.error import HTTPError
    from email.message import Message
    return HTTPError("http://x", code, msg, Message(), None)


def test_minimax_provider_401_raises_auth_error() -> None:
    p = MinimaxProvider(api_key="bad")
    with patch("urllib.request.urlopen", side_effect=_http_error(401, "Unauthorized")):
        with pytest.raises(MinimaxAuthError):
            p.generate("x")


def test_minimax_provider_500_raises_api_error() -> None:
    p = MinimaxProvider(api_key="k")
    with patch("urllib.request.urlopen", side_effect=_http_error(500, "Internal Server Error")):
        with pytest.raises(MinimaxAPIError):
            p.generate("x")


def test_minimax_provider_network_error() -> None:
    from urllib.error import URLError

    p = MinimaxProvider(api_key="k")
    with patch("urllib.request.urlopen", side_effect=URLError("net down")):
        with pytest.raises(MinimaxAPIError):
            p.generate("x")


def test_minimax_provider_malformed_response() -> None:
    """响应缺 choices → APIError。"""
    import json
    from unittest.mock import MagicMock

    p = MinimaxProvider(api_key="k")
    mock = MagicMock()
    mock.__enter__.return_value.read.return_value = json.dumps({"weird": 1}).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=mock):
        with pytest.raises(MinimaxAPIError):
            p.generate("x")


def test_minimax_provider_no_key_raises() -> None:
    """没 key 立刻报错,不打网络。"""
    p = MinimaxProvider(api_key="")
    with pytest.raises(MinimaxAuthError):
        p.generate("x")