import DualView from "@/components/doc/DualView";
import PdfViewer from "@/components/doc/PdfViewer";
import { Markdown } from "@/components/post/Markdown";
import { stripLeadingTitle } from "@/lib/heading";
import TagList from "@/components/post/TagList";
import { serverFetch, serverFetchOr404 } from "@/lib/server-api";
import type { DocumentDetail } from "@/lib/types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 文档详情页（FR-VIEW-16~19）：元信息 + 双视图。支持 ?page=N（PDF）与 #chunk-N（文本视图）。 */
export default async function DocDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { id } = await params;
  const { page } = await searchParams;
  const initialPage = page ? Number(page) : undefined;
  const doc = await serverFetchOr404<DocumentDetail>(`/api/docs/${id}`);

  const original =
    doc.file_format === "pdf" ? (
      <PdfViewer url={`/api/docs/${doc.id}/raw`} initialPage={initialPage} />
    ) : doc.file_format === "markdown" ? (
      <Markdown content={stripLeadingTitle(doc.parsed_text, doc.title)} />
    ) : (
      <pre className="whitespace-pre-wrap text-sm text-foreground">{doc.parsed_text}</pre>
    );

  // 文本视图按块渲染，每块带 id="chunk-N" 锚点（FR-VIEW-19，H4）
  const textView =
    doc.chunks.length > 0 ? (
      <div className="space-y-6">
        {doc.chunks.map((c) => (
          <div
            key={c.seq}
            id={`chunk-${c.seq}`}
            className="scroll-mt-24 whitespace-pre-wrap text-sm leading-relaxed text-foreground"
          >
            {c.content}
          </div>
        ))}
      </div>
    ) : (
      <pre className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
        {doc.parsed_text}
      </pre>
    );

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6 space-y-3 border-b border-border pb-6">
          <h1 className="text-2xl font-semibold">{doc.title}</h1>
          {doc.description && <p className="text-muted">{doc.description}</p>}
          <div className="flex flex-wrap items-center gap-x-3 text-xs text-faint">
            <span>目录：{doc.dir_path || "根目录"}</span>
            <span>格式：{doc.file_format}</span>
            <span>大小：{formatSize(doc.file_size)}</span>
            {doc.page_count != null && <span>页数：{doc.page_count}</span>}
            <span>上传于 {new Date(doc.uploaded_at).toLocaleDateString("zh-CN")}</span>
          </div>
          <TagList tags={doc.tags} />
          {/* ?download=1 让后端带上 Content-Disposition: attachment 与原始文件名。
              不加的话 PDF 会被浏览器内联打开而不是下载（FR-VIEW-23）。 */}
          <a
            href={`/api/docs/${doc.id}/raw?download=1`}
            className="inline-block text-sm text-accent hover:opacity-80"
          >
            下载原文件
          </a>
        </header>

        <DualView original={original} text={textView} />
      </div>
    </main>
  );
}
