"""BM25 关键词检索（技术方案 §6.6，RAG-RETR-02）。

倒排索引 + jieba 中文分词；无 jieba 时降级为二元组（bigram）。
技术内容大量是专有名词 / 函数名 / 报错信息，语义检索容易失准，BM25 一击命中。
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

try:
    import jieba

    _HAS_JIEBA = True
except ImportError:  # 极端环境无 jieba 时降级
    _HAS_JIEBA = False

_K1 = 1.5
_B = 0.75


def _is_word(t: str) -> bool:
    return any(c.isalnum() or "一" <= c <= "鿿" for c in t)


def tokenize(text: str) -> list[str]:
    if _HAS_JIEBA:
        return [t for t in jieba.cut(text) if t.strip() and _is_word(t)]
    # 降级：二元组
    text = re.sub(r"[^A-Za-z0-9一-鿿]+", "", text.lower())
    return [text[i : i + 2] for i in range(len(text) - 1)] if len(text) > 2 else [text]


class BM25:
    """BM25 打分器。构造时传入文档列表，search 返回 [(doc_idx, score)]。"""

    def __init__(self, docs: list[str]) -> None:
        self._docs = docs
        self._tokenized = [tokenize(d) for d in docs]
        self._doc_len = [len(t) for t in self._tokenized]
        self._avgdl = (sum(self._doc_len) / len(docs)) if docs else 0.0

        # 倒排索引：token -> {doc_idx: term_freq}
        self._postings: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for i, toks in enumerate(self._tokenized):
            for t in toks:
                self._postings[t][i] += 1

        self._n = len(docs)
        self._idf: dict[str, float] = {}
        for t, postings in self._postings.items():
            nt = len(postings)
            self._idf[t] = math.log((self._n - nt + 0.5) / (nt + 0.5) + 1)

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for t in tokenize(query):
            postings = self._postings.get(t)
            if not postings:
                continue
            idf = self._idf[t]
            for doc_idx, tf in postings.items():
                dl = self._doc_len[doc_idx]
                denom = tf + _K1 * (1 - _B + _B * dl / self._avgdl) if self._avgdl else 1.0
                scores[doc_idx] += idf * tf * (_K1 + 1) / denom
        return sorted(scores.items(), key=lambda x: -x[1])[:top_k]
