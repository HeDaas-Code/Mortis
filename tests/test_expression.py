"""Test issue #94: 表达方式学习 — 从对话中提取说话风格。

验收链路:
- ``mortis.expression.stats``: 纯函数提取 + vault 按天 JSON 读写 + 聚合格式化
- ``mortis.expression.distill``: LLM 提炼表达模式 + ``<think>`` 清理 + id 生成
- ``LightDreamer.phase_expression_distill``: 无 stats / 空 body / 正常产出 三场景
- ``RuntimeContext.expression_patterns_prompt``: 扫描 tone 目录注入 ``## Expression Patterns (learned)``
- ``RuntimeContext.messages_for_provider``: expression 段注入位置 (growth 之后)
- ``RuntimeContext.growth_context_for_task``: 排除 expression growth (避免重复注入)
- ``ChatService.send``: 对话后触发 ``record_turn_stats`` 写入 stats 文件
- ``ChatService._build_messages``: 含 expression patterns 段
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.expression.distill import (
    DEFAULT_DISTILL_DAYS,
    EXPRESSION_ID_PREFIX,
    distill_expression_patterns,
    expression_growth_id,
    is_expression_growth,
)
from mortis.expression.stats import (
    EXPRESSION_STATS_DIR,
    SideStats,
    TurnStats,
    build_turn_stats,
    extract_side_stats,
    format_stats_for_prompt,
    load_recent_stats,
    record_turn_stats,
)
from mortis.growth.model import Dimension
from mortis.memory import Session, Thread
from mortis.provider import MockProvider
from mortis.provider.base import Message
from mortis.runtime import MasterRuntime, RuntimeContext
from mortis.seed import Seed
from mortis.vault import Vault
from mortis.web.chat import ChatService


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(tmp_path)


@pytest.fixture
def seed() -> Seed:
    return Seed(
        identity="I", values="V", tone="简短。不注水。",
        agency="A", relations="R", creativity="C", mortality="M",
    )


@pytest.fixture
def master(seed: Seed, vault: Vault) -> MasterRuntime:
    return MasterRuntime(
        seed=seed,
        vault=vault,
        provider=MockProvider(),
        session=Session(session_id="test-expression"),
    )


def _make_expression_growth(
    vault: Vault,
    growth_id: str,
    body: str,
    confidence: float = 0.3,
) -> None:
    """直接写一个 expression- 开头的 tone growth 到 vault。"""
    from mortis.dream.crystallize import make_candidate
    g = make_candidate(
        body=body,
        dimension=Dimension.TONE,
        source_sessions=[],
        valence=0.0,
        arousal=0.3,
        id=growth_id,
    )
    # 覆盖 confidence (make_candidate 默认 0.3, 测试可显式传不同值)
    if confidence != 0.3:
        g = g.__class__(**{**g.__dict__, "confidence": confidence})
    vault.write_growth(g)


# ============================================================
# stats: extract_side_stats (纯函数)
# ============================================================


class TestExtractSideStats:
    def test_empty_text_returns_zero_stats(self) -> None:
        s = extract_side_stats("")
        assert s.avg_sentence_length == 0.0
        assert s.sentence_count == 0
        assert s.char_count == 0
        assert s.top_words == []
        assert s.discourse_markers == {}

    def test_whitespace_only_returns_zero(self) -> None:
        s = extract_side_stats("   \n  \t  ")
        assert s.sentence_count == 0
        assert s.char_count == 0  # len(text) 仍计入空白? 不, 空文本分支返回零
        # 注: extract_side_stats 检查 text.strip(), 空白返回零 SideStats

    def test_chinese_text_extracts_bigrams_and_markers(self) -> None:
        text = "嗯,今天天气不错啊。我们去散步吧?"
        s = extract_side_stats(text)
        assert s.char_count == len(text)
        assert s.sentence_count >= 2  # 至少两句 (。和? 分隔)
        assert s.avg_sentence_length > 0
        # 语气词命中
        assert "嗯" in s.discourse_markers
        assert "啊" in s.discourse_markers
        assert "吧" in s.discourse_markers
        # 中文 bigram 至少有若干
        assert len(s.top_words) > 0

    def test_english_text_extracts_word_tokens(self) -> None:
        text = "Hello world. This is a test sentence with hello again."
        s = extract_side_stats(text)
        assert s.sentence_count == 2
        # ASCII 词被提取
        words = [w for w, _ in s.top_words]
        assert "hello" in words  # 出现 2 次, 应进 top

    def test_question_ratio(self) -> None:
        text = "是吗?真的?不是。"
        s = extract_side_stats(text)
        # 含 2 个 ? 和 1 个 。 → 疑问占比 2/3
        assert s.question_ratio > 0
        assert s.question_ratio <= 1.0

    def test_round_trip_dict(self) -> None:
        text = "嗯,测试一下啊。"
        s = extract_side_stats(text)
        d = s.to_dict()
        s2 = SideStats.from_dict(d)
        assert s2.avg_sentence_length == s.avg_sentence_length
        assert s2.char_count == s.char_count
        assert s2.discourse_markers == s.discourse_markers
        assert s2.top_words == s.top_words


# ============================================================
# stats: build_turn_stats + vault 读写
# ============================================================


class TestTurnStatsVaultIO:
    def test_build_turn_stats_has_timestamp_and_both_sides(self) -> None:
        ts = build_turn_stats("你好啊", "嗯,你好。")
        assert ts.timestamp  # 非空 ISO8601
        assert ts.user_stats.char_count == 3  # "你好啊"
        assert ts.mortis_stats.char_count == 5  # "嗯,你好。" (含半角逗号+句号)
        assert "啊" in ts.user_stats.discourse_markers
        assert "嗯" in ts.mortis_stats.discourse_markers

    def test_record_turn_stats_creates_daily_file(self, vault: Vault) -> None:
        result = record_turn_stats(vault, "你好", "嗯,你好。")
        assert result is not None
        date_str = result.timestamp[:10]
        rel = f"{EXPRESSION_STATS_DIR}/{date_str}.json"
        assert vault.exists(rel)
        # 文件内容是 JSON array, 含 1 条
        data = json.loads(vault.read(rel).content)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["user_stats"]["char_count"] == 2

    def test_record_turn_stats_appends_to_existing(self, vault: Vault) -> None:
        now = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
        record_turn_stats(vault, "第一句", "回复一", now=now)
        record_turn_stats(vault, "第二句", "回复二", now=now)
        date_str = now.strftime("%Y-%m-%d")
        rel = f"{EXPRESSION_STATS_DIR}/{date_str}.json"
        data = json.loads(vault.read(rel).content)
        assert len(data) == 2
        assert data[0]["user_stats"]["char_count"] == 3
        assert data[1]["user_stats"]["char_count"] == 3

    def test_record_turn_stats_silent_failure_on_bad_vault(self, tmp_path: Path) -> None:
        """vault.write 抛异常时 record_turn_stats 返回 None, 不传播。"""
        class _BadVault:
            root = tmp_path
            def exists(self, *a, **k): return False
            def read(self, *a, **k): raise RuntimeError("bad")
            def write(self, *a, **k): raise RuntimeError("bad vault")

        result = record_turn_stats(_BadVault(), "x", "y")  # type: ignore[arg-type]
        assert result is None

    def test_load_recent_stats_returns_chronological(self, vault: Vault) -> None:
        """读最近 N 天, 按时间顺序 (旧→新)。"""
        # 用动态日期避免 time-bomb (issue #78)
        from datetime import timedelta
        today = datetime.now(tz=timezone.utc)
        yesterday = today - timedelta(days=1)
        record_turn_stats(vault, "昨", "y", now=yesterday)
        record_turn_stats(vault, "今", "t", now=today)
        # days=7 应能读到两条
        turns = load_recent_stats(vault, days=7)
        assert len(turns) == 2
        # 验证顺序: 昨天 (offset 小) 在前
        assert turns[0].user_stats.char_count == 1  # "昨"
        assert turns[1].user_stats.char_count == 1  # "今"

    def test_load_recent_stats_missing_files_skipped(self, vault: Vault) -> None:
        """无任何 stats 文件 → 返回空列表, 不抛异常。"""
        turns = load_recent_stats(vault, days=7)
        assert turns == []

    def test_load_recent_stats_corrupt_file_skipped(self, vault: Vault) -> None:
        """损坏 JSON 文件被跳过, 不影响其他天。"""
        from datetime import timedelta
        today = datetime.now(tz=timezone.utc)
        # 写一份合法的今天 stats
        record_turn_stats(vault, "合法", "ok", now=today)
        # 把昨天的文件写成损坏 JSON (动态日期)
        yesterday = today - timedelta(days=1)
        bad_rel = f"{EXPRESSION_STATS_DIR}/{yesterday.strftime('%Y-%m-%d')}.json"
        vault.write(bad_rel, "{not valid json")
        turns = load_recent_stats(vault, days=7)
        assert len(turns) == 1  # 只读到今天那条


# ============================================================
# stats: format_stats_for_prompt (聚合格式化)
# ============================================================


class TestFormatStatsForPrompt:
    def test_empty_returns_empty_string(self) -> None:
        assert format_stats_for_prompt([]) == ""

    def test_aggregates_multiple_turns(self) -> None:
        ts1 = build_turn_stats("嗯,你好啊。", "嗯,你好。")
        ts2 = build_turn_stats("今天呢?", "今天不错吧。")
        text = format_stats_for_prompt([ts1, ts2])
        assert "轮次数: 2" in text
        assert "用户平均句长" in text
        assert "Mortis 平均句长" in text
        # 语气词聚合
        assert "嗯" in text


# ============================================================
# distill: expression_growth_id + is_expression_growth
# ============================================================


class TestExpressionGrowthId:
    def test_id_format_with_default_now(self) -> None:
        gid = expression_growth_id()
        assert gid.startswith(EXPRESSION_ID_PREFIX)
        # 格式: expression-YYYY-MM-DD
        date_part = gid[len(EXPRESSION_ID_PREFIX):]
        assert len(date_part) == 10
        assert date_part[4] == "-" and date_part[7] == "-"

    def test_id_format_with_explicit_now(self) -> None:
        now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
        assert expression_growth_id(now=now) == "expression-2026-06-30"

    def test_same_day_overwrites(self) -> None:
        """同一天的两个时刻 → 同一 id (覆盖语义)。"""
        morning = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)
        evening = datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc)
        assert expression_growth_id(now=morning) == expression_growth_id(now=evening)

    def test_different_days_different_ids(self) -> None:
        d1 = datetime(2026, 6, 29, tzinfo=timezone.utc)
        d2 = datetime(2026, 6, 30, tzinfo=timezone.utc)
        assert expression_growth_id(now=d1) != expression_growth_id(now=d2)


class TestIsExpressionGrowth:
    def test_matches_expression_prefix(self) -> None:
        assert is_expression_growth("expression-2026-06-30") is True

    def test_rejects_dream_prefix(self) -> None:
        assert is_expression_growth("dream-2026-06-30-001") is False

    def test_rejects_empty_or_none(self) -> None:
        assert is_expression_growth("") is False
        assert is_expression_growth(None) is False  # type: ignore[arg-type]


# ============================================================
# distill: distill_expression_patterns (LLM 调用)
# ============================================================


class TestDistillExpressionPatterns:
    def test_empty_turns_returns_empty_body(self) -> None:
        result = distill_expression_patterns(MockProvider(), [])
        assert result["body"] == ""
        assert result["turn_count"] == 0

    def test_distill_returns_llm_body(self) -> None:
        provider = MockProvider(responses=[
            "- 偏好短句, 避免长篇大论\n- 复用 '嗯' 表示认可\n- 疑问句用 '?' 结尾"
        ])
        turns = [build_turn_stats("嗯?", "回复。")]
        result = distill_expression_patterns(provider, turns)
        assert result["turn_count"] == 1
        assert "- 偏好短句" in result["body"]
        assert "嗯" in result["body"]

    def test_distill_strips_think_tags(self) -> None:
        """LLM 返回含 <think>...</think> 时被剥离。"""
        provider = MockProvider(responses=[
            "<think>这是内部思考, 不应注入</think>\n- 模式一\n- 模式二"
        ])
        turns = [build_turn_stats("hi", "yo")]
        result = distill_expression_patterns(provider, turns)
        assert "<think>" not in result["body"]
        assert "内部思考" not in result["body"]
        assert "- 模式一" in result["body"]

    def test_distill_llm_failure_returns_empty_body(self) -> None:
        """LLM 调用抛异常 → 静默失败返回空 body。"""
        class _BoomProvider(MockProvider):
            def generate(self, messages, **kwargs):  # type: ignore[override]
                raise RuntimeError("LLM down")
        turns = [build_turn_stats("hi", "yo")]
        result = distill_expression_patterns(_BoomProvider(), turns)
        assert result["body"] == ""
        assert result["turn_count"] == 1  # turn_count 仍记录


# ============================================================
# dream phase: LightDreamer.phase_expression_distill
# ============================================================


class TestPhaseExpressionDistill:
    def _make_dreamer(self, vault: Vault, responses: list[str] | None = None):
        from mortis.dream.light import LightDreamer
        return LightDreamer(vault, MockProvider(responses=responses))

    def test_no_stats_skips_ok(self, vault: Vault) -> None:
        """vault 无 expression-stats → ok=True, reason=no_stats。"""
        dreamer = self._make_dreamer(vault)
        trace = dreamer.phase_expression_distill()
        assert trace.ok is True
        assert trace.detail["reason"] == "no_stats"
        assert trace.detail["loaded"] == 0
        # 不应写任何 growth
        assert vault.list_growths(dimension=Dimension.TONE) == []

    def test_with_stats_writes_tone_growth(self, vault: Vault) -> None:
        """有 stats + LLM 产出 body → 写 tone growth (id=expression-<date>)。"""
        # 先写入一份 stats
        record_turn_stats(vault, "嗯,你好啊", "嗯,你好。", now=datetime.now(tz=timezone.utc))
        dreamer = self._make_dreamer(vault, responses=[
            "- 偏好短句\n- 复用 '嗯' 表示认可"
        ])
        trace = dreamer.phase_expression_distill()
        assert trace.ok is True
        assert trace.detail["dimension"] == Dimension.TONE.value
        assert "growth_id" in trace.detail
        assert trace.detail["growth_id"].startswith(EXPRESSION_ID_PREFIX)
        assert trace.detail["turn_count"] >= 1
        assert trace.detail["body_len"] > 0
        # vault 里确有该 growth
        tone_paths = vault.list_growths(dimension=Dimension.TONE)
        assert any(EXPRESSION_ID_PREFIX in p for p in tone_paths)

    def test_empty_body_skips_ok(self, vault: Vault) -> None:
        """有 stats + LLM 产出空 body → ok=True, reason=empty_body, 不写 growth。"""
        record_turn_stats(vault, "hi", "yo", now=datetime.now(tz=timezone.utc))
        dreamer = self._make_dreamer(vault, responses=["   "])  # 空白 body
        trace = dreamer.phase_expression_distill()
        assert trace.ok is True
        assert trace.detail["reason"] == "empty_body"
        # 不写 growth
        assert vault.list_growths(dimension=Dimension.TONE) == []

    def test_same_day_overwrites_growth(self, vault: Vault) -> None:
        """同一天重复 dream → 同 id 覆盖 (取最新模式)。"""
        now = datetime.now(tz=timezone.utc)
        record_turn_stats(vault, "hi", "yo", now=now)
        # 第一次 dream
        dreamer1 = self._make_dreamer(vault, responses=["- 模式A"])
        dreamer1.phase_expression_distill()
        # 第二次 dream (同天)
        dreamer2 = self._make_dreamer(vault, responses=["- 模式B"])
        dreamer2.phase_expression_distill()
        tone_paths = vault.list_growths(dimension=Dimension.TONE)
        # 仍是 1 个文件 (同 id 覆盖)
        expr_paths = [p for p in tone_paths if EXPRESSION_ID_PREFIX in p]
        assert len(expr_paths) == 1
        # 内容是最新模式 B
        g = vault.read_growth(expr_paths[0])
        assert "模式B" in g.body


# ============================================================
# context: expression_patterns_prompt
# ============================================================


class TestExpressionPatternsPrompt:
    def _make_ctx(self, master: MasterRuntime) -> RuntimeContext:
        thread = Thread(
            thread_id="th-expr-test",
            session_id=master.session.session_id,
            task="测试 expression 注入",
        )
        return master.make_context(thread)

    def test_no_expression_growth_returns_empty(self, master: MasterRuntime) -> None:
        ctx = self._make_ctx(master)
        assert ctx.expression_patterns_prompt() == ""

    def test_non_expression_tone_growth_ignored(self, master: MasterRuntime) -> None:
        """普通 tone growth (非 expression- 前缀) 不被 expression 段注入。"""
        from mortis.dream.crystallize import make_candidate
        g = make_candidate(
            body="普通 tone 笔记",
            dimension=Dimension.TONE,
            source_sessions=[],
            valence=0.0,
            arousal=0.3,
            id="dream-2026-06-30-001",
        )
        master.vault.write_growth(g)
        ctx = self._make_ctx(master)
        assert ctx.expression_patterns_prompt() == ""

    def test_expression_growth_injected(self, master: MasterRuntime) -> None:
        _make_expression_growth(
            master.vault,
            "expression-2026-06-30",
            "- 偏好短句\n- 复用 '嗯'",
        )
        ctx = self._make_ctx(master)
        prompt = ctx.expression_patterns_prompt()
        assert prompt.startswith("## Expression Patterns (learned)")
        assert "- 偏好短句" in prompt
        assert "嗯" in prompt

    def test_max_items_limits_injection(self, master: MasterRuntime) -> None:
        """max_items 限制注入条数 (最新在前)。"""
        # 写 3 天的 expression growth
        _make_expression_growth(master.vault, "expression-2026-06-28", "- 模式旧")
        _make_expression_growth(master.vault, "expression-2026-06-29", "- 模式中")
        _make_expression_growth(master.vault, "expression-2026-06-30", "- 模式新")
        ctx = self._make_ctx(master)
        prompt = ctx.expression_patterns_prompt(max_items=2)
        # 最新两条 (06-30, 06-29)
        assert "模式新" in prompt
        assert "模式中" in prompt
        assert "模式旧" not in prompt

    def test_silent_failure_on_vault_error(self, tmp_path: Path) -> None:
        """vault 异常时返回空串, 不传播。"""
        class _BadVault:
            root = tmp_path
            def list_growths(self, dimension=None): raise RuntimeError("boom")
        ctx = RuntimeContext.__new__(RuntimeContext)
        ctx.vault = _BadVault()  # type: ignore[assignment]
        assert ctx.expression_patterns_prompt() == ""


# ============================================================
# context: messages_for_provider 注入位置
# ============================================================


class TestMessagesForProviderInjection:
    def test_expression_injected_after_growth(self, master: MasterRuntime) -> None:
        """expression 段在 growth 段之后, step output 之前。"""
        # 写一个 expression growth
        _make_expression_growth(master.vault, "expression-2026-06-30", "- 表达模式X")
        # 写一个普通高置信度 growth (会被 growth_context_for_task 检索到)
        from mortis.dream.crystallize import make_candidate
        g = make_candidate(
            body="测试相关 growth 内容",
            dimension=Dimension.TONE,
            source_sessions=[],
            valence=0.0,
            arousal=0.3,
            id="dream-2026-06-29-001",
        )
        # 提升置信度让 growth_context_for_task (min_confidence=0.5) 能检索到
        g = g.__class__(**{**g.__dict__, "confidence": 0.8})
        master.vault.write_growth(g)

        thread = Thread(
            thread_id="th-inj",
            session_id=master.session.session_id,
            task="测试相关 growth",
        )
        thread.add_step(__import__("mortis.memory", fromlist=["StepRecord"]).StepRecord(
            step_id="s1", step_type="act", input="in", output="step output 内容",
        ))
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()

        # 找到各段的位置
        expr_idx = None
        growth_idx = None
        step_idx = None
        for i, m in enumerate(msgs):
            if m.role == "system" and "## Expression Patterns (learned)" in m.content:
                expr_idx = i
            if m.role == "system" and "## 当前人格成长" in m.content:
                growth_idx = i
            if m.role == "assistant" and "step output 内容" in m.content:
                step_idx = i

        assert growth_idx is not None, "growth 段应被注入"
        assert expr_idx is not None, "expression 段应被注入"
        assert step_idx is not None, "step output 应存在"
        # 顺序: growth < expression < step
        assert growth_idx < expr_idx < step_idx

    def test_no_expression_growth_no_injection(self, master: MasterRuntime) -> None:
        """无 expression growth 时 messages_for_provider 不含 expression 段。"""
        thread = Thread(
            thread_id="th-no-expr",
            session_id=master.session.session_id,
            task="无 expression",
        )
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        for m in msgs:
            assert "## Expression Patterns (learned)" not in m.content


# ============================================================
# context: growth_context_for_task 排除 expression growth
# ============================================================


class TestGrowthContextExcludesExpression:
    def test_expression_growth_not_in_growth_context(self, master: MasterRuntime) -> None:
        """expression growth 不应出现在 growth_context_for_task 的输出里。"""
        # 写一个 expression growth (body 含关键词 'expression-test')
        _make_expression_growth(
            master.vault, "expression-2026-06-30",
            "expression-test 关键内容", confidence=0.8,
        )
        thread = Thread(
            thread_id="th-filter",
            session_id=master.session.session_id,
            task="expression-test",
        )
        ctx = master.make_context(thread)
        prompt = ctx.growth_context_for_task("expression-test")
        # growth 段不应包含 expression growth
        assert "## 当前人格成长" not in prompt or "expression-2026-06-30" not in prompt

    def test_normal_growth_still_in_growth_context(self, master: MasterRuntime) -> None:
        """普通 growth 仍正常被 growth_context_for_task 检索。"""
        from mortis.dream.crystallize import make_candidate
        g = make_candidate(
            body="normal-growth-test 普通内容",
            dimension=Dimension.TONE,
            source_sessions=[],
            valence=0.0,
            arousal=0.3,
            id="dream-2026-06-29-001",
        )
        g = g.__class__(**{**g.__dict__, "confidence": 0.8})
        master.vault.write_growth(g)
        thread = Thread(
            thread_id="th-normal",
            session_id=master.session.session_id,
            task="normal-growth-test",
        )
        ctx = master.make_context(thread)
        prompt = ctx.growth_context_for_task("normal-growth-test")
        assert "## 当前人格成长" in prompt
        assert "普通内容" in prompt


# ============================================================
# chat: send 触发 record_turn_stats
# ============================================================


class TestChatTriggersStats:
    def test_send_writes_expression_stats(self, master: MasterRuntime) -> None:
        """ChatService.send 后, expression-stats 文件被写入。"""
        # MockProvider 默认返回 [mock:<首行>]
        chat = ChatService(master)
        resp = chat.send("嗯,你好啊")
        assert resp.message  # 有回复

        # 验证 stats 文件被写
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        rel = f"{EXPRESSION_STATS_DIR}/{today}.json"
        assert master.vault.exists(rel), "expression-stats 文件应被 send 触发写入"
        data = json.loads(master.vault.read(rel).content)
        assert isinstance(data, list)
        assert len(data) >= 1
        # user 侧统计含 '啊' 语气词
        turn = data[0]
        assert "啊" in turn["user_stats"]["discourse_markers"]

    def test_stream_writes_expression_stats(self, master: MasterRuntime) -> None:
        """ChatService.stream 后, expression-stats 文件也被写入。"""
        chat = ChatService(master)
        # 消费完 generator
        chunks = list(chat.stream("嗯,散步吧"))
        assert chunks  # 有 chunk

        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        rel = f"{EXPRESSION_STATS_DIR}/{today}.json"
        assert master.vault.exists(rel), "expression-stats 文件应被 stream 触发写入"

    def test_build_messages_includes_expression_segment(self, master: MasterRuntime) -> None:
        """vault 有 expression growth 时, _build_messages 注入对应段。"""
        _make_expression_growth(
            master.vault, "expression-2026-06-30", "- 表达模式Z",
        )
        chat = ChatService(master)
        conv = chat.create_conversation()
        conv.add_user("测试")
        msgs = chat._build_messages(conv)
        expr_msgs = [m for m in msgs if "## Expression Patterns (learned)" in m.content]
        assert len(expr_msgs) == 1
        assert "表达模式Z" in expr_msgs[0].content

    def test_stats_failure_does_not_block_chat(self, tmp_path: Path) -> None:
        """record_turn_stats 抛异常时, send 仍正常返回 (静默失败)。"""
        vault = Vault(tmp_path)
        master = MasterRuntime(
            seed=Seed(identity="I", values="V", tone="T", agency="A",
                      relations="R", creativity="C", mortality="M"),
            vault=vault,
            provider=MockProvider(responses=["回复"]),
            session=Session(session_id="bad-vault-test"),
        )
        # 破坏 vault.write 让 record_turn_stats 失败
        original_write = vault.write
        call_count = {"n": 0}
        def flaky_write(rel_path, content, whitelist=None):
            call_count["n"] += 1
            # 只在写 expression-stats 时抛错 (第 3 次以后的写, conversation 文件之后)
            if EXPRESSION_STATS_DIR in rel_path:
                raise RuntimeError("simulated stats write failure")
            return original_write(rel_path, content, whitelist=whitelist)
        vault.write = flaky_write  # type: ignore[assignment]

        chat = ChatService(master)
        resp = chat.send("你好")  # 不应抛异常
        assert resp.message == "回复"
