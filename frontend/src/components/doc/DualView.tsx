"use client";

import { useState } from "react";

/** 文档双视图切换（FR-VIEW-17~19）：原文视图（默认）/ 文本视图。 */
export default function DualView({
  original,
  text,
}: {
  original: React.ReactNode;
  text: React.ReactNode;
}) {
  const [view, setView] = useState<"original" | "text">("original");

  const tabCls = (active: boolean) =>
    `border-b-2 px-3 py-2 text-sm ${
      active ? "border-accent text-foreground" : "border-transparent text-muted hover:text-foreground"
    }`;

  return (
    <div>
      <div className="mb-4 flex gap-4 border-b border-border">
        <button className={tabCls(view === "original")} onClick={() => setView("original")}>
          原文视图
        </button>
        <button className={tabCls(view === "text")} onClick={() => setView("text")}>
          文本视图
        </button>
      </div>
      {view === "original" ? original : text}
    </div>
  );
}
