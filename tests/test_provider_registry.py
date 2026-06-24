"""Test provider 注册表 + 按任务路由 (issue #45)。

验收 issue #45:
- register_provider / get_provider / list_providers 注册表基础
- 内置 mock / minimax 在包导入时自动注册
- 未知 provider 抛 ValueError
- configure_routing / get_provider_for_task 按任务类型路由
- 无路由配置时回退 default provider
- make_provider 行为向后兼容 (auto/mock/minimax)
"""
from __future__ import annotations

import pytest

from mortis.provider import (
    MinimaxProvider,
    MockProvider,
    configure_routing,
    get_provider,
    get_provider_for_task,
    list_providers,
    make_provider,
    register_provider,
)
from mortis.provider import registry as registry_mod
from mortis.provider import router as router_mod


# --------------------------------------------------------------------------- #
# 全局状态隔离 — 注册表与路由都是模块级全局, 每个测试前后快照/恢复
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _isolate_global_state():
    saved_registry = dict(registry_mod._registry)
    saved_routing = dict(router_mod._TASK_ROUTING)
    yield
    registry_mod._registry.clear()
    registry_mod._registry.update(saved_registry)
    router_mod._TASK_ROUTING.clear()
    router_mod._TASK_ROUTING.update(saved_routing)


# --------------------------------------------------------------------------- #
# 注册表基础
# --------------------------------------------------------------------------- #


class TestRegistryBasics:
    """register_provider / get_provider / list_providers。"""

    def test_list_providers_contains_builtin(self) -> None:
        """包导入后 mock / minimax 应已自动注册。"""
        names = list_providers()
        assert "mock" in names
        assert "minimax" in names

    def test_list_providers_is_sorted(self) -> None:
        """list_providers 返回字母序。"""
        names = list_providers()
        assert names == sorted(names)

    def test_get_provider_mock(self) -> None:
        p = get_provider("mock")
        assert isinstance(p, MockProvider)

    def test_get_provider_minimax(self) -> None:
        p = get_provider("minimax")
        assert isinstance(p, MinimaxProvider)

    def test_get_provider_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError) as exc:
            get_provider("bogus")
        assert "bogus" in str(exc.value)
        # 错误信息应列出可用 provider, 便于排查
        assert "available" in str(exc.value)

    def test_register_and_get_custom_provider(self) -> None:
        """注册一个自定义 provider 工厂, 再按名称取出。"""

        class FakeProvider:
            def generate_text(self, prompt, system="", **kw):
                return "fake"

            def generate(self, messages, **kw):
                from mortis.provider.base import Message

                return Message(role="assistant", content="fake")

        register_provider("fake", FakeProvider)
        assert "fake" in list_providers()
        p = get_provider("fake")
        assert isinstance(p, FakeProvider)

    def test_register_provider_overwrites(self) -> None:
        """重复注册同名 provider 覆盖旧工厂。"""
        register_provider("mock", MockProvider)  # 覆盖内置 mock
        p = get_provider("mock")
        assert isinstance(p, MockProvider)

    def test_get_provider_passes_kwargs_to_factory(self) -> None:
        """get_provider 的 **kwargs 透传给工厂。"""
        p = get_provider("mock", responses=["canned"])
        assert isinstance(p, MockProvider)
        assert p.generate_text("x") == "canned"


# --------------------------------------------------------------------------- #
# make_provider 向后兼容 (走注册表)
# --------------------------------------------------------------------------- #


class TestMakeProviderBackcompat:
    """make_provider 行为不变, 内部走注册表。"""

    def test_mock(self) -> None:
        assert isinstance(make_provider("mock"), MockProvider)

    def test_auto_falls_back_to_mock_without_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        assert isinstance(make_provider("auto"), MockProvider)

    def test_auto_uses_minimax_with_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        assert isinstance(make_provider("auto"), MinimaxProvider)

    def test_unknown_kind_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            make_provider("bogus")

    def test_make_provider_finds_registered_provider(self) -> None:
        """新注册的 provider 也能通过 make_provider 取到。"""

        class FakeProvider:
            def generate_text(self, prompt, system="", **kw):
                return "fake"

            def generate(self, messages, **kw):
                from mortis.provider.base import Message

                return Message(role="assistant", content="fake")

        register_provider("fake", FakeProvider)
        assert isinstance(make_provider("fake"), FakeProvider)


# --------------------------------------------------------------------------- #
# 按任务路由
# --------------------------------------------------------------------------- #


class TestTaskRouting:
    """configure_routing / get_provider_for_task。"""

    def test_no_routing_returns_default(self) -> None:
        """无路由配置时返回传入的 default provider。"""
        default = MockProvider()
        got = get_provider_for_task("reflect", default)
        assert got is default

    def test_no_routing_for_unconfigured_task(self) -> None:
        """配置了部分任务, 未配置的任务仍回退 default。"""
        default = MockProvider()
        configure_routing({"dream": "minimax"})
        # reflect 未配置 -> default
        assert get_provider_for_task("reflect", default) is default
        # dream 已配置 -> 非 default
        assert get_provider_for_task("dream", default) is not default

    def test_configure_routing_routes_to_named_provider(self) -> None:
        """reflect -> mock, dream -> minimax。"""
        default = MockProvider()
        configure_routing({"reflect": "mock", "dream": "minimax"})

        reflect_p = get_provider_for_task("reflect", default)
        assert isinstance(reflect_p, MockProvider)
        assert reflect_p is not default  # 路由产出新实例

        dream_p = get_provider_for_task("dream", default)
        assert isinstance(dream_p, MinimaxProvider)

    def test_configure_routing_overwrites(self) -> None:
        """重复配置同名任务覆盖旧值。"""
        default = MockProvider()
        configure_routing({"reflect": "mock"})
        configure_routing({"reflect": "minimax"})  # 覆盖
        got = get_provider_for_task("reflect", default)
        assert isinstance(got, MinimaxProvider)

    def test_configure_routing_empty_dict_keeps_existing(self) -> None:
        """空 dict 不影响现有配置。"""
        default = MockProvider()
        configure_routing({"reflect": "minimax"})
        configure_routing({})  # 不应清空
        got = get_provider_for_task("reflect", default)
        assert isinstance(got, MinimaxProvider)

    def test_routing_isolated_between_tests(self) -> None:
        """验证 autouse fixture 隔离: 默认无路由配置。"""
        default = MockProvider()
        assert get_provider_for_task("anything", default) is default
