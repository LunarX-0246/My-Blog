import Link from "next/link";

import type { PostNeighbor } from "@/lib/types";

/** 上一篇 / 下一篇导航（FR-VIEW-12）。 */
export default function PrevNext({
  prev,
  next,
}: {
  prev: PostNeighbor | null;
  next: PostNeighbor | null;
}) {
  return (
    <nav className="mt-10 grid grid-cols-1 gap-3 border-t border-border pt-6 sm:grid-cols-2">
      {prev ? (
        <Link href={`/posts/${prev.slug}`} className="group">
          <p className="text-xs text-faint">上一篇</p>
          <p className="mt-1 text-sm text-muted group-hover:text-accent">{prev.title}</p>
        </Link>
      ) : (
        <span />
      )}
      {next ? (
        <Link href={`/posts/${next.slug}`} className="group text-right">
          <p className="text-xs text-faint">下一篇</p>
          <p className="mt-1 text-sm text-muted group-hover:text-accent">{next.title}</p>
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}
