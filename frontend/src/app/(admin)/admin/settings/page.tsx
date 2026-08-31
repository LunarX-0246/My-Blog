"use client";

import { useEffect, useState } from "react";

import { clientFetch } from "@/lib/api";

interface AskLimits {
  per_hour: number;
  daily_total: number;
  max_chars: number;
}

interface Settings {
  presets: string[];
  limits: AskLimits | null;
}

/** 站点设置（FR-ASK-07、FR-ASK-22）：预设问题、限流阈值。 */
export default function SettingsPage() {
  const [presetsText, setPresetsText] = useState("");
  const [limits, setLimits] = useState<AskLimits>({ per_hour: 10, daily_total: 200, max_chars: 1000 });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    clientFetch<Settings>("/api/admin/settings")
      .then((d) => {
        setPresetsText(d.presets.join("\n"));
        if (d.limits) setLimits(d.limits);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"));
  }, []);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const presets = presetsText.split("\n").map((s) => s.trim()).filter(Boolean);
      await clientFetch("/api/admin/settings", {
        method: "PUT",
        body: JSON.stringify({ presets, limits }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  const inputCls =
    "rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint focus:border-accent focus:outline-none";

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-2xl space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">站点设置</h1>
          <button
            onClick={save}
            disabled={saving}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90 disabled:opacity-50"
          >
            {saved ? "已保存" : saving ? "保存中…" : "保存"}
          </button>
        </header>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <section className="space-y-2">
          <h2 className="text-sm font-medium text-muted">预设问题（每行一个，FR-ASK-07）</h2>
          <textarea
            className={`${inputCls} w-full`}
            rows={4}
            value={presetsText}
            onChange={(e) => setPresetsText(e.target.value)}
            placeholder={"这个博客主要讲什么？\n什么是混合检索？"}
          />
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-medium text-muted">问答限流阈值（FR-ASK-19~22）</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block space-y-1">
              <span className="text-xs text-muted">每小时/单 IP</span>
              <input
                type="number"
                className={`${inputCls} w-full`}
                value={limits.per_hour}
                onChange={(e) => setLimits({ ...limits, per_hour: Number(e.target.value) })}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-muted">每日总量熔断</span>
              <input
                type="number"
                className={`${inputCls} w-full`}
                value={limits.daily_total}
                onChange={(e) => setLimits({ ...limits, daily_total: Number(e.target.value) })}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-muted">单问长度上限（字）</span>
              <input
                type="number"
                className={`${inputCls} w-full`}
                value={limits.max_chars}
                onChange={(e) => setLimits({ ...limits, max_chars: Number(e.target.value) })}
              />
            </label>
          </div>
        </section>
      </div>
    </main>
  );
}
