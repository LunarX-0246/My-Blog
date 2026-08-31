"use client";

import { useEffect, useState } from "react";

import type { TocItem } from "@/lib/types";

/** 文章目录（FR-VIEW-09）：标注当前阅读位置，点击跳转。 */
export default function Toc({ items }: { items: TocItem[] }) {
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const headings = items
      .map((i) => document.getElementById(i.anchor))
      .filter((el): el is HTMLElement => el != null);
    if (headings.length === 0) return;

    const onScroll = () => {
      let current = headings[0]?.id ?? null;
      for (const el of headings) {
        if (el.getBoundingClientRect().top <= 120) current = el.id;
      }
      setActive(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [items]);

  if (items.length === 0) return null;

  return (
    <nav className="text-sm">
      <p className="mb-2 text-xs text-faint">目录</p>
      <ul className="space-y-0.5">
        {items.map((i) => (
          <li key={`${i.anchor}-${i.level}-${i.text}`}>
            <a
              href={`#${i.anchor}`}
              style={{ paddingLeft: `${(i.level - 1) * 0.75}rem` }}
              className={`block border-l-2 py-0.5 pl-2 transition-colors ${
                active === i.anchor
                  ? "border-accent text-foreground"
                  : "border-transparent text-muted hover:text-foreground"
              }`}
            >
              {i.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
