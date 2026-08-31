import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 本机开发：把 /api 代理到后端，保持同源，避免 CORS（技术方案 §10）。
  // 生产环境由 Nginx 直接把 /api/* 路由到 FastAPI，此 rewrite 不再参与。
  async rewrites() {
    const base = process.env.INTERNAL_API_BASE ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${base}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
