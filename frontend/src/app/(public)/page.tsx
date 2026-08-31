import Link from "next/link";

import { serverFetch } from "@/lib/server-api";
import type { PostListResponse, TagWithCount } from "@/lib/types";

/** 首页（FR-HOME-01~05）：主视觉 → 精选 → AI 问答 → 最新 → 热门标签 → 知识库入口。 */
export default async function HomePage() {
  const [featured, latest, hotTags] = await Promise.all([
    serverFetch<PostListResponse>("/api/posts?featured=true&page_size=3"),
    serverFetch<PostListResponse>("/api/posts?page_size=5"),
    serverFetch<TagWithCount[]>("/api/tags/hot?limit=10"),
  ]);

  return (
    <main className="min-h-screen">
      {/* 主视觉区 */}
      <section className="border-b border-border px-6 py-20 text-center">
        <h1 className="text-4xl font-bold">记录技术，也让知识可以被提问</h1>
        <p className="mx-auto mt-4 max-w-xl text-muted">
          一个个人技术博客。除了文章与资料，还能就站内内容提问——每个回答都带可验证的原文出处。
        </p>
      </section>

      {/* 精选文章 */}
      {featured.items.length > 0 && (
        <section className="border-b border-border px-6 py-12">
          <div className="mx-auto max-w-4xl">
            <h2 className="mb-6 text-lg font-semibold">精选文章</h2>
            <div className="grid gap-6 sm:grid-cols-3">
              {featured.items.map((p) => (
                <Link
                  key={p.id}
                  href={`/posts/${p.slug}`}
                  className="rounded-lg border border-border p-5 transition-colors hover:border-accent"
                >
                  <h3 className="font-medium">{p.title}</h3>
                  {p.summary && (
                    <p className="mt-2 line-clamp-3 text-sm text-muted">{p.summary}</p>
                  )}
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* AI 问答入口面板（占位，T3c 替换为完整交互组件） */}
      <section className="border-b border-border px-6 py-12">
        <div className="mx-auto max-w-4xl rounded-lg border border-border p-6">
          <h2 className="text-lg font-semibold">AI 问答</h2>
          <p className="mt-2 text-sm text-muted">
            就站内内容提问，回答带可验证出处。问答能力将在后续阶段上线。
          </p>
          <Link href="/ai" className="mt-4 inline-block text-sm text-accent">
            前往问答页 →
          </Link>
        </div>
      </section>

      {/* 最新文章 */}
      <section className="border-b border-border px-6 py-12">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-6 text-lg font-semibold">最新文章</h2>
          <ul className="space-y-4">
            {latest.items.map((p) => (
              <li key={p.id} className="flex items-baseline gap-3">
                <Link href={`/posts/${p.slug}`} className="font-medium hover:text-accent">
                  {p.title}
                </Link>
                {p.published_at && (
                  <span className="shrink-0 text-xs text-faint">
                    {new Date(p.published_at).toLocaleDateString("zh-CN")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 热门标签 */}
      {hotTags.length > 0 && (
        <section className="border-b border-border px-6 py-12">
          <div className="mx-auto max-w-4xl">
            <h2 className="mb-4 text-lg font-semibold">热门标签</h2>
            <div className="flex flex-wrap gap-2">
              {hotTags.map((t) => (
                <Link
                  key={t.id}
                  href={`/tags/${t.slug}`}
                  className="rounded-full border border-border px-3 py-1 text-sm text-muted hover:text-foreground"
                >
                  {t.name} <span className="text-faint">{t.count}</span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 知识库入口（占位，stage 2 补全） */}
      <section className="px-6 py-12">
        <div className="mx-auto max-w-4xl rounded-lg border border-border p-6">
          <h2 className="text-lg font-semibold">知识库</h2>
          <p className="mt-2 text-sm text-muted">
            站内收录的资料文档，支持原文 / 文本双视图。知识库将在后续阶段上线。
          </p>
        </div>
      </section>
    </main>
  );
}
