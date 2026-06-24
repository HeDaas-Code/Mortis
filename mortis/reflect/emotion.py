"""Mortis reflect — emotion 标注。

issue #21: REFLECT phase 的情绪打分。
- valence ∈ [-1.0, 1.0]: 负向 ↔ 正向
- arousal ∈ [0.0, 1.0]: 冷静 ↔ 激动

实现要点:
- module-level 缓存 `dict[str, tuple[float, float]]`,key 是 session_path
  (同一 session 不重复打分 — 节省 token 且情绪基调稳定)。
- 通过 LLMProviderProtocol.generate_text() 走单轮 prompt 拿 JSON。
  prompt 强制 LLM 输出 `{"valence": <num>, "arousal": <num>}`。
- parse 失败 → 回退 (0.0, 0.0) + warning log。
- 不写 vault: 缓存只活在本进程内(情绪是 LLM 推断,重新推理可能不同,
  持久化反而引入"哪个时刻的情绪值更准"的口径问题)。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from mortis.provider.base import LLMProviderProtocol
from mortis.redact import redact_snippet


# 模块日志 — 配 log warning 即可
_logger = logging.getLogger(__name__)

# module-level 缓存:session_path -> (valence, arousal)
# 全局共享,反射测试需要 clear_cache() 避免跨测试污染
_cache: dict[str, tuple[float, float]] = {}


# ----- prompt 模板 -----

# 强制 LLM 输出 JSON,避免长段叙述被截断带来的 parse 失败
_EMOTION_PROMPT = """请阅读以下会话内容,根据文风与措辞判断**整体情绪基调**。

要求:
1. valence: -1.0(很消极/痛苦) ↔ 0.0(中性) ↔ +1.0(很积极/愉悦)
2. arousal: 0.0(很冷静/平淡) ↔ 1.0(很激动/强烈)
3. **只输出一个 JSON 对象**,形如: {"valence": 0.3, "arousal": 0.6}
4. 不要解释,不要 markdown 代码块包裹,不要其他文字

会话内容:
\"\"\"
{session_text}
\"\"\"
"""


# JSON 容错提取:LLM 有时会用 ```json ... ``` 包裹,有时夹杂前后文字
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\"valence\"[^{}]*\"arousal\"[^{}]*\}")


def clear_cache() -> None:
    """清空 module-level 缓存 — 供测试用。"""
    _cache.clear()


def score_emotion(
    provider: LLMProviderProtocol,
    session_path: str,
    session_text: str,
) -> tuple[float, float]:
    """给一段会话内容打情绪分,按 session_path 缓存。

    Args:
        provider: LLM provider(调 generate_text)。
        session_path: 缓存 key。约定是 session 的相对路径
            (e.g. `mortis-journal/sessions/2026-06-22/session-abc.json`),
            但**任何字符串**都行 — 唯一性 = 缓存命中 = 不重打。
        session_text: 喂给 LLM 的会话纯文本(已拼好的 summary)。

    Returns:
        (valence, arousal),都已被 clamp 到合法范围。
        parse 失败 → (0.0, 0.0)。
    """
    if session_path in _cache:
        return _cache[session_path]

    # 不走 str.format — session_text 里若含 `{` 会被当占位符(典型场景:JSON 测试
    # fixture 喂入带花括号的 LLM 响应会破坏 prompt 自身)。
    text = session_text or "(empty)"
    # issue #86: 发 LLM 前 redact owner 私密字段 (dream callouts / emotion 标签 /
    # subconscious / emotional_*), 防止 session 全文泄漏给外部 LLM。
    # 复用共享模块 mortis.redact.redact_snippet, 保证所有 LLM 入口 redact 一致
    # (HARNESS.md '数据不外流' 原则)。
    safe_text = redact_snippet(text)
    prompt = _EMOTION_PROMPT.replace("{session_text}", safe_text)
    raw = provider.generate_text(prompt)
    valence, arousal = _parse_emotion_response(raw)
    valence, arousal = _clamp(valence, arousal)
    _cache[session_path] = (valence, arousal)
    return valence, arousal


# ============================================================
# 内部
# ============================================================


def _parse_emotion_response(raw: str) -> tuple[float, float]:
    """从 LLM 响应中解析 (valence, arousal)。失败回退 (0.0, 0.0)。"""
    if not raw:
        _logger.warning("emotion scorer: empty response, fallback to (0,0)")
        return 0.0, 0.0

    # 策略 1: 严格 JSON parse
    try:
        data = json.loads(raw)
        v, a = _extract_pair(data)
        if v is not None and a is not None:
            return v, a
    except (json.JSONDecodeError, ValueError):
        pass

    # 策略 2: 用正则挑出最像 JSON object 的子串
    m = _JSON_OBJECT_RE.search(raw)
    if m:
        try:
            data = json.loads(m.group(0))
            v, a = _extract_pair(data)
            if v is not None and a is not None:
                return v, a
        except (json.JSONDecodeError, ValueError):
            pass

    _logger.warning(
        "emotion scorer: failed to parse response, fallback to (0,0). raw=%r",
        raw[:200],
    )
    return 0.0, 0.0


def _extract_pair(data: Any) -> tuple[float | None, float | None]:
    """从已 parse 的 JSON 数据中提取 valence/arousal。"""
    if not isinstance(data, dict):
        return None, None
    if "valence" not in data or "arousal" not in data:
        return None, None
    try:
        v = float(data["valence"])
        a = float(data["arousal"])
    except (TypeError, ValueError):
        return None, None
    return v, a


def _clamp(valence: float, arousal: float) -> tuple[float, float]:
    """夹到合法范围 — LLM 偶尔会越界。"""
    v = max(-1.0, min(1.0, valence))
    a = max(0.0, min(1.0, arousal))
    return v, a
