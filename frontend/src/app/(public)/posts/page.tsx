import Link from "next/link";

import { serverFetch } from "@/lib/server-api";
import type { CategoryOut, PostListResponse, TagOut } from "@/lib/types";

/** 文章归档页（FR-VIEW-06/07）：全部已发布文章，支持分类 / 标签筛选。 */
export default async function PostsPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; tag?: string }>;
}) {
  const { category, tag } = await searchParams;
  const qs = new URLSearchParams();
  if (category) qs.set("category", category);
  if (tag) qs.set("tag", tag);

  const [data, categories, tags] = await Promise.all([
    serverFetch<PostListResponse>(`/api/posts${qs.size ? `?${qs}` : ""}`),
    serverFetch<CategoryOut[]>("/api/categories"),
    serverFetch<TagOut[]>("/api/tags"),
  ]);

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="space-y-4">
          <h1 className="text-2xl font-semibold">文章归档</h1>
          <div className="flex flex-wrap gap-2 text-sm">
            <Link
              href="/posts"
              className={`rounded-full border px-3 py-1 ${
                !category && !tag ? "border-accent text-accent" : "border-border text-muted hover:text-foreground"
              }`}
            >
              全部
            </Link>
            {categories.map((c) => (
              <Link
                key={c.id}
                href={`/posts?category=${c.slug}`}
                className={`rounded-full border px-3 py-1 ${
                  category === c.slug ? "border-accent text-accent" : "border-border text-muted hover:text-foreground"
                }`}
              >
                {c.name}
              </Link>
            ))}
          </div>
          {tags.length > 0 && (
            <div className="flex flex-wrap gap-2 text-xs">
              {tags.map((t) => (
                <Link
                  key={t.id}
                  href={`/posts?tag=${t.slug}`}
                  className={`rounded-full px-2.5 py-0.5 ${
                    tag === t.slug ? "bg-accent text-accent-foreground" : "bg-surface text-muted hover:text-foreground"
                  }`}
                >
                  {t.name}
                </Link>
              ))}
            </div>
          )}
        </header>

        {data.items.length === 0 ? (
          <p className="text-muted">暂无文章。</p>
        ) : (
          <ul className="space-y-6">
            {data.items.map((p) => (
              <li key={p.id} className="space-y-1.5">
                <Link href={`/posts/${p.slug}`} className="text-lg font-medium hover:text-accent">
                  {p.title}
                </Link>
                {p.summary && <p className="text-sm text-muted">{p.summary}</p>}
                <div className="flex flex-wrap items-center gap-x-3 text-xs text-faint">
                  {p.category && <span>{p.category.name}</span>}
                  {p.published_at && (
                    <span>{new Date(p.published_at).toLocaleDateString("zh-CN")}</span>
                  )}
                  <span>阅读约 {p.read_minutes} 分钟</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
