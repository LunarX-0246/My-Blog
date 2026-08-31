"use client";

import { useCallback } from "react";
import MDEditor from "@uiw/react-md-editor";
import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";

import { ApiErrorShape } from "@/lib/api";

/**
 * Markdown 编辑器（FR-POST-01~05）。
 * - 工具栏 + 分屏实时预览 + 代码块高亮（内部 rehype-prism-plus，Prism.js）
 * - 图片粘贴 / 拖拽上传：拦截 paste/drop，上传到 /api/images，在光标处插入 `![](url)`
 */
export default function MarkdownEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  async function uploadImage(file: File): Promise<string> {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/images", { method: "POST", body: fd });
    const body = (await res.json()) as { url?: string } & ApiErrorShape;
    if (!res.ok) {
      throw new Error(body?.error?.message ?? "图片上传失败");
    }
    return body.url as string;
  }

  // 上传一组图片，并在光标处插入 Markdown 图片语法（FR-POST-05）。
  // 光标位置取自 textarea 的 selectionStart；CodeMirror 会同步该值。
  async function insertImages(textarea: HTMLTextAreaElement, files: File[]) {
    const pos = textarea.selectionStart ?? value.length;
    const marks: string[] = [];
    for (const f of files) {
      const url = await uploadImage(f);
      marks.push(`![${f.name.replace(/[[\]()]/g, "")}](${url})`);
    }
    const snippet = marks.join("\n") + "\n";
    onChange(value.slice(0, pos) + snippet + value.slice(pos));
  }

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const files: File[] = [];
      for (const item of Array.from(e.clipboardData?.items ?? [])) {
        if (item.kind === "file" && item.type.startsWith("image/")) {
          const f = item.getAsFile();
          if (f) files.push(f);
        }
      }
      if (files.length === 0) return; // 普通文本粘贴，交给默认行为
      e.preventDefault();
      void insertImages(e.currentTarget, files);
    },
    [value],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLTextAreaElement>) => {
      const files = Array.from(e.dataTransfer?.files ?? []).filter((f) =>
        f.type.startsWith("image/"),
      );
      if (files.length === 0) return;
      e.preventDefault();
      void insertImages(e.currentTarget, files);
    },
    [value],
  );

  return (
    <div data-color-mode="dark">
      <MDEditor
        value={value}
        onChange={(v) => onChange(v ?? "")}
        height={480}
        preview="live"
        textareaProps={{
          onPaste: handlePaste,
          onDrop: handleDrop,
          placeholder: "用 Markdown 撰写正文，支持粘贴 / 拖拽图片…",
        }}
      />
    </div>
  );
}
