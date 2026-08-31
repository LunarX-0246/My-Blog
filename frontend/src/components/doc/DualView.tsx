"use client";

import { useEffect, useState } from "react";

/** 文档双视图切换（FR-VIEW-17~19）。带 #chunk-N 进入时自动切到文本视图并滚动定位。 */
export default function DualView({
  original,
  text,
  initialView = "original",
}: {
  original: React.ReactNode;
  text: React.ReactNode;
  initialView?: "original" | "text";
}) {
  const [view, setView] = useState<"original" | "text">(initialView);

  // 带 #chunk-N 进入时切到文本视图（该块只在文本视图有锚点落点，H4）
  useEffect(() => {
    if (window.location.hash.startsWith("#chunk-")) {
      setView("text");
    }
  }, []);

  // 切到文本视图后滚动到对应块
  useEffect(() => {
    if (view === "text") {
      const hash = window.location.hash;
      if (hash.startsWith("#chunk-")) {
        const id = hash.slice(1);
        setTimeout(() => {
          document.getElementById(id)?.scrollIntoView({ block: "start" });
        }, 80);
      }
    }
  }, [view]);

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
