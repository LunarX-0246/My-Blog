// (admin) 路由组的统一鉴权（红线 A6）。
//
// 所有管理页共用这一层做服务端鉴权，避免逐页漏写（漏写一个即是越权漏洞，NFR-SEC-05）。
// 服务端鉴权是必须的：仅靠前端隐藏入口等于没有鉴权。

import { redirect } from "next/navigation";

import { serverFetch } from "@/lib/server-api";
import type { MeResponse } from "@/lib/types";

export default async function AdminLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  let me: MeResponse | null = null;
  try {
    me = await serverFetch<MeResponse>("/api/auth/me");
  } catch {
    // 后端不可达时也回到登录页，避免在管理区抛 500
    redirect("/login");
  }
  if (!me?.authenticated) {
    redirect("/login");
  }
  return <>{children}</>;
}
