import ReactMarkdown from "react-markdown";
import { Bot, User, Zap, Clock } from "lucide-react";

interface Props {
  role: string;
  content: string;
  isStreaming?: boolean;
  routed_agent?: string;
  latency_ms?: number;
}

const AGENT_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  knowledge_assistant: { label: "Knowledge Assistant", color: "text-lime-700", bg: "bg-lime-100" },
  general_assistant: { label: "General Assistant", color: "text-teal-700", bg: "bg-teal-50" },
  genie_space: { label: "Genie · ASX Data", color: "text-amber-700", bg: "bg-amber-50" },
};

export default function ChatMessage({
  role,
  content,
  isStreaming,
  routed_agent,
  latency_ms,
}: Props) {
  const isUser = role === "user";
  const agent = routed_agent && routed_agent !== "unknown" && routed_agent !== "done"
    ? AGENT_CONFIG[routed_agent] || { label: routed_agent, color: "text-petrol-600", bg: "bg-petrol-50" }
    : null;

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : ""}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-lg bg-petrol-700 flex items-center justify-center shrink-0">
          <Bot size={16} className="text-teal-400" />
        </div>
      )}

      <div className="max-w-[75%] flex flex-col gap-1">
        {/* Message bubble */}
        <div
          className={`px-4 py-3 text-[13px] leading-relaxed ${
            isUser
              ? "bg-petrol-700 text-white rounded-2xl rounded-br-sm"
              : "bg-petrol-50 text-petrol-800 rounded-2xl rounded-bl-sm"
          }`}
        >
          {isUser ? (
            <p>{content}</p>
          ) : (
            <div className="prose-chat">
              <ReactMarkdown>{content}</ReactMarkdown>
              {isStreaming && (
                <span className="inline-block w-2 h-4 bg-teal-500 animate-pulse ml-0.5" />
              )}
            </div>
          )}
        </div>

        {/* Agent routing info bar */}
        {!isUser && agent && (
          <div className="flex items-center gap-2 px-1 mt-0.5">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${agent.bg} ${agent.color}`}>
              <Zap size={10} />
              {agent.label}
            </span>
            {latency_ms != null && latency_ms > 0 && (
              <span className="inline-flex items-center gap-1 text-[10px] text-petrol-400">
                <Clock size={10} />
                {latency_ms >= 1000
                  ? `${(latency_ms / 1000).toFixed(1)}s`
                  : `${Math.round(latency_ms)}ms`}
              </span>
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-lg bg-petrol-200 flex items-center justify-center shrink-0">
          <User size={16} className="text-petrol-700" />
        </div>
      )}
    </div>
  );
}
