import Link from "next/link";

import type { TagOut } from "@/lib/types";

export default function TagList({ tags }: { tags: TagOut[] }) {
  if (tags.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((t) => (
        <Link
          key={t.id}
          href={`/tags/${t.slug}`}
          className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted hover:text-foreground"
        >
          {t.name}
        </Link>
      ))}
    </div>
  );
}
