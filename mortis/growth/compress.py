"""Growth 维度压缩 — 合并同维度低 confidence growth。

issue #47: 随着 dream 周期积累，同一维度可能产生大量相似 growth 条目。
定期合并同维度低 confidence growth，减少冗余。

策略:
1. 按维度分组
2. 每个维度内: confidence < 0.3 的 growth 作为合并候选
3. 用 LLM 合并候选的 body 为一条摘要（无 provider 时 fallback 拼接前 3 条）
4. 合并后的 confidence = max(候选) + 0.1 (不超过 0.5)
5. 合并后的 source_sessions = union(候选)
6. 合并后的 tags = union(候选)
7. 删除被合并的候选, 写入合并后的新 growth

幂等性: 合并后该维度只剩 1 条低 confidence growth（或 0 条，若合并后
confidence >= 阈值）。MIN_CANDIDATES=2 保证再次调用不会重复压缩。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.provider.base import LLMProviderProtocol
from mortis.vault import Vault

_logger = logging.getLogger(__name__)

COMPRESSION_THRESHOLD = 0.3  # confidence < 此值的 growth 才参与合并
MIN_CANDIDATES = 2  # 同维度至少 N 个候选才触发合并
MAX_COMPRESSED_CONFIDENCE = 0.5


def compress_growths(
    vault: Vault,
    provider: LLMProviderProtocol | None = None,
    dimension: Dimension | None = None,
) -> dict:
    """压缩同维度低 confidence growth。

    Args:
        vault: Vault 实例
        provider: LLM provider（可选，用于 body 合并）
        dimension: 只压缩指定维度（None = 全部维度）

    Returns:
        dict: {"compressed": int, "merged": int}
            - compressed: 被合并删除的 growth 总数
            - merged: 写入的合并后新 growth 条数
    """
    dims = [dimension] if dimension else list(Dimension)
    total_compressed = 0
    total_merged = 0

    for dim in dims:
        rels = vault.list_growths(dim)
        candidates: list[tuple[str, Growth]] = []
        keep: list[Growth] = []

        for rel in rels:
            g = vault.read_growth(rel)
            if g.confidence < COMPRESSION_THRESHOLD:
                candidates.append((rel, g))
            else:
                keep.append(g)

        if len(candidates) < MIN_CANDIDATES:
            continue

        # 合并候选
        merged = _merge_candidates(candidates, provider)
        if merged:
            # 删除旧候选
            for rel, _ in candidates:
                vault.delete_growth(rel)
            # 写入合并后的
            vault.write_growth(merged)
            total_compressed += len(candidates)
            total_merged += 1
            _logger.info("compressed %d growths in %s -> 1", len(candidates), dim.value)

    return {
        "compressed": total_compressed,
        "merged": total_merged,
    }


def _merge_candidates(
    candidates: list[tuple[str, Growth]],
    provider: LLMProviderProtocol | None,
) -> Growth | None:
    """合并多个候选 growth 为一条。"""
    if not candidates:
        return None

    # 取第一条作为基础
    first = candidates[0][1]
    all_bodies = [g.body for _, g in candidates]

    # 如果有 provider, 用 LLM 合并 body
    if provider:
        try:
            merged_body = _llm_merge_bodies(provider, all_bodies)
        except Exception:
            merged_body = " | ".join(all_bodies[:3])  # fallback: 取前3条拼接
    else:
        merged_body = " | ".join(all_bodies[:3])

    # 合并 source_sessions
    all_sessions: set[str] = set()
    for _, g in candidates:
        all_sessions.update(g.source_sessions)

    # 合并 tags
    all_tags: set[str] = set()
    for _, g in candidates:
        all_tags.update(g.tags)

    # 合并 confidence
    max_conf = max(g.confidence for _, g in candidates)
    merged_conf = min(max_conf + 0.1, MAX_COMPRESSED_CONFIDENCE)

    now = datetime.now(tz=timezone.utc).isoformat()

    return Growth(
        id=f"compressed-{now[:10]}-{first.dimension.value}",
        dimension=first.dimension,
        confidence=merged_conf,
        created_at=now,
        last_validated=now,
        source_sessions=tuple(sorted(all_sessions)),
        dream_level=DreamLevel.MEDIUM,  # 合并的视为 medium
        emotional_valence=0.0,
        emotional_arousal=0.0,
        tags=tuple(sorted(all_tags)),
        body=merged_body,
    )


def _llm_merge_bodies(provider: LLMProviderProtocol, bodies: list[str]) -> str:
    """用 LLM 合并多条 growth body 为一条摘要。"""
    prompt = f"""请将以下 {len(bodies)} 条记忆合并为一条简洁的摘要，保留关键信息：

""" + "\n".join(f"- {b}" for b in bodies) + """

合并后的摘要:"""

    system = "你是一个记忆整合助手。请将多条相似记忆合并为一条。"
    result = provider.generate_text(prompt, system=system)
    return result[:200] if result else " | ".join(bodies[:3])
