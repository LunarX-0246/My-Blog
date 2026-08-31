import { MarkdownAsync } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypePrettyCode from "rehype-pretty-code";

import { rehypeHeadingIds } from "@/lib/slug";
import CodeBlock from "./CodeBlock";

/**
 * Markdown 渲染（服务端，SSR 供搜索引擎抓取）。
 * - remark-gfm：表格 / 删除线 / 任务列表
 * - rehypeHeadingIds：自写插件给标题加 id，与后端锚点一致
 * - rehype-pretty-code：Shiki 服务端语法高亮（FR-VIEW-10）
 * - 代码块用 CodeBlock 包一层加复制按钮
 */
export function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <MarkdownAsync
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHeadingIds, [rehypePrettyCode, { theme: "github-dark" }]]}
        components={{ pre: CodeBlock }}
      >
        {content}
      </MarkdownAsync>
    </div>
  );
}
