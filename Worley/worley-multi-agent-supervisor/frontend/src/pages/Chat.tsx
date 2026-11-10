import { useState, useRef, useEffect, MutableRefObject } from "react";
import { Send, Loader2, Sparkles } from "lucide-react";
import ChatMessage from "../components/ChatMessage";
import { sendMessageStream, ChatMessage as ChatMsg } from "../api/client";

const SUGGESTED: { question: string; agent: "knowledge" | "genie" | "general" }[] = [
  { question: "What is Worley's strategy for the energy transition?", agent: "knowledge" },
  { question: "How many employees does Worley have?", agent: "knowledge" },
  { question: "What are Worley's sustainability targets?", agent: "knowledge" },
  { question: "What safety procedures apply to offshore operations?", agent: "knowledge" },
  { question: "What was Worley's highest closing price in 2024?", agent: "genie" },
  { question: "Show me Worley's average trading volume by month.", agent: "genie" },
  { question: "What are the key risks for an LNG construction project?", agent: "general" },
  { question: "Explain the difference between green and blue hydrogen.", agent: "general" },
];

const AGENT_BORDER: Record<string, string> = {
  knowledge: "border-l-lime-500",
  genie: "border-l-amber-500",
  general: "border-l-teal-500",
};

const AGENT_LABEL: Record<string, string> = {
  knowledge: "Knowledge",
  genie: "ASX Data",
  general: "General",
};

const AGENT_DOT: Record<string, string> = {
  knowledge: "bg-lime-500",
  genie: "bg-amber-500",
  general: "bg-teal-500",
};

export default function Chat({ onResetRef }: { onResetRef?: MutableRefObject<(() => void) | undefined> }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (onResetRef) {
      onResetRef.current = () => {
        setMessages([]);
        setInput("");
      };
    }
  }, [onResetRef]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const history = [...messages, { role: "user", content: msg }];
    setMessages(history);
    setInput("");
    setLoading(true);

    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      await sendMessageStream(msg, messages, {
        onDelta: (content) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, content: last.content + content };
            return updated;
          });
        },
        onMetadata: (meta) => {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              routed_agent: meta.routed_agent,
              latency_ms: meta.latency_ms,
              sub_agent_input: meta.sub_agent_input,
              sub_agent_output: meta.sub_agent_output,
            };
            return updated;
          });
        },
        onError: (error) => {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: `Error: ${error}` };
            return updated;
          });
        },
        onDone: () => {},
      }, controller.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
          };
          return updated;
        });
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="flex flex-col h-full bg-cream">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="w-16 h-16 rounded-2xl bg-petrol-700 flex items-center justify-center mb-5 shadow-lg">
              <Sparkles size={28} className="text-teal-400" />
            </div>
            <h2 className="font-heading text-xl font-semibold text-petrol-700 mb-2">
              Worley Multi-Agent Supervisor
            </h2>
            <p className="text-[13px] text-petrol-400 text-center max-w-md leading-relaxed mb-8">
              Ask questions and the supervisor will route them to the best
              sub-agent — Knowledge Assistant for Worley-specific topics, or
              the general assistant for everything else.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl w-full">
              {SUGGESTED.map((s) => (
                <button
                  key={s.question}
                  onClick={() => send(s.question)}
                  className={`text-left text-[12px] leading-relaxed p-3.5 bg-white border border-ui-gray border-l-[3px] ${AGENT_BORDER[s.agent]} rounded-xl hover:shadow-sm transition-all text-petrol-600`}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className={`w-1.5 h-1.5 rounded-full ${AGENT_DOT[s.agent]}`} />
                    <span className="text-[10px] font-semibold text-petrol-400 uppercase tracking-wider">{AGENT_LABEL[s.agent]}</span>
                  </div>
                  {s.question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-5">
            {messages.map((msg, i) => (
              <ChatMessage
                key={i}
                role={msg.role}
                content={msg.content}
                isStreaming={loading && i === messages.length - 1 && msg.role === "assistant"}
                routed_agent={msg.routed_agent}
                latency_ms={msg.latency_ms}
              />
            ))}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="border-t border-ui-gray bg-white px-6 py-3.5">
        <div className="max-w-3xl mx-auto flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask the supervisor..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-petrol-100 bg-cream px-4 py-3 text-[13px] text-petrol-800 placeholder:text-petrol-300 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent transition-shadow"
            style={{ minHeight: "44px", maxHeight: "120px" }}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 120) + "px";
            }}
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            className="px-4 py-3 bg-lime-500 hover:bg-lime-400 text-petrol-900 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-semibold"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}
