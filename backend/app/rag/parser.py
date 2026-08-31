"""文档解析（技术方案 §6.2）。

PDF 按页返回 ``[(page_no, text)]``，页码一路保留到切块阶段（红线 R2）。
若拼成单一 raw_text，页码在拼接那一刻永久丢失，FR-VIEW-22 的 PDF 引用跳页码就无法实现。
"""
from __future__ import annotations

import pymupdf  # PyMuPDF（1.28 起推荐 import pymupdf，fitz 别名已弃用）


def parse_pdf(data: bytes) -> list[tuple[int, str]]:
    """按页解析 PDF，返回 [(page_no, text)]。page_no 从 1 开始。"""
    pages: list[tuple[int, str]] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc, start=1):
            pages.append((i, page.get_text()))
    return pages


def parse_markdown(data: bytes) -> str:
    """Markdown 原样读取，交给 chunker 按标题切（技术方案 §6.2）。"""
    return data.decode("utf-8", errors="replace")


def parse_txt(data: bytes) -> str:
    """txt 读取为纯文本；切块时按空行分段（chunker 处理）。"""
    return data.decode("utf-8", errors="replace")
