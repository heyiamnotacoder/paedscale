import type { ExtrapolationResponse, TraceEvent } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface StreamHandlers {
  onTrace?: (ev: TraceEvent) => void;
  onResult?: (res: ExtrapolationResponse) => void;
  onError?: (detail: string) => void;
  onDone?: () => void;
}

/**
 * POST /extrapolate/stream and dispatch Server-Sent Events as they arrive:
 * `trace` events feed the reasoning sidebar; a final `result` event carries the
 * full recommendation; `error` / `done` close the run.
 */
export async function extrapolateStream(
  query: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let finished = false;
  const finish = () => {
    if (!finished) {
      finished = true;
      handlers.onDone?.();
    }
  };

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/extrapolate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal,
    });
  } catch (err) {
    handlers.onError?.(err instanceof Error ? err.message : "Network error");
    finish();
    return;
  }

  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    handlers.onError?.(body.detail ?? "Request failed");
    finish();
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (block: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let data: unknown;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }
    if (event === "trace") handlers.onTrace?.(data as TraceEvent);
    else if (event === "result") handlers.onResult?.(data as ExtrapolationResponse);
    else if (event === "error") handlers.onError?.((data as { detail?: string }).detail ?? "Run failed");
    else if (event === "done") finish();
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) if (block.trim()) dispatch(block);
    }
    if (buffer.trim()) dispatch(buffer);
  } catch (err) {
    handlers.onError?.(err instanceof Error ? err.message : "Stream interrupted");
  } finally {
    finish();
  }
}
