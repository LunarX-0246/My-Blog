# 前端镜像（Next.js 15，多阶段构建）
#
# ★ 为什么必须多阶段：
#   构建（next build）内存峰值超过 1.5 GB，目标服务器只有 2 GiB —— 在服务器上构建会
#   直接拖死系统（红线 E5）。多阶段让「构建」和「运行」分开：镜像在开发机上构建完成，
#   服务器只负责运行已经构建好的产物，不需要 Node 工具链、不需要 devDependencies。
#
# ★ 依赖 next.config.ts 的 output: "standalone"：
#   Next 会把运行所需的最小依赖集输出到 .next/standalone，运行阶段无需 node_modules。

# ── 阶段 1：装依赖 ────────────────────────────────────────────────
FROM node:22-alpine AS deps
WORKDIR /app
# 用 npm ci 而非 npm install：严格按 lock 文件安装，保证可复现
COPY package.json package-lock.json ./
RUN npm ci

# ── 阶段 2：构建 ─────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── 阶段 3：运行 ─────────────────────────────────────────────────
# 只带构建产物，不含 Node 工具链与 devDependencies
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# public 里有 pdf.worker.min.js（PDF 阅读器要用），不能漏
COPY --from=builder /app/public ./public
# standalone 产物自带精简后的 node_modules 与 server.js
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
# 静态资源不在 standalone 里，要单独拷
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

# standalone 模式的入口是 server.js，不是 next start
CMD ["node", "server.js"]
