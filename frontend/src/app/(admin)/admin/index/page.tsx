"use client";

import { useCallback, useEffect, useState } from "react";

import { clientFetch } from "@/lib/api";

interface IndexItem {
  id: number;
  title: string;
  idx_status: string;
  idx_error: string | null;
}

interface IndexStatus {
  posts: IndexItem[];
  documents: IndexItem[];
  total_chunks: number;
  /** 源内容已删除但残留在索引里的块。正常为 0；不为 0 时检索会命中已不存在的内容 */
  orphan_chunks: number;
  model: string;
  dim: number;
  embedding_tokens: number;
  last_indexed_at: string | null;
}

const statusText: Record<string, string> = {
  pending: "待索引",
  queued: "排队中",
  running: "索引中",
  indexed: "已索引",
  failed: "失败",
};

const statusColor: Record<string, string> = {
  pending: "bg-surface-hover text-muted",
  queued: "bg-surface-hover text-muted",
  running: "bg-accent/20 text-accent",
  indexed: "bg-accent/20 text-accent",
  failed: "bg-red-400/20 text-red-400",
};

/** 索引管理（FR-IDX-04~09）：状态、重试、全量重建、统计。 */
export default function AdminIndexPage() {
  const [data, setData] = useState<IndexStatus | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    clientFetch<IndexStatus>("/api/admin/index/status")
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function retry(srcType: "post" | "document", id: number) {
    setBusy(true);
    try {
      await clientFetch(`/api/admin/index/retry/${srcType}/${id}`, { method: "POST" });
      setTimeout(load, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "重试失败");
    } finally {
      setBusy(false);
    }
  }

  async function rebuild() {
    if (!window.confirm("确定全量重建索引吗？将重新计算全部块的向量，可能消耗较多 API 调用。")) return;
    setBusy(true);
    try {
      await clientFetch("/api/admin/index/rebuild", { method: "POST" });
      setTimeout(load, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "重建失败");
    } finally {
      setBusy(false);
    }
  }

  async function purgeOrphans() {
    setBusy(true);
    try {
      const r = await clientFetch<{ purged: number }>("/api/admin/index/purge-orphans", {
        method: "POST",
      });
      setError(r.purged > 0 ? `已清除 ${r.purged} 个孤儿块` : null);
      setTimeout(load, 800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "清理失败");
    } finally {
      setBusy(false);
    }
  }

  function renderItem(item: IndexItem, srcType: "post" | "document") {
    if (filter !== "all" && item.idx_status !== filter) return null;
    return (
      <li key={`${srcType}-${item.id}`} className="flex items-center justify-between gap-4 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-xs text-faint">{srcType === "post" ? "文章" : "文档"}</span>
            <span className="truncate font-medium">{item.title}</span>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${statusColor[item.idx_status] ?? "bg-surface-hover text-muted"}`}>
              {statusText[item.idx_status] ?? item.idx_status}
            </span>
          </div>
          {item.idx_error && <div className="mt-1 truncate text-xs text-red-400">{item.idx_error}</div>}
        </div>
        {item.idx_status === "failed" && (
          <button
            onClick={() => retry(srcType, item.id)}
            disabled={busy}
            className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs text-muted hover:text-foreground disabled:opacity-50"
          >
            重试
          </button>
        )}
      </li>
    );
  }

  const filters = ["all", "pending", "queued", "running", "indexed", "failed"];

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">索引管理</h1>
          <button
            onClick={rebuild}
            disabled={busy}
            className="rounded-md border border-accent px-3 py-1.5 text-sm text-accent hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
          >
            全量重建
          </button>
        </header>

        {data && (
          <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-lg border border-border p-4 text-sm text-muted">
            <span>块总数：<b className="text-foreground">{data.total_chunks}</b></span>
            {data.orphan_chunks > 0 && (
              <span className="text-red-400">
                孤儿块：<b>{data.orphan_chunks}</b>
                <button
                  onClick={purgeOrphans}
                  disabled={busy}
                  className="ml-2 rounded border border-red-400/40 px-2 py-0.5 text-xs hover:bg-red-400/10 disabled:opacity-50"
                >
                  清理
                </button>
              </span>
            )}
            <span>向量模型：<b className="text-foreground">{data.model}</b>（{data.dim} 维）</span>
            <span>累计 embedding token：<b className="text-foreground">{data.embedding_tokens}</b></span>
            {data.last_indexed_at && (
              <span>最近索引：<b className="text-foreground">{new Date(data.last_indexed_at).toLocaleString("zh-CN")}</b></span>
            )}
          </div>
        )}

        {error && <p className="text-sm text-red-400">{error}</p>}

        <div className="flex flex-wrap gap-2 text-xs">
          {filters.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full border px-3 py-1 ${
                filter === f ? "border-accent text-accent" : "border-border text-muted hover:text-foreground"
              }`}
            >
              {f === "all" ? "全部" : (statusText[f] ?? f)}
            </button>
          ))}
        </div>

        {data === null ? (
          <p className="text-muted">加载中…</p>
        ) : (
          <div className="rounded-md border border-border">
            <ul className="divide-y divide-border">
              {data.posts.map((p) => renderItem(p, "post"))}
              {data.documents.map((d) => renderItem(d, "document"))}
            </ul>
            {data.posts.length + data.documents.length === 0 && (
              <p className="p-4 text-sm text-muted">暂无内容。</p>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
