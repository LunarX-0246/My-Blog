"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { clientFetch } from "@/lib/api";
import type { DocumentOut, TagOut } from "@/lib/types";

const fmtText: Record<string, string> = { pdf: "PDF", markdown: "Markdown", txt: "txt" };

/** 知识库管理（FR-DOC-14~18）：上传、重命名、移动目录、删除。 */
export default function AdminDocsPage() {
  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [tags, setTags] = useState<TagOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({ dir_path: "", title: "", description: "", tags: "" });

  const load = useCallback(() => {
    clientFetch<DocumentOut[]>("/api/docs")
      .then(setDocs)
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"));
  }, []);

  useEffect(() => {
    load();
    clientFetch<TagOut[]>("/api/tags").then(setTags).catch(() => {});
  }, [load]);

  async function resolveTagIds(names: string[]): Promise<number[]> {
    const ids: number[] = [];
    for (const name of names) {
      const n = name.trim();
      if (!n) continue;
      let t = tags.find((x) => x.name === n);
      if (!t) {
        t = await clientFetch<TagOut>("/api/tags", { method: "POST", body: JSON.stringify({ name: n }) });
        setTags((prev) => [...prev, t as TagOut]);
      }
      ids.push((t as TagOut).id);
    }
    return ids;
  }

  async function upload(onConflict: "error" | "overwrite" | "rename" = "error") {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("请先选择文件");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const tagNames = form.tags.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      const tagIds = await resolveTagIds(tagNames);
      const fd = new FormData();
      fd.append("file", file);
      fd.append("dir_path", form.dir_path);
      fd.append("title", form.title);
      fd.append("description", form.description);
      fd.append("tag_ids", tagIds.join(","));
      fd.append("on_conflict", onConflict);

      const res = await fetch("/api/docs", { method: "POST", body: fd });
      const body = await res.json();
      if (!res.ok) {
        if (res.status === 409 && onConflict === "error") {
          if (window.confirm("同目录下已存在同名文档。\n确定覆盖？点取消则自动另存（加后缀）。")) {
            await upload("overwrite");
            return;
          }
          await upload("rename");
          return;
        }
        setError(body?.error?.message ?? "上传失败");
        return;
      }
      if (fileRef.current) fileRef.current.value = "";
      setForm({ dir_path: "", title: "", description: "", tags: "" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function rename(doc: DocumentOut) {
    const title = window.prompt("新标题", doc.title);
    if (title === null || title === doc.title) return;
    await clientFetch(`/api/docs/${doc.id}`, { method: "PATCH", body: JSON.stringify({ title }) });
    load();
  }

  async function move(doc: DocumentOut) {
    const dir = window.prompt("新目录路径（如 八斗学院/week10，留空为根目录）", doc.dir_path);
    if (dir === null || dir === doc.dir_path) return;
    await clientFetch(`/api/docs/${doc.id}`, { method: "PATCH", body: JSON.stringify({ dir_path: dir }) });
    load();
  }

  async function remove(doc: DocumentOut) {
    if (!window.confirm(`确定删除文档「${doc.title}」吗？将同时删除原始文件，不可恢复。`)) return;
    await clientFetch(`/api/docs/${doc.id}`, { method: "DELETE" });
    load();
  }

  const inputCls =
    "rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint focus:border-accent focus:outline-none";

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-xl font-semibold">知识库管理</h1>

        {/* 上传 */}
        <div className="space-y-3 rounded-lg border border-border p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <input className={inputCls} placeholder="目录路径（留空为根目录）" value={form.dir_path}
              onChange={(e) => setForm({ ...form, dir_path: e.target.value })} />
            <input className={inputCls} placeholder="显示标题（留空用文件名）" value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <input className={inputCls} placeholder="一句话描述（可选）" value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <input className={inputCls} placeholder="标签，逗号分隔（可选）" value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })} />
          </div>
          <div className="flex items-center gap-3">
            <input ref={fileRef} type="file" accept=".pdf,.md,.markdown,.txt" className="text-sm text-muted" />
            <button onClick={() => upload("error")} disabled={busy}
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90 disabled:opacity-50">
              {busy ? "上传中…" : "上传"}
            </button>
          </div>
          <p className="text-xs text-faint">支持 PDF / Markdown / txt，单文件 ≤ 50 MB。</p>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        {/* 列表 */}
        {docs === null ? (
          <p className="text-muted">加载中…</p>
        ) : docs.length === 0 ? (
          <p className="text-muted">还没有文档。</p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{d.title}</span>
                    <span className="shrink-0 rounded-full bg-surface-hover px-2 py-0.5 text-xs text-muted">
                      {fmtText[d.file_format] ?? d.file_format}
                    </span>
                  </div>
                  <div className="mt-1 truncate text-xs text-faint">
                    {d.dir_path || "根目录"} · 索引状态：{d.idx_status}
                  </div>
                </div>
                <div className="flex shrink-0 gap-2 text-xs">
                  <button onClick={() => rename(d)} className="text-muted hover:text-foreground">重命名</button>
                  <button onClick={() => move(d)} className="text-muted hover:text-foreground">移动</button>
                  <button onClick={() => remove(d)} className="text-red-400 hover:text-foreground">删除</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
