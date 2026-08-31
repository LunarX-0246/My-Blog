"use client";

import { useRef, useState } from "react";

/** 代码块：包裹 <pre>，加「一键复制」按钮（FR-VIEW-10）。 */
export default function CodeBlock({
  node: _node,
  children,
  ...rest
}: React.ComponentPropsWithoutRef<"pre"> & { node?: unknown }) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  async function copy() {
    const text = preRef.current?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 剪贴板不可用时静默失败
    }
  }

  return (
    <div className="group relative">
      <button
        onClick={copy}
        className="absolute right-2 top-2 z-10 rounded-md border border-border bg-surface px-2 py-1 text-xs text-muted opacity-0 transition-opacity group-hover:opacity-100"
      >
        {copied ? "已复制" : "复制"}
      </button>
      <pre ref={preRef} {...rest}>
        {children}
      </pre>
    </div>
  );
}
