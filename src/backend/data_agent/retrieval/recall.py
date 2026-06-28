"""Schema 召回打分：
- BM25Recaller：无外部依赖，把表名/列名/注释当文档，问题当查询。
- EmbeddingRecaller：可选，需注入 EmbeddingProvider（fastembed / 自托管模型等）。

实际召回入口仍在 SchemaManager._recall()，本模块只负责打分。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Protocol

from ..connectors.base import TableInfo


# 简易中英文分词：按非字母数字切分，单字符不计
_TOKEN = re.compile(r"[A-Za-z0-9_]+|[一-龥]+")
# CamelCase 边界：lower→Upper 之间、Upper→UpperLower 之间（"XMLParser" → "XML_Parser"）
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _tokenize(text: str) -> list[str]:
    """统一切分到 token；中文按整段汉字保留（再拆 1-2gram），英文按下划线/驼峰拆。

    CamelCase 拆分必须在 lowercase 之前完成（否则边界已丢）。流程：
      原文 → re.findall 取 token → 每个英文 token 先 CamelCase 边界插下划线
           → lowercase → 按 `_` 切分 → 去重保留顺序
    """
    if not text:
        return []
    parts = _TOKEN.findall(text)
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        # 英文 / 数字 token：CamelCase + 下划线拆分
        if all("a" <= c.lower() <= "z" or "0" <= c <= "9" or c == "_" for c in p):
            # 先在 CamelCase 边界插下划线，再小写化、按 `_` 切
            expanded = _CAMEL_BOUNDARY.sub("_", p).lower()
            for sub in expanded.split("_"):
                if sub and sub not in out:
                    out.append(sub)
        else:
            # 中文：整体 + 2-gram，提升短语匹配
            p = p.lower()
            out.append(p)
            for i in range(len(p) - 1):
                out.append(p[i : i + 2])
    return out


@dataclass
class _Doc:
    """封装 _Doc 的数据结构或业务行为。"""
    table: str
    tokens: list[str]
    tf: dict[str, int] = field(default_factory=dict)


class BM25Recaller:
    """轻量 BM25。把每张表渲染成一个 doc（表名 + 列名 + 列注释 + 表注释）。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """初始化当前对象的依赖和内部状态。"""
        self.k1 = k1
        self.b = b
        self._docs: list[_Doc] = []
        self._df: dict[str, int] = {}
        self._avgdl = 0.0
        self._N = 0

    def fit(self, tables: dict[str, TableInfo], extra_text_per_table: dict[str, str] | None = None) -> None:
        """执行 fit 处理并返回结果。"""
        self._docs = []
        self._df = {}
        for name, info in tables.items():
            doc_text = self._render_table_doc(name, info, (extra_text_per_table or {}).get(name, ""))
            tokens = _tokenize(doc_text)
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            for t in tf:
                self._df[t] = self._df.get(t, 0) + 1
            self._docs.append(_Doc(table=name, tokens=tokens, tf=tf))

        self._N = len(self._docs)
        self._avgdl = (
            sum(len(d.tokens) for d in self._docs) / self._N if self._N else 0.0
        )

    def score(self, query: str) -> dict[str, float]:
        """执行 score 处理并返回结果。"""
        if not self._docs:
            return {}
        q_tokens = _tokenize(query)
        if not q_tokens:
            return {d.table: 0.0 for d in self._docs}
        out: dict[str, float] = {}
        for d in self._docs:
            s = 0.0
            dl = len(d.tokens) or 1
            for t in q_tokens:
                if t not in d.tf:
                    continue
                df = self._df.get(t, 0)
                if df == 0:
                    continue
                idf = math.log(1 + (self._N - df + 0.5) / (df + 0.5))
                tf = d.tf[t]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
                s += idf * (tf * (self.k1 + 1)) / (denom or 1)
            out[d.table] = s
        return out

    @staticmethod
    def _render_table_doc(name: str, info: TableInfo, extra: str) -> str:
        """渲染 render_table_doc 对应的数据片段。"""
        parts = [name, name.replace("_", " ")]
        for col in info.columns:
            parts.append(col.name)
            parts.append(col.name.replace("_", " "))
            if col.comment:
                parts.append(col.comment)
        if info.comment:
            parts.append(info.comment)
        if extra:
            parts.append(extra)
        return " ".join(parts)


class EmbeddingProvider(Protocol):
    """Embedding 后端接口：实现该协议即可接入嵌入向量召回。
    建议实现 fastembed / sentence-transformers / OpenAI embeddings 中任一。
    """

    def encode(self, texts: list[str]) -> list[list[float]]:
        """执行 encode 处理并返回结果。"""
        ...


class EmbeddingRecaller:
    """可选：基于 EmbeddingProvider 的 cosine 召回。

    SchemaManager 不强依赖此类；只有用户显式注入 provider 时才启用。
    """

    def __init__(self, provider: EmbeddingProvider):
        """初始化当前对象的依赖和内部状态。"""
        self.provider = provider
        self._tables: list[str] = []
        self._vectors: list[list[float]] = []

    def fit(self, tables: dict[str, TableInfo]) -> None:
        """执行 fit 处理并返回结果。"""
        docs = []
        names = []
        for name, info in tables.items():
            doc = name + " " + " ".join(c.name for c in info.columns)
            if info.comment:
                doc += " " + info.comment
            docs.append(doc)
            names.append(name)
        self._vectors = self.provider.encode(docs)
        self._tables = names

    def score(self, query: str) -> dict[str, float]:
        """执行 score 处理并返回结果。"""
        if not self._tables:
            return {}
        q_vec = self.provider.encode([query])[0]
        out: dict[str, float] = {}
        q_norm = math.sqrt(sum(x * x for x in q_vec)) or 1.0
        for name, vec in zip(self._tables, self._vectors):
            v_norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            dot = sum(a * b for a, b in zip(q_vec, vec))
            out[name] = dot / (q_norm * v_norm)
        return out
