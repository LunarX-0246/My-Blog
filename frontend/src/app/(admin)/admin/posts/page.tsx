"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { clientFetch } from "@/lib/api";
import type { PostListItem } from "@/lib/types";

const statusText: Record<string, string> = { draft: "草稿", published: "已发布" };

export default function AdminPostsPage() {
  const [posts, setPosts] = useState<PostListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    clientFetch<PostListItem[]>("/api/admin/posts")
      .then(setPosts)
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"));
  }, []);

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">文章管理</h1>
          <Link
            href="/admin/posts/new"
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90"
          >
            新建文章
          </Link>
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
                    <Link href={`/admin/posts/${p.id}/edit`} className="truncate font-medium hover:text-accent">
                      {p.title || "（无标题）"}
                    </Link>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${
                        p.status === "published" ? "bg-accent/20 text-accent" : "bg-surface-hover text-muted"
                      }`}
                    >
                      {statusText[p.status] ?? p.status}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-faint">
                    {p.category?.name ?? "未分类"}
                    {p.tags.length > 0 && ` · ${p.tags.map((t) => t.name).join(" / ")}`}
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs text-faint">
                  {p.updated_at ? new Date(p.updated_at).toLocaleDateString("zh-CN") : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
