"""反馈样例 BM25 召回。"""
from __future__ import annotations

import math
import re
import sqlite3

from .feedback_models import FeedbackEntry, row_to_entry

TOKEN = re.compile(r"[A-Za-z0-9_]+|[一-龥]+")


def tokenize(text: str) -> list[str]:
    """把中英文问题切成 BM25 token。"""
    if not text:
        return []
    parts = TOKEN.findall(text.lower())
    out: list[str] = []
    for part in parts:
        if all("a" <= c <= "z" or "0" <= c <= "9" or c == "_" for c in part):
            out.extend([sub for sub in part.split("_") if sub])
        else:
            out.append(part)
            out.extend(part[i: i + 2] for i in range(len(part) - 1))
    return out


def bm25_recall(rows: list[sqlite3.Row], question: str, top_k: int) -> list[FeedbackEntry]:
    """对 approved 反馈做 BM25-only 召回。"""
    if not rows:
        return []
    docs = [tokenize(row["question"]) for row in rows]
    avgdl = sum(len(doc) for doc in docs) / len(docs)
    df: dict[str, int] = {}
    for doc in docs:
        for token in set(doc):
            df[token] = df.get(token, 0) + 1
    scores: list[tuple[float, sqlite3.Row]] = []
    for row, doc in zip(rows, docs, strict=True):
        score = bm25_score(tokenize(question), doc, df, len(docs), avgdl)
        if score > 0:
            scores.append((score, row))
    scores.sort(key=lambda item: item[0], reverse=True)
    return [row_to_entry(row) for _, row in scores[:top_k]]


def bm25_score(query_tokens: list[str], doc: list[str], df: dict[str, int], doc_count: int, avgdl: float) -> float:
    """计算一篇文档的 BM25 分数。"""
    tf: dict[str, int] = {}
    for token in doc:
        tf[token] = tf.get(token, 0) + 1
    score = 0.0
    k1, b = 1.5, 0.75
    dl = len(doc) or 1
    for token in query_tokens:
        freq = tf.get(token, 0)
        if not freq:
            continue
        idf = math.log(1 + (doc_count - df[token] + 0.5) / (df[token] + 0.5))
        denom = freq + k1 * (1 - b + b * dl / (avgdl or 1))
        score += idf * (freq * (k1 + 1)) / (denom or 1)
    return score
