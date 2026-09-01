import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 部署用：只输出运行所需的最小依赖集到 .next/standalone，
  // 运行镜像不必带整个 node_modules。目标服务器只有 2 GiB / 40 GiB，
  // 这能把前端镜像从几百 MB 压到百 MB 量级，上传与启动都快得多。
  // 对 npm run dev / npm run start 无影响。
  output: "standalone",

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
  // pdfjs-dist 的 Node 构建里 require("canvas")（原生模块），浏览器端用不到，
  // 但 webpack 打包时会去解析。fallback 成空模块即可（标准解法）。
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, canvas: false };
    return config;
  },
};

export default nextConfig;
