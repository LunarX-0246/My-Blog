import Link from "next/link";

import DirTree from "@/components/doc/DirTree";
import { serverFetch } from "@/lib/server-api";
import type { DocDirNode } from "@/lib/types";

/** 知识库页（FR-VIEW-15）：左侧目录树 + 右侧内容区。 */
export default async function DocsPage() {
  const tree = await serverFetch<DocDirNode>("/api/docs/tree");

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto flex max-w-5xl gap-8">
        <aside className="w-64 shrink-0">
          <h1 className="mb-4 text-lg font-semibold">知识库</h1>
          <DirTree node={tree} />
        </aside>
        <div className="min-w-0 flex-1 border-l border-border pl-8">
          <h2 className="mb-4 text-sm text-faint">根目录文档</h2>
          {tree.documents.length === 0 ? (
            <p className="text-sm text-muted">从左侧目录树选择文档查看。</p>
          ) : (
            <ul className="space-y-2">
              {tree.documents.map((d) => (
                <li key={d.id}>
                  <Link href={`/docs/${d.id}`} className="text-foreground hover:text-accent">
                    {d.title}
                  </Link>
                  <p className="text-xs text-faint">{d.description}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </main>
  );
}
