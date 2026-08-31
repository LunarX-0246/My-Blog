"use client";

import { useCallback, useEffect, useState } from "react";

import { clientFetch } from "@/lib/api";
import type { QaLogListResponse, QaLogOut, QaLogStats } from "@/lib/types";

/** 问答日志（FR-LOG-01~05）：时间倒序、可展开、筛选、汇总统计。 */
export default function AdminLogsPage() {
  const [data, setData] = useState<QaLogListResponse | null>(null);
  const [stats, setStats] = useState<QaLogStats | null>(null);
  const [usedRetrieval, setUsedRetrieval] = useState<string>("");
  const [hasError, setHasError] = useState<string>("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (usedRetrieval !== "") params.set("used_retrieval", usedRetrieval);
    if (hasError !== "") params.set("has_error", hasError);
    const qs = params.toString();
    clientFetch<QaLogListResponse>(`/api/admin/qa-logs${qs ? `?${qs}` : ""}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"));
    clientFetch<QaLogStats>("/api/admin/qa-logs/stats").then(setStats).catch(() => {});
  }, [usedRetrieval, hasError]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-xl font-semibold">问答日志</h1>

        {stats && (
          <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-lg border border-border p-4 text-sm text-muted">
            <span>总提问：<b className="text-foreground">{stats.total_questions}</b></span>
            <span>检索命中率：<b className="text-foreground">{(stats.retrieval_rate * 100).toFixed(1)}%</b>（{stats.retrieval_count}）</span>
            <span>平均耗时：<b className="text-foreground">{stats.avg_latency_ms}ms</b></span>
            <span>累计 token：<b className="text-foreground">{stats.total_tokens}</b></span>
          </div>
        )}

        <div className="flex flex-wrap gap-2 text-sm">
          <select
            value={usedRetrieval}
            onChange={(e) => setUsedRetrieval(e.target.value)}
            className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm"
          >
            <option value="">是否检索：全部</option>
            <option value="true">已检索</option>
            <option value="false">未检索</option>
          </select>
          <select
            value={hasError}
            onChange={(e) => setHasError(e.target.value)}
            className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm"
          >
            <option value="">是否报错：全部</option>
            <option value="true">报错</option>
            <option value="false">正常</option>
          </select>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}
        {data === null ? (
          <p className="text-muted">加载中…</p>
        ) : data.items.length === 0 ? (
          <p className="text-muted">暂无问答记录。</p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {data.items.map((log) => (
              <li key={log.id} className="px-4 py-3">
                <button
                  onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <span className="min-w-0 truncate text-sm text-foreground">{log.question}</span>
                  <span className="flex shrink-0 items-center gap-2 text-xs text-faint">
                    <span className={log.used_retrieval ? "text-accent" : ""}>
                      {log.used_retrieval ? "已检索" : "未检索"}
                    </span>
                    {log.error && <span className="text-red-400">报错</span>}
                    <span>{log.created_at ? new Date(log.created_at).toLocaleString("zh-CN") : ""}</span>
                  </span>
                </button>

                {expanded === log.id && (
                  <div className="mt-3 space-y-2 border-t border-border pt-3 text-sm">
                    <div className="flex flex-wrap gap-x-4 text-xs text-faint">
                      <span>耗时 {log.latency_ms ?? "-"}ms</span>
                      <span>prompt {log.tokens_prompt ?? "-"} / output {log.tokens_output ?? "-"} token</span>
                      {log.hit_chunks && log.hit_chunks.length > 0 && <span>命中 {log.hit_chunks.length} 块</span>}
                    </div>
                    {log.hit_chunks && log.hit_chunks.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-xs text-faint">命中的块：</p>
                        {log.hit_chunks.map((h, i) => (
                          <p key={i} className="text-xs text-muted">
                            {h.src_type}:{h.src_id}#{h.seq} · 分数 {h.score.toFixed(4)}
                          </p>
                        ))}
                      </div>
                    )}
                    {log.error && <p className="text-xs text-red-400">错误：{log.error}</p>}
                    {log.answer && (
                      <div className="whitespace-pre-wrap rounded-md bg-surface p-3 text-sm text-foreground">
                        {log.answer}
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
