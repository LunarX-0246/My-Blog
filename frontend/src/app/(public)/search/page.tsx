import Link from "next/link";

import { serverFetch } from "@/lib/server-api";
import type { SearchResult } from "@/lib/types";

/** 把含 <mark> 的片段渲染成高亮文本（不用 dangerouslySetInnerHTML，避免注入）。 */
function renderExcerpt(excerpt: string) {
  const parts = excerpt.split(/(<mark>|<\/mark>)/g);
  let inMark = false;
  return parts.map((part, i) => {
    if (part === "<mark>") {
      inMark = true;
      return null;
    }
    if (part === "</mark>") {
      inMark = false;
      return null;
    }
    return inMark ? (
      <mark key={i} className="rounded bg-accent/30 px-0.5 text-foreground">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    );
  });
}

/** 全站搜索（FR-SEARCH-01~05）。 */
export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; type?: string; tag?: string }>;
}) {
  const { q, type, tag } = await searchParams;
  const results = q
    ? await serverFetch<SearchResult[]>(
        `/api/search?q=${encodeURIComponent(q)}${type ? `&type=${type}` : ""}${tag ? `&tag=${tag}` : ""}`,
      )
    : [];

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <form action="/search" className="flex gap-2">
          <input
            name="q"
            type="search"
            defaultValue={q ?? ""}
            placeholder="搜索文章与知识库文档"
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint focus:border-accent focus:outline-none"
          />
          <button className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90">
            搜索
          </button>
        </form>

        {q && (
          <div className="flex flex-wrap gap-2 text-sm">
            <Link href={`/search?q=${encodeURIComponent(q)}`} className={!type ? "text-accent" : "text-muted hover:text-foreground"}>
              全部
            </Link>
            <Link href={`/search?q=${encodeURIComponent(q)}&type=post`} className={type === "post" ? "text-accent" : "text-muted hover:text-foreground"}>
              文章
            </Link>
            <Link href={`/search?q=${encodeURIComponent(q)}&type=document`} className={type === "document" ? "text-accent" : "text-muted hover:text-foreground"}>
              文档
            </Link>
          </div>
        )}

        {q && results.length === 0 && (
          <div className="rounded-lg border border-border p-6 text-sm text-muted">
            没有找到与「{q}」相关的内容。
            <p className="mt-2">
              试试 <Link href={`/ai`} className="text-accent hover:underline">AI 问答</Link>
              ，就站内内容提问。
            </p>
          </div>
        )}

        {results.length > 0 && (
          <ul className="space-y-4">
            {results.map((r, i) => (
              <li key={i} className="space-y-1">
                <Link href={r.url} className="text-base font-medium hover:text-accent">
                  {r.title}
                </Link>
                <span className="ml-2 text-xs text-faint">{r.type === "post" ? "文章" : "文档"}</span>
                <p className="text-sm text-muted">{renderExcerpt(r.excerpt)}</p>
                {r.date && <p className="text-xs text-faint">{new Date(r.date).toLocaleDateString("zh-CN")}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
