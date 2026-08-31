"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function AdminIndex() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleLogout() {
    setLoading(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      setLoading(false);
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <main className="min-h-screen p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">管理后台</h1>
        <button
          onClick={handleLogout}
          disabled={loading}
          className="rounded-md border border-border px-3 py-1.5 text-sm text-muted hover:text-foreground disabled:opacity-50"
        >
          退出登录
        </button>
      </div>

      <nav className="mt-6 flex flex-col gap-2 text-sm">
        <Link href="/admin/posts" className="text-muted hover:text-foreground">
          文章管理 →
        </Link>
        <Link href="/admin/docs" className="text-muted hover:text-foreground">
          知识库管理 →
        </Link>
        <Link href="/admin/index" className="text-muted hover:text-foreground">
          索引管理 →
        </Link>
        <Link href="/admin/settings" className="text-muted hover:text-foreground">
          站点设置 →
        </Link>
      </nav>
    </main>
  );
}
