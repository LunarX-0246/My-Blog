"use client";

import MDEditor from "@uiw/react-md-editor";
import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";

/**
 * Markdown 编辑器（FR-POST-01~04）。
 * @uiw/react-md-editor 自带格式工具栏 + 分屏实时预览 + 代码块高亮
 * （内部用 rehype-prism-plus，Prism.js）。暗色通过 data-color-mode="dark" 启用。
 */
export default function MarkdownEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div data-color-mode="dark">
      <MDEditor
        value={value}
        onChange={(v) => onChange(v ?? "")}
        height={480}
        preview="live"
        textareaProps={{ placeholder: "用 Markdown 撰写正文…" }}
      />
    </div>
  );
}
