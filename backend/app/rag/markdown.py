"""Markdown 工具：标题锚点 slug 与 TOC 提取（文章 / 文档共用，chunker 复用 slug）。

锚点必须与前端 ``lib/slug.ts`` 的 ``slugifyHeading`` 逐字一致，否则引用跳转会错位
（FR-VIEW-11 / RAG-CHUNK-07 的引用落点）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark")


@dataclass
class Heading:
    level: int
    text: str
    anchor: str


def slugify_heading(text: str) -> str:
    """标题锚点 slug。规则：小写 → 去反引号 → 非 [a-z0-9 中文 扩展A] 连续字符换 '-' → 去首尾 '-'。"""
    s = text.lower().replace("`", "")
    s = re.sub(r"[^a-z0-9一-鿿㐀-䶿]+", "-", s)
    return s.strip("-") or "section"


def _inline_text(inline) -> str:
    """从 markdown-it 的 inline token 提取纯文本（去掉加粗/斜体/链接等标记）。"""
    parts: list[str] = []
    for child in inline.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif child.type == "image":
            parts.append(child.content or "")
    return "".join(parts)


def build_toc(content_md: str) -> list[Heading]:
    """提取标题层级生成 TOC，锚点带去重（重复标题加 -1、-2）。"""
    tokens = _md.parse(content_md)
    headings: list[Heading] = []
    seen: dict[str, int] = {}
    for i, tok in enumerate(tokens):
        if tok.type != "heading_open":
            continue
        level = int(tok.tag[1])  # h1 -> 1, h2 -> 2
        text = _inline_text(tokens[i + 1])
        anchor = slugify_heading(text)
        if anchor in seen:
            seen[anchor] += 1
            anchor = f"{anchor}-{seen[anchor]}"
        else:
            seen[anchor] = 0
        headings.append(Heading(level=level, text=text, anchor=anchor))
    return headings
