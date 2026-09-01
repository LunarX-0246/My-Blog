"""索引任务队列（技术方案 §7，FR-IDX-01~03、RAG-INC-01~03）。

- 状态持久化在 index_tasks 表，进程重启后恢复
- 进程内 asyncio 队列 + 单 worker 串行消费（向量化是外部 API，并发只会更快限流）
- 增量索引：按内容指纹比对，只对新增/变化的块调用向量化（R6）
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.config import settings
from app.db import SessionLocal
from app.models import Chunk, Document, IndexStatus, IndexTask, Post, Setting, SourceType
from app.rag import chunker, embedder, parser
from app.rag.retriever import invalidate_bm25
from app.rag.store.base import ChunkVec, get_store
from app.services import ask_cache, search_service

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[tuple[int, str, int, bool]] = asyncio.Queue()
_loop: asyncio.AbstractEventLoop | None = None


def _to_enum(src_type: str) -> SourceType:
    return SourceType.post if src_type == "post" else SourceType.document


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_worker() -> None:
    """启动后台 worker（main.py 的 lifespan 调用）。"""
    global _loop
    _loop = asyncio.get_event_loop()
    asyncio.create_task(_worker_loop())
    _recover_pending()


def enqueue(src_type: str, src_id: int, *, force: bool = False) -> None:
    """创建索引任务并入队（供 API 层调用）。force=True 表示全量重建，忽略指纹。"""
    # 内容变更 → 清空问答缓存（N7，决策 A：全清）与搜索缓存（B5，同步失效，避免搜索滞后于发布/编辑）
    ask_cache.clear()
    search_service.invalidate()
    with SessionLocal() as db:
        task = IndexTask(
            src_type=_to_enum(src_type), src_id=src_id, status=IndexStatus.queued,
            force=force,
        )
        db.add(task)
        db.commit()
        task_id = task.id
        # 源内容置为排队中
        _set_source_idx_status(db, src_type, src_id, IndexStatus.queued, None)
    if _loop is not None:
        _loop.call_soon_threadsafe(_queue.put_nowait, (task_id, src_type, src_id, force))


def _accumulate_embedding_tokens(db, total_tokens: int) -> None:
    """累计索引环节的 embedding token 消耗到 settings（M3，成本可见）。不 commit，随主流程提交。"""
    if total_tokens <= 0:
        return
    row = db.get(Setting, "embedding_tokens")
    if row is None:
        db.add(Setting(key="embedding_tokens", value={"total": total_tokens}))
    else:
        row.value = {"total": int(row.value.get("total", 0)) + total_tokens}


def _set_source_idx_status(db, src_type: str, src_id: int, status: IndexStatus, error: str | None) -> None:
    if src_type == "post":
        post = db.get(Post, src_id)
        if post:
            post.idx_status = status
            post.idx_error = error
    else:
        doc = db.get(Document, src_id)
        if doc:
            doc.idx_status = status
            doc.idx_error = error
    db.commit()


def _recover_pending() -> None:
    """启动时扫描 queued/running 的任务重新入队（崩溃恢复）。"""
    with SessionLocal() as db:
        rows = db.scalars(
            select(IndexTask).where(IndexTask.status.in_([IndexStatus.queued, IndexStatus.running]))
        ).all()
        for t in rows:
            src_type = t.src_type.value
            _queue.put_nowait((t.id, src_type, t.src_id, t.force))
    logger.info("index worker recovered %d pending tasks", len(rows))


async def _worker_loop() -> None:
    while True:
        task_id, src_type, src_id, force = await _queue.get()
        try:
            await asyncio.to_thread(_process_task, task_id, src_type, src_id, force)
        except Exception as e:  # noqa: BLE001 —— 单任务异常不应中断 worker
            logger.exception("index task %d failed", task_id)
        finally:
            _queue.task_done()


def _process_task(task_id: int, src_type: str, src_id: int, force: bool = False) -> None:
    with SessionLocal() as db:
        task = db.get(IndexTask, task_id)
        if not task:
            return
        task.status = IndexStatus.running
        task.started_at = _now()
        db.commit()
        try:
            chunk_total, chunk_new = _index_source(db, src_type, src_id, force=force)
            task.status = IndexStatus.indexed
            task.chunk_total = chunk_total
            task.chunk_new = chunk_new
            task.finished_at = _now()
            db.commit()
            _set_source_idx_status(db, src_type, src_id, IndexStatus.indexed, None)
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:500] or "索引失败"
            task.status = IndexStatus.failed
            task.error = msg
            task.finished_at = _now()
            db.commit()
            _set_source_idx_status(db, src_type, src_id, IndexStatus.failed, msg)
            logger.exception("index source %s:%s failed", src_type, src_id)
    # 索引内容已变化（无论成功与否），失效块级 BM25 缓存（M1）。
    # 搜索缓存已由 enqueue 同步失效（B5），此处不再重复失效。
    invalidate_bm25()


def _chunk_source(db, src_type: str, src_id: int) -> list[chunker.ChunkData]:
    if src_type == "post":
        post = db.get(Post, src_id)
        if not post:
            raise ValueError("文章不存在")
        return chunker.chunk_markdown(post.content_md, root_ctx=post.title)
    doc = db.get(Document, src_id)
    if not doc:
        raise ValueError("文档不存在")
    root_ctx = f"{doc.dir_path} > {doc.title}" if doc.dir_path else doc.title
    if doc.file_format == "pdf":
        data = (settings.uploads_dir / doc.stored_name).read_bytes()
        pages = parser.parse_pdf(data)
        return chunker.chunk_pdf(pages, root_ctx=root_ctx, description=doc.description)
    if doc.file_format == "markdown":
        return chunker.chunk_markdown(doc.parsed_text, root_ctx=root_ctx, description=doc.description)
    return chunker.chunk_plain_text(doc.parsed_text, root_ctx=root_ctx, description=doc.description)


def _index_source(db, src_type: str, src_id: int, *, force: bool = False) -> tuple[int, int]:
    """增量索引：指纹比对，仅向量化新增/变化的块（R6）。force=True 时忽略指纹全量重算。"""
    new_chunks = _chunk_source(db, src_type, src_id)

    if force:
        # 全量重建：先清空该源旧块，再全部重新向量化（RAG-INC-03 / FR-IDX-06）
        db.execute(
            delete(Chunk).where(Chunk.src_type == _to_enum(src_type), Chunk.src_id == src_id)
        )
        db.commit()
        existing: dict[str, object] = {}
    else:
        # 现有块的 指纹 -> embedding
        existing = {
            c.fingerprint: c.embedding
            for c in db.scalars(
                select(Chunk).where(Chunk.src_type == _to_enum(src_type), Chunk.src_id == src_id)
            ).all()
        }

    # 需要向量化的块（force 时全部；增量时仅新增或指纹变化）
    to_embed = new_chunks if force else [c for c in new_chunks if c.fingerprint not in existing]
    embeddings: dict[str, list[float]] = {}
    if to_embed:
        usage: list[int] = []
        vecs = embedder.embed_batch([c.embed_text for c in to_embed], usage_out=usage)
        for c, v in zip(to_embed, vecs):
            embeddings[c.fingerprint] = v
        _accumulate_embedding_tokens(db, sum(usage))

    chunk_vecs: list[ChunkVec] = []
    for c in new_chunks:
        emb = embeddings.get(c.fingerprint) or existing.get(c.fingerprint)
        if emb is None:  # 理论上不会发生（都该有值），兜底跳过
            continue
        chunk_vecs.append(
            ChunkVec(
                src_type=src_type,
                src_id=src_id,
                seq=c.seq,
                content=c.content,
                context_prefix=c.context_prefix,
                embed_text=c.embed_text,
                fingerprint=c.fingerprint,
                page_no=c.page_no,
                anchor=c.anchor,
                embedding=emb,
            )
        )

    get_store().upsert(db, chunk_vecs)

    # 删除已移除的块（RAG-INC-02）
    new_fps = {c.fingerprint for c in new_chunks}
    for fp in existing:
        if fp not in new_fps:
            db.execute(
                delete(Chunk).where(
                    Chunk.src_type == _to_enum(src_type),
                    Chunk.src_id == src_id,
                    Chunk.fingerprint == fp,
                )
            )
    db.commit()
    return len(new_chunks), len(to_embed)


def rebuild_all() -> int:
    """全量重建索引（FR-IDX-06、RAG-INC-03）：忽略指纹，重算全部块。"""
    with SessionLocal() as db:
        posts = db.scalars(select(Post).where(Post.status == "published")).all()
        docs = db.scalars(select(Document)).all()
        sources = [("post", p.id) for p in posts] + [("document", d.id) for d in docs]
    for src_type, src_id in sources:
        enqueue(src_type, src_id, force=True)
    return len(sources)


def _rebuild_sync() -> int:
    """同步全量重建（CLI 用，绕过队列与启动自检）。

    换 embedding 模型后，启动自检会因「模型不一致」拒绝启动，无法走管理页重建。
    此时用 `python -m app.services.index_service --rebuild` 直接同步重建，
    并刷新 settings 里的模型记录，使随后启动自检通过。
    """
    with SessionLocal() as db:
        posts = db.scalars(select(Post).where(Post.status == "published")).all()
        docs = db.scalars(select(Document)).all()
        sources = [("post", p.id) for p in posts] + [("document", d.id) for d in docs]
        for src_type, src_id in sources:
            _index_source(db, src_type, src_id, force=True)
            _set_source_idx_status(db, src_type, src_id, IndexStatus.indexed, None)
        current = {"model": settings.embedding_model, "dim": settings.embedding_dim}
        row = db.get(Setting, "embedding_model")
        if row:
            row.value = current
        else:
            db.add(Setting(key="embedding_model", value=current))
        db.commit()
    return len(sources)


def index_source_sync(src_type: str, src_id: int) -> tuple[int, int]:
    """同步索引单个内容（批量导入脚本用，T8-1）。

    复用与 worker 完全相同的 ``_index_source``（chunker → embedder → store），
    只是绕过队列与线程，让 CLI 脚本能立即拿到块数与索引状态。不写 index_tasks 表
    （导入脚本直接驱动，无需崩溃恢复语义）。失败时把源内容标记为 failed 并抛出，
    由调用方决定继续导入下一份还是中止。
    """
    try:
        with SessionLocal() as db:
            chunk_total, chunk_new = _index_source(db, src_type, src_id)
            _set_source_idx_status(db, src_type, src_id, IndexStatus.indexed, None)
        return chunk_total, chunk_new
    except Exception as e:  # noqa: BLE001 —— 单篇失败不应中断批量导入，交给调用方处理
        msg = str(e)[:500] or "索引失败"
        with SessionLocal() as db:
            _set_source_idx_status(db, src_type, src_id, IndexStatus.failed, msg)
        raise
    finally:
        # 块集合已变化，失效 BM25 缓存（与 worker 的 _process_task 一致）
        invalidate_bm25()
        search_service.invalidate()


if __name__ == "__main__":
    import sys

    if "--rebuild" in sys.argv:
        print(f"全量重建完成，共 {_rebuild_sync()} 个内容")
