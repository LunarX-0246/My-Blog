// FastAPI 调用封装（服务端 / SSR 侧）。
//
// 与 lib/api.ts 分开的原因：这里用到了 next/headers 的 cookies()，
// 它是 Server Component 专有 API，若和客户端代码混在同一文件，
// 客户端组件 import 时会导致构建报错。故拆成两个文件。
//
// 只在 Server Component / layout 里 import 本文件。

import { cookies } from "next/headers";

import { parseResponse } from "./api";

// 本机开发默认指向本机后端；生产由 docker-compose 注入容器内网地址 http://api:8000。
const INTERNAL_API_BASE =
  process.env.INTERNAL_API_BASE ?? "http://127.0.0.1:8000";

/**
 * SSR 取数：手动转发浏览器 Cookie 给后端（红线 A5）。
 *
 * Next.js 在服务端渲染时是 Node 进程去调 FastAPI，浏览器 Cookie 不会自动带上，
 * 必须手动读取并放到请求头里。漏掉这一步的典型症状：站内跳转进管理页一切正常，
 * 一刷新页面就跳登录页（那次 SSR 请求没有身份）。
 *
 * 注意：path 必须带 `/api` 前缀（如 `/api/auth/me`），因为这里是直连 FastAPI，
 * 而后端所有路由都挂在 `/api` 下；客户端则靠 rewrite 转发，两者路径保持一致。
 */
export async function serverFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieHeader = (await cookies()).toString();
  const res = await fetch(`${INTERNAL_API_BASE}${path}`, {
    ...init,
    headers: { ...(init?.headers ?? {}), cookie: cookieHeader },
    cache: "no-store",
  });
  return parseResponse<T>(res);
}
