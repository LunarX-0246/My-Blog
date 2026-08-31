"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
      <p className="mt-3 text-muted">
        阶段 0 骨架：鉴权已生效。文章管理等将在阶段 1 加入。
      </p>
    </main>
  );
}
