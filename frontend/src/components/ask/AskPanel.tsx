"use client";

import { useEffect, useRef, useState } from "react";

import { clientFetch } from "@/lib/api";
import { streamAsk } from "@/lib/stream";
import type { AskHistoryItem, AskSource } from "@/lib/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources: AskSource[];
  usedRetrieval: boolean | null;
  metadataTools: string[];
}

const STORAGE_KEY = "blog_ask_history";
const MAX_CHARS = 1000;

const stageText: Record<string, string> = {
  deciding: "正在判断…",
  retrieving: "正在检索知识库…",
  listing: "正在查看文章清单…",
  outlining: "正在查看文章目录…",
  sectioning: "正在查看文章章节…",
  generating: "正在生成…",
};

const metadataToolText: Record<string, string> = {
  list_posts: "文章清单",
  get_post_outline: "文章目录",
  get_post_section: "文章章节",
};

/** 渲染引用角标 [n] 为可点击链接（FR-ASK-12）。 */
function renderContent(content: string, sources: AskSource[]) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m && sources.length > 0) {
      const src = sources.find((s) => s.n === Number(m[1]));
      if (src) {
        return (
          <a
            key={i}
            href={src.url}
            className="ml-0.5 align-super text-xs text-accent hover:underline"
          >
            [{m[1]}]
          </a>
        );
      }
    }
    return <span key={i}>{part}</span>;
  });
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }
  return (
    <button onClick={copy} className="text-xs text-faint hover:text-foreground">
      {copied ? "已复制" : "复制"}
    </button>
  );
}

/** AI 问答面板（FR-ASK-01~08、10、16、17）。首页与独立问答页共用（FR-ASK-02）。 */
export default function AskPanel({
  scope,
  compact = false,
}: {
  scope?: { post_slug: string };
  compact?: boolean;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [presets, setPresets] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const items = JSON.parse(raw) as AskHistoryItem[];
        setMessages(
          items.map((i) => ({
            role: i.role,
            content: i.content,
            sources: [],
            usedRetrieval: null,
            metadataTools: [],
          })),
        );
      } catch {
        /* ignore */
      }
    }
    clientFetch<string[]>("/api/ask/presets")
      .then(setPresets)
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, stage]);

  function saveHistory(msgs: Message[]) {
    const items: AskHistoryItem[] = msgs.map((m) => ({ role: m.role, content: m.content }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || loading) return;
    setInput("");
    const history: AskHistoryItem[] = messages.map((m) => ({ role: m.role, content: m.content }));
    const next = [...messages, { role: "user" as const, content: question, sources: [], usedRetrieval: null, metadataTools: [] }];
    setMessages(next);
    setLoading(true);
    setStage("deciding");

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", sources: [], usedRetrieval: null, metadataTools: [] },
    ]);

    function patchAssistant(patch: (m: Message) => Message) {
      setMessages((prev) => {
        const copy = [...prev];
        const idx = copy.length - 1;
        copy[idx] = patch(copy[idx]);
        return copy;
      });
    }

    try {
      await streamAsk(
        { question, history, scope },
        {
          onStatus: (s) => setStage(s),
          onSources: (d) =>
            patchAssistant((m) => ({
              ...m,
              usedRetrieval: d.used_retrieval,
              sources: d.sources,
              metadataTools: d.metadata_tools ?? [],
            })),
          onDelta: (t) => patchAssistant((m) => ({ ...m, content: m.content + t })),
          onError: (msg) =>
            patchAssistant((m) => ({ ...m, content: m.content || msg, usedRetrieval: false })),
        },
      );
    } finally {
      setLoading(false);
      setStage("");
      setMessages((prev) => {
        saveHistory(prev);
        return prev;
      });
    }
  }

  function clear() {
    localStorage.removeItem(STORAGE_KEY);
    setMessages([]);
  }

  const inputCls =
    "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint focus:border-accent focus:outline-none";

  return (
    <div className={compact ? "" : "mx-auto max-w-3xl"}>
      <div className={`space-y-4 ${compact ? "max-h-[60vh] overflow-y-auto" : ""}`}>
        {messages.length === 0 && !loading && (
          <div className="space-y-3">
            <p className="text-sm text-muted">就站内内容提问，回答带可验证出处。</p>
            {presets.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {presets.map((p) => (
                  <button
                    key={p}
                    onClick={() => void send(p)}
                    className="rounded-full border border-border px-3 py-1 text-xs text-muted hover:text-foreground"
                  >
                    {p}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            <div
              className={`inline-block max-w-full rounded-lg px-4 py-2 text-sm ${
                m.role === "user" ? "bg-accent text-accent-foreground" : "text-foreground"
              }`}
            >
              {m.role === "assistant" ? (
                <div className="whitespace-pre-wrap">{renderContent(m.content, m.sources)}</div>
              ) : (
                m.content
              )}
            </div>

            {m.role === "assistant" && m.content && (
              <div className="mt-1 flex items-center justify-between">
                <span className="text-xs text-faint">
                  {[
                    m.usedRetrieval ? "已检索知识库" : "",
                    m.metadataTools.length > 0
                      ? `查看了${m.metadataTools.map((t) => metadataToolText[t] ?? t).join("、")}`
                      : "",
                    !m.usedRetrieval && m.metadataTools.length === 0 && m.usedRetrieval === false
                      ? "本次未检索知识库"
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                <CopyButton text={m.content} />
              </div>
            )}

            {m.role === "assistant" && m.sources.length > 0 && (
              <div className="mt-2 space-y-2">
                {m.sources.map((s) => (
                  <a
                    key={s.n}
                    href={s.url}
                    className="block rounded-md border border-border p-3 text-left hover:border-accent"
                  >
                    <div className="text-xs text-accent">
                      [{s.n}] {s.type === "post" ? "文章" : "文档"} · {s.title}
                    </div>
                    <div className="mt-1 line-clamp-2 text-xs text-muted">{s.excerpt}</div>
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && stage && <p className="text-xs text-faint">{stageText[stage] ?? ""}</p>}
        <div ref={bottomRef} />
      </div>

      <div className="mt-4 space-y-2">
        <textarea
          className={inputCls}
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(input);
            }
          }}
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        />
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs">
            <span className={input.length > MAX_CHARS ? "text-red-400" : "text-faint"}>
              {input.length}/{MAX_CHARS}
            </span>
            {messages.length > 0 && (
              <button onClick={clear} className="text-faint hover:text-foreground">
                清空会话
              </button>
            )}
          </div>
          <button
            onClick={() => void send(input)}
            disabled={loading || !input.trim() || input.length > MAX_CHARS}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "回答中…" : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
