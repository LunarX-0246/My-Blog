// SSE 解析（技术方案 §8.3）。浏览器直连 FastAPI /api/ask，不经 Node 中转（A2）。

import type { AskSource } from "./types";

export interface SourcesEvent {
  used_retrieval: boolean;
  sources: AskSource[];
  metadata_tools?: string[];
}

export interface AskHandlers {
  onStatus?: (stage: string) => void;
  onSources?: (data: SourcesEvent) => void;
  onDelta?: (text: string) => void;
  onDone?: (data: { latency_ms: number }) => void;
  onError?: (message: string) => void;
}

export async function streamAsk(
  body: { question: string; history: { role: string; content: string }[]; scope?: object },
  handlers: AskHandlers,
): Promise<void> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    const errBody = (await res.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    handlers.onError?.(errBody?.error?.message ?? "请求失败，请稍后再试");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      let event = "message";
      let data = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!data) continue;
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(data);
      } catch {
        continue;
      }
      if (event === "status") handlers.onStatus?.(String(parsed.stage ?? ""));
      else if (event === "sources") handlers.onSources?.(parsed as unknown as SourcesEvent);
      else if (event === "delta") handlers.onDelta?.(String(parsed.text ?? ""));
      else if (event === "done") handlers.onDone?.(parsed as unknown as { latency_ms: number });
      else if (event === "error") handlers.onError?.(String(parsed.message ?? ""));
    }
  }
}
