"""语义层：将业务术语映射到数据库表和列。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json


@dataclass
class TermMapping:
    """封装 TermMapping 的数据结构或业务行为。"""
    term: str
    table_name: str
    column_name: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class SemanticLayer:
    """封装 SemanticLayer 的数据结构或业务行为。"""
    mappings: list[TermMapping] = field(default_factory=list)
    table_descriptions: dict[str, str] = field(default_factory=dict)
    join_hints: dict[str, str] = field(default_factory=dict)
    # 敏感列：{"users.phone": "phone", "*.email": "email"} 等。
    # 类型见 safety.masking.supported_mask_types()
    sensitive_columns: dict[str, str] = field(default_factory=dict)

    def find_matches(self, question: str) -> list[TermMapping]:
        """执行 find_matches 逻辑。"""
        matched: list[TermMapping] = []
        question_lower = question.lower()
        for m in self.mappings:
            terms = [m.term] + m.aliases
            if any(t.lower() in question_lower for t in terms):
                matched.append(m)
        return matched

    def find_ambiguities(self, question: str) -> dict[str, list[TermMapping]]:
        """检测一个 term/alias 触发多个不同 (table, column) 候选的场景。

        返回 {匹配到的关键词: [候选 mapping...]}，至少 2 个候选才算歧义。
        """
        question_lower = question.lower()
        # 按触发关键词聚合候选
        hits: dict[str, list[TermMapping]] = {}
        for m in self.mappings:
            for trigger in [m.term] + m.aliases:
                t_lower = trigger.lower()
                if t_lower in question_lower:
                    hits.setdefault(t_lower, []).append(m)
                    break  # 同一 mapping 同一问题只贡献一次
        # 只保留有 ≥ 2 个不同 (table, column) 候选的关键词
        ambiguous = {
            kw: cands for kw, cands in hits.items()
            if len({(c.table_name, c.column_name) for c in cands}) >= 2
        }
        return ambiguous

    def to_schema_context(self) -> str:
        """执行 to_schema_context 逻辑。"""
        lines: list[str] = []
        if self.table_descriptions:
            lines.append("-- 业务术语 -> 表/列映射:")
            for m in self.mappings:
                lines.append(f"--   {m.term} -> {m.table_name}.{m.column_name}  ({m.description})")
        if self.join_hints:
            lines.append("-- 表关联提示:")
            for (t1, t2), hint in self.join_hints.items():
                lines.append(f"--   {t1} <-> {t2}: {hint}")
        return "\n".join(lines)

    @classmethod
    def from_json(cls, path: str | Path) -> "SemanticLayer":
        """执行 from_json 逻辑。"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        mappings = [TermMapping(**m) for m in data.get("mappings", [])]
        return cls(
            mappings=mappings,
            table_descriptions=data.get("table_descriptions", {}),
            join_hints={tuple(k.split(",")): v for k, v in data.get("join_hints", {}).items()},
            sensitive_columns=data.get("sensitive_columns", {}),
        )
