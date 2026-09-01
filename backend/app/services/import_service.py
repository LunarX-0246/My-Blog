"""Markdown 批量导入脚本（T8-1，技术方案 §12 对比实验的前置）。

读取指定目录下的 Markdown 文件，逐个导入为「已发布」文章并同步走索引管线：

- 标题：取首个 h1；没有则用文件名（去扩展名）
- slug：中文转拼音（复用 services.slug.slugify），冲突自动去重
- 导入：post_service.create_published（直接以 published 状态落库）
- 索引：index_service.index_source_sync（chunker → embedder → store，不得绕过）

用法：
    python -m app.services.import_service --dir <目录>
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.db import SessionLocal
from app.rag.markdown import build_toc
from app.services import index_service, post_service
from app.services.slug import slugify

_MD_SUFFIXES = {".md", ".markdown"}


def extract_title(content_md: str, filename: str) -> str:
    """取首个非空 h1 作标题，没有则用文件名（去扩展名）。"""
    for h in build_toc(content_md):
        if h.level == 1 and h.text.strip():
            return h.text.strip()
    return Path(filename).stem.strip()


def discover_files(dir_path: str) -> list[Path]:
    """列出目录下（仅一级、不递归）的 Markdown 文件，按文件名排序保证顺序稳定。"""
    root = Path(dir_path)
    if not root.is_dir():
        raise SystemExit(f"目录不存在：{dir_path}")
    files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in _MD_SUFFIXES]
    return sorted(files, key=lambda p: p.name)


def import_directory(dir_path: str) -> None:
    files = discover_files(dir_path)
    if not files:
        print("目录下没有 Markdown 文件。")
        return

    print(f"导入 {len(files)} 个 Markdown 文件：")
    for f in files:
        content = f.read_text(encoding="utf-8")
        title = extract_title(content, f.name)

        with SessionLocal() as db:
            post = post_service.create_published(db, title=title, content_md=content)
        try:
            chunk_total, chunk_new = index_service.index_source_sync("post", post.id)
        except Exception as e:  # noqa: BLE001 —— 单篇索引失败不中断其余导入
            print(f"  ✗ #{post.id}「{post.title}」索引失败：{e}")
            continue
        print(
            f"  ✓ #{post.id}「{post.title}」slug={post.slug} "
            f"块={chunk_total}（新增 {chunk_new}）"
        )


def _main() -> None:
    parser = argparse.ArgumentParser(description="批量导入 Markdown 为已发布文章并触发索引")
    parser.add_argument("--dir", required=True, help="Markdown 文件所在目录")
    args = parser.parse_args()
    import_directory(args.dir)


if __name__ == "__main__":
    _main()
