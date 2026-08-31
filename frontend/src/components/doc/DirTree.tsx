"use client";

import Link from "next/link";
import { useState } from "react";

import type { DocDirNode } from "@/lib/types";

/** 目录树（FR-DOC-10~12）：展开 / 折叠。展开状态存组件内（演示规模足够）。 */
export default function DirTree({
  node,
  depth = 0,
}: {
  node: DocDirNode;
  depth?: number;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div>
      {node.name && (
        <button
          onClick={() => setOpen(!open)}
          className="flex w-full items-center gap-1 py-1 text-left text-sm text-foreground hover:text-accent"
          style={{ paddingLeft: `${depth * 1}rem` }}
        >
          <span className="text-faint">{open ? "▾" : "▸"}</span>
          <span className="truncate">{node.name}</span>
        </button>
      )}
      <div className={open ? "" : "hidden"}>
        {node.dirs.map((d) => (
          <DirTree key={d.path} node={d} depth={depth + 1} />
        ))}
        {node.documents.map((doc) => (
          <Link
            key={doc.id}
            href={`/docs/${doc.id}`}
            className="block truncate py-1 text-sm text-muted hover:text-foreground"
            style={{ paddingLeft: `${(depth + 1) * 1}rem` }}
          >
            {doc.title}
          </Link>
        ))}
      </div>
    </div>
  );
}
