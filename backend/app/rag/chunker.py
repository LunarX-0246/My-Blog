"""切块器（技术方案 §6.3，红线 R3）。

- 文章 / Markdown 文档：按标题层级（h2/h3）切分，拼接上下文前缀
- PDF：按页切分，页码记录到块
- txt：按段落切分
- 每个块：content / context_prefix / embed_text / fingerprint / page_no / anchor

禁止用固定长度滑动窗口切块：会把代码块与表格从中间切碎，且丢失标题路径。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from markdown_it import MarkdownIt

from app.config import settings
from app.rag.markdown import _inline_text, slugify_heading

_md = MarkdownIt("commonmark")


@dataclass
class ChunkData:
    """切块结果（尚未向量化）。"""

    seq: int
    content: str
    context_prefix: str
    embed_text: str
    fingerprint: str
    page_no: int | None = None
    anchor: str | None = None


def _fingerprint(context_prefix: str, content: str) -> str:
    """内容指纹 = sha256(context_prefix + content)，增量索引比对依据（RAG-INC-01）。"""
    return hashlib.sha256((context_prefix + "\n" + content).encode("utf-8")).hexdigest()


def _make_chunk(seq: int, context_prefix: str, content: str, *, page_no=None, anchor=None) -> ChunkData:
    content = content.strip()
    return ChunkData(
        seq=seq,
        content=content,
        context_prefix=context_prefix,
        embed_text=f"{context_prefix}\n{content}",  # 实际送去向量化的文本
        fingerprint=_fingerprint(context_prefix, content),
        page_no=page_no,
        anchor=anchor,
    )


def _split_paragraphs_keep_fences(text: str) -> list[str]:
    """按空行切段落，但代码围栏（```）内部不切（RAG-CHUNK-03）。"""
    lines = text.split("\n")
    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                current.append(line)
                paragraphs.append("\n".join(current))
                current = []
                in_fence = False
            else:
                if current:
                    paragraphs.append("\n".join(current))
                    current = []
                current.append(line)
                in_fence = True
        else:
            current.append(line)
            if not in_fence and stripped == "":
                paragraphs.append("\n".join(current))
                current = []
    if current:
        paragraphs.append("\n".join(current))
    return [p for p in paragraphs if p.strip()]


def _split_long(content: str) -> list[str]:
    """超长块按段落二次切分（RAG-CHUNK-02），代码块/表格整块保留。返回文本块列表。"""
    if len(content) <= settings.chunk_max_chars:
        return [content]

    blocks: list[str] = []
    current = ""
    for para in _split_paragraphs_keep_fences(content):
        # 单段本身超长（如超大代码块）则整段保留，避免从中间切开
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= settings.chunk_max_chars:
            current = f"{current}\n\n{para}"
        else:
            blocks.append(current)
            current = para
    if current:
        blocks.append(current)
    return blocks


def _heading_sections(md_text: str) -> list[tuple[list[tuple[int, str]], int, str]]:
    """返回 [(标题链 [(level, text)], 起始行, 标题文本)]，按出现顺序。

    只在 h2/h3 处作为切分边界（RAG-CHUNK-01「以二级、三级标题为界」）；
    h1 与 h4+ 仍计入标题链（供上下文前缀），但不切分。
    """
    tokens = _md.parse(md_text)
    result: list[tuple[list[tuple[int, str]], int, str]] = []
    chain: list[tuple[int, str]] = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            text = _inline_text(tokens[i + 1]).strip()
            if not text:
                continue
            start = tok.map[0] if tok.map else 0
            # 维护标题链：弹出 >= 当前层级的旧标题
            while chain and chain[-1][0] >= level:
                chain.pop()
            chain.append((level, text))
            if level in (2, 3):
                result.append((list(chain), start, text))
    return result


def chunk_markdown(md_text: str, *, root_ctx: str, description: str = "") -> list[ChunkData]:
    """按标题层级切分 Markdown（文章与 Markdown 文档共用）。"""
    lines = md_text.split("\n")
    sections = _heading_sections(md_text)

    prefix_root = root_ctx
    if description:
        prefix_root = f"{root_ctx}（{description}）"

    chunks: list[ChunkData] = []
    seq = 0

    def emit(prefix: str, content: str, *, anchor=None, page_no=None):
        nonlocal seq
        for block in _split_long(content):
            chunks.append(_make_chunk(seq, prefix, block, anchor=anchor, page_no=page_no))
            seq += 1

    if not sections:
        # 无标题：整篇作为一个块
        emit(prefix_root, md_text)
        return chunks

    # 首标题之前的引导内容
    first_start = sections[0][1]
    lead = "\n".join(lines[:first_start]).strip()
    if lead:
        emit(prefix_root, lead)

    # 逐段切分：每段从标题行到下一个标题（或结尾）
    seen_anchors: dict[str, int] = {}
    for idx, (chain, start, text) in enumerate(sections):
        end = sections[idx + 1][1] if idx + 1 < len(sections) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        prefix = prefix_root
        for _lvl, htext in chain:
            # 文章的 h1 通常就是文章标题本身（导入脚本正是从 h1 取标题的），
            # 直接拼会得到「标题 > 标题 > 小节」这种重复前缀 ——
            # 既稀释 embedding 的语义，也白白多占 token。与根上下文同名则跳过。
            if htext == root_ctx:
                continue
            prefix = f"{prefix} > {htext}"
        # 锚点用当前标题的 slug（供引用跳转，RAG-CHUNK-07）；同名标题去重（L1，与前端一致）
        anchor = slugify_heading(text)
        if anchor in seen_anchors:
            seen_anchors[anchor] += 1
            anchor = f"{anchor}-{seen_anchors[anchor]}"
        else:
            seen_anchors[anchor] = 0
        emit(prefix, content, anchor=anchor)

    return chunks


def chunk_plain_text(text: str, *, root_ctx: str, description: str = "") -> list[ChunkData]:
    """txt 按段落切分（FR-DOC / RAG-CHUNK）。"""
    prefix_root = root_ctx
    if description:
        prefix_root = f"{root_ctx}（{description}）"
    chunks: list[ChunkData] = []
    seq = 0
    current = ""
    for para in _split_paragraphs_keep_fences(text):
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= settings.chunk_max_chars:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(_make_chunk(seq, prefix_root, current, anchor=f"chunk-{seq}"))
            seq += 1
            current = para
    if current.strip():
        chunks.append(_make_chunk(seq, prefix_root, current, anchor=f"chunk-{seq}"))
    return chunks


def chunk_pdf(pages: list[tuple[int, str]], *, root_ctx: str, description: str = "") -> list[ChunkData]:
    """PDF 按页切分，每页内部再按段落合并；页码记录到块（RAG-CHUNK-07）。"""
    prefix_root = root_ctx
    if description:
        prefix_root = f"{root_ctx}（{description}）"
    chunks: list[ChunkData] = []
    seq = 0
    for page_no, page_text in pages:
        text = page_text.strip()
        if not text:
            continue
        if len(text) <= settings.chunk_max_chars:
            chunks.append(
                _make_chunk(seq, prefix_root, text, page_no=page_no, anchor=f"chunk-{seq}")
            )
            seq += 1
        else:
            current = ""
            for para in _split_paragraphs_keep_fences(text):
                if not current:
                    current = para
                elif len(current) + len(para) + 2 <= settings.chunk_max_chars:
                    current = f"{current}\n\n{para}"
                else:
                    chunks.append(_make_chunk(seq, prefix_root, current, page_no=page_no, anchor=f"chunk-{seq}"))
                    seq += 1
                    current = para
            if current.strip():
                chunks.append(_make_chunk(seq, prefix_root, current, page_no=page_no, anchor=f"chunk-{seq}"))
                seq += 1
    return chunks
