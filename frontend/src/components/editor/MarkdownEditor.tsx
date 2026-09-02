"use client";

import { useCallback, useEffect, useRef } from "react";
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

  // ★ 正文的最新值。图片上传是异步的，插入结果必须基于**上传完成那一刻**的正文，
  //   不能用发起粘贴时闭包里捕获的那份快照 —— 上传一张图要几百毫秒到几秒，
  //   这期间用户还在打字，拿旧快照去拼接会把这段新输入整段覆盖掉，
  //   表现为「插入图片后，刚才敲的字凭空消失」，而且不报任何错。
  const valueRef = useRef(value);
  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  // 上传一组图片，并在光标处插入 Markdown 图片语法（FR-POST-05）。
  // 光标位置取自 textarea 的 selectionStart；CodeMirror 会同步该值。
  const insertImages = useCallback(
    async (textarea: HTMLTextAreaElement, files: File[]) => {
      const pos = textarea.selectionStart ?? valueRef.current.length;
      const marks: string[] = [];
      for (const f of files) {
        const url = await uploadImage(f);
        marks.push(`![${f.name.replace(/[[\]()]/g, "")}](${url})`);
      }
      const snippet = marks.join("\n") + "\n";
      // 用最新正文重新拼接；光标位置也夹到新长度内 ——
      // 用户在上传期间删过字的话，pos 会越界
      const latest = valueRef.current;
      const at = Math.min(pos, latest.length);
      onChange(latest.slice(0, at) + snippet + latest.slice(at));
    },
    [onChange],
  );

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
    [insertImages],
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
    [insertImages],
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
