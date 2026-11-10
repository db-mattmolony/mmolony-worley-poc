export interface ChatMessage {
  role: string;
  content: string;
  routed_agent?: string;
  sub_agent_input?: string;
  sub_agent_output?: string;
  latency_ms?: number;
}

export interface TraceData {
  timestamp: string;
  status: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_read_tokens: number;
  num_spans: number;
  trace_size_bytes: number;
  span_p50: number;
  span_max: number;
  model_version_id: string;
  routed_agent: string;
  model: string;
  question: string;
  source: string;
}

export async function sendMessage(
  message: string,
  history: ChatMessage[]
): Promise<{ content: string; latency_ms: number; routed_agent: string; sub_agent_input: string; sub_agent_output: string }> {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!resp.ok) throw new Error(`Chat failed: ${resp.status}`);
  return resp.json();
}

interface StreamCallbacks {
  onDelta: (content: string) => void;
  onMetadata: (meta: { routed_agent: string; latency_ms: number; sub_agent_input: string; sub_agent_output: string }) => void;
  onError: (error: string) => void;
  onDone: () => void;
}

export async function sendMessageStream(
  message: string,
  history: ChatMessage[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
    signal,
  });

  if (!resp.ok) throw new Error(`Chat stream failed: ${resp.status}`);

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;

      const payload = trimmed.slice(6);
      if (payload === "[DONE]") {
        callbacks.onDone();
        return;
      }

      try {
        const event = JSON.parse(payload);
        switch (event.type) {
          case "delta":
            callbacks.onDelta(event.content);
            break;
          case "metadata":
            callbacks.onMetadata(event);
            break;
          case "error":
            callbacks.onError(event.content);
            break;
        }
      } catch {
        // Skip malformed events
      }
    }
  }
}

export async function fetchTraces(
  maxResults = 200
): Promise<TraceData[]> {
  const resp = await fetch(`/api/traces?max_results=${maxResults}`);
  if (!resp.ok) throw new Error(`Traces failed: ${resp.status}`);
  const data = await resp.json();
  return data.traces ?? [];
}
