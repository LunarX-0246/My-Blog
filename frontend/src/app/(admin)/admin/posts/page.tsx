"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { clientFetch } from "@/lib/api";
import type { PostListItem } from "@/lib/types";

const statusText: Record<string, string> = { draft: "草稿", published: "已发布" };

export default function AdminPostsPage() {
  const [posts, setPosts] = useState<PostListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  // 排序：updated=按更新时间（默认），views=按浏览次数（FR-STAT-02）
  const [sort, setSort] = useState<"updated" | "views">("updated");

  const load = useCallback(() => {
    clientFetch<PostListItem[]>(`/api/admin/posts?sort=${sort}`)
      .then(setPosts)
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"));
  }, [sort]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(id: number, fn: () => Promise<unknown>) {
    setBusyId(id);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusyId(null);
    }
  }

  function handleDelete(p: PostListItem) {
    // 硬删除二次确认，提示中包含标题（FR-POST-15）
    if (!window.confirm(`确定删除文章「${p.title}」吗？此操作不可恢复。`)) return;
    void run(p.id, () => clientFetch(`/api/posts/${p.id}`, { method: "DELETE" }));
  }

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">文章管理</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSort((s) => (s === "updated" ? "views" : "updated"))}
              className="rounded-md border border-border px-3 py-2 text-sm text-muted hover:text-foreground"
            >
              {sort === "updated" ? "按浏览次数排序" : "按更新时间排序"}
            </button>
            <Link
              href="/admin/posts/new"
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90"
            >
              新建文章
            </Link>
          </div>
        </header>

        {error && <p className="text-sm text-red-400">{error}</p>}
        {posts === null && !error && <p className="text-muted">加载中…</p>}
        {posts && posts.length === 0 && <p className="text-muted">还没有文章。</p>}

        {posts && posts.length > 0 && (
          <ul className="divide-y divide-border rounded-md border border-border">
            {posts.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/admin/posts/${p.id}/edit`}
                      className="truncate font-medium hover:text-accent"
                    >
                      {p.title || "（无标题）"}
                    </Link>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${
                        p.status === "published"
                          ? "bg-accent/20 text-accent"
                          : "bg-surface-hover text-muted"
                      }`}
                    >
                      {statusText[p.status] ?? p.status}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-faint">
                    {p.category?.name ?? "未分类"}
                    {p.tags.length > 0 && ` · ${p.tags.map((t) => t.name).join(" / ")}`}
                    <span className="ml-2 text-muted">浏览 {p.view_count}</span>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2 text-sm">
                  <span className="mr-2 hidden text-xs text-faint sm:inline">
                    {p.updated_at ? new Date(p.updated_at).toLocaleDateString("zh-CN") : ""}
                  </span>
                  {p.status === "draft" ? (
                    <button
                      onClick={() =>
                        void run(p.id, () =>
                          clientFetch(`/api/posts/${p.id}/publish`, { method: "POST" }),
                        )
                      }
                      disabled={busyId === p.id}
                      className="rounded-md border border-accent px-2.5 py-1 text-xs text-accent hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
                    >
                      发布
                    </button>
                  ) : (
                    <button
                      onClick={() =>
                        void run(p.id, () =>
                          clientFetch(`/api/posts/${p.id}/unpublish`, { method: "POST" }),
                        )
                      }
                      disabled={busyId === p.id}
                      className="rounded-md border border-border px-2.5 py-1 text-xs text-muted hover:text-foreground disabled:opacity-50"
                    >
                      撤回
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(p)}
                    disabled={busyId === p.id}
                    className="rounded-md border border-border px-2.5 py-1 text-xs text-red-400 hover:bg-red-400/10 disabled:opacity-50"
                  >
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
