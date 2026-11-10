import { useState, useEffect } from "react";
import { RefreshCw, Loader2 } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  AreaChart, Area, PieChart, Pie, Cell, ScatterChart, Scatter,
} from "recharts";
import { fetchTraces, TraceData } from "../api/client";

const COLORS = {
  petrol: "#003645",
  teal: "#29c8c1",
  lime: "#81d114",
  coral: "#f43a4f",
  gray: "#99bbc4",
  amber: "#f59e0b",
};

const AGENT_COLORS: Record<string, string> = {
  general_assistant: COLORS.teal,
  knowledge_assistant: COLORS.lime,
  genie_space: COLORS.amber,
  done: COLORS.gray,
  unknown: "#ccdde2",
};

function KpiCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color: string }) {
  return (
    <div className="bg-white rounded-xl border border-ui-gray p-5 flex-1 min-w-[160px]">
      <div className="text-[11px] text-petrol-400 uppercase tracking-wider font-semibold">
        {label}
      </div>
      <div className="text-[28px] font-heading font-bold mt-1" style={{ color }}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-petrol-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function Monitoring() {
  const [traces, setTraces] = useState<TraceData[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => { refresh(); }, []);

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await fetchTraces();
      setTraces(data);
      setLoaded(true);
    } catch (err) {
      console.error("Failed to fetch traces:", err);
    } finally {
      setLoading(false);
    }
  };

  // === KPIs ===
  const total = traces.length;
  const avgLatency = total ? Math.round(traces.reduce((s, t) => s + t.latency_ms, 0) / total) : 0;
  const totalTokens = traces.reduce((s, t) => s + t.total_tokens, 0);
  const totalInputTokens = traces.reduce((s, t) => s + t.input_tokens, 0);
  const totalOutputTokens = traces.reduce((s, t) => s + t.output_tokens, 0);
  const totalCacheTokens = traces.reduce((s, t) => s + t.cache_read_tokens, 0);
  const errors = traces.filter((t) => t.status !== "OK").length;
  const errorRate = total ? ((errors / total) * 100).toFixed(1) : "0.0";
  const cacheRate = totalInputTokens ? ((totalCacheTokens / totalInputTokens) * 100).toFixed(1) : "0.0";
  const avgRatio = totalInputTokens ? (totalOutputTokens / totalInputTokens).toFixed(2) : "0.00";

  // === Requests over time grouped by agent ===
  const timeByAgent = new Map<string, { general: number; knowledge: number; genie: number }>();
  traces.forEach((t) => {
    const hour = t.timestamp.slice(0, 13) + ":00";
    const entry = timeByAgent.get(hour) || { general: 0, knowledge: 0, genie: 0 };
    if (t.routed_agent === "knowledge_assistant") entry.knowledge += 1;
    else if (t.routed_agent === "genie_space") entry.genie += 1;
    else entry.general += 1;
    timeByAgent.set(hour, entry);
  });
  const timeData = [...timeByAgent.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([time, v]) => ({ time: time.slice(11, 16), general: v.general, knowledge: v.knowledge, genie: v.genie }));

  // === Token consumption (cumulative, by agent) ===
  const sorted = [...traces].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  let cumGeneral = 0, cumKnowledge = 0, cumGenie = 0;
  const tokenData = sorted.map((t) => {
    if (t.routed_agent === "knowledge_assistant") cumKnowledge += t.total_tokens;
    else if (t.routed_agent === "genie_space") cumGenie += t.total_tokens;
    else cumGeneral += t.total_tokens;
    return { time: t.timestamp.slice(11, 16), general: cumGeneral, knowledge: cumKnowledge, genie: cumGenie };
  });

  // === Latency buckets grouped by agent ===
  const latencyByAgent = new Map<string, { general: number; knowledge: number; genie: number }>();
  traces.forEach((t) => {
    const bucket = `${Math.floor(t.latency_ms / 500) * 500}`;
    const entry = latencyByAgent.get(bucket) || { general: 0, knowledge: 0, genie: 0 };
    if (t.routed_agent === "knowledge_assistant") entry.knowledge += 1;
    else if (t.routed_agent === "genie_space") entry.genie += 1;
    else entry.general += 1;
    latencyByAgent.set(bucket, entry);
  });
  const latencyData = [...latencyByAgent.entries()]
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([ms, v]) => ({ ms: `${ms}ms`, general: v.general, knowledge: v.knowledge, genie: v.genie }));

  // === Agent delegation ===
  const agentMap = new Map<string, number>();
  traces.forEach((t) => {
    if (t.routed_agent !== "done") {
      agentMap.set(t.routed_agent, (agentMap.get(t.routed_agent) || 0) + 1);
    }
  });
  const agentData = [...agentMap.entries()].map(([name, value]) => ({
    name,
    value,
    color: AGENT_COLORS[name] || COLORS.gray,
  }));

  // === Token efficiency scatter ===
  const tokenScatter = traces.map((t) => ({
    input: t.input_tokens,
    output: t.output_tokens,
    agent: t.routed_agent,
    question: t.question?.slice(0, 40) || "",
    fill: AGENT_COLORS[t.routed_agent] || COLORS.gray,
  }));

  // === Latency vs complexity scatter ===
  const complexityScatter = traces
    .filter((t) => t.num_spans > 0)
    .map((t) => ({
      spans: t.num_spans,
      latency: t.latency_ms,
      agent: t.routed_agent,
      fill: AGENT_COLORS[t.routed_agent] || COLORS.gray,
    }));

  // === Trace size over time ===
  const traceSizeData = sorted
    .filter((t) => t.trace_size_bytes > 0)
    .map((t) => ({
      time: t.timestamp.slice(11, 16),
      size: Math.round(t.trace_size_bytes / 1024 * 10) / 10,
    }));

  // === Span count breakdown ===
  const spanCounts = new Map<number, number>();
  traces.forEach((t) => {
    if (t.num_spans > 0) {
      spanCounts.set(t.num_spans, (spanCounts.get(t.num_spans) || 0) + 1);
    }
  });
  const spanData = [...spanCounts.entries()]
    .sort(([a], [b]) => a - b)
    .map(([spans, count]) => ({ spans: `${spans} spans`, count }));

  return (
    <div className="h-full overflow-y-auto bg-cream px-6 py-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="font-heading text-lg font-semibold text-petrol-700">
            Agent Monitoring
          </h1>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-lime-500 hover:bg-lime-400 text-petrol-900 rounded-xl text-[13px] font-semibold disabled:opacity-50 transition-colors"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            Refresh
          </button>
        </div>

        {!loaded ? (
          <div className="flex flex-col items-center justify-center py-24 text-petrol-400">
            <Activity size={40} className="mb-4 opacity-30" />
            <p className="text-[13px]">Click Refresh to load trace data</p>
          </div>
        ) : (
          <>
            {/* KPIs Row 1 */}
            <div className="flex gap-4 flex-wrap mb-4">
              <KpiCard label="Total Requests" value={total.toLocaleString()} color={COLORS.petrol} />
              <KpiCard label="Avg Latency" value={`${avgLatency.toLocaleString()}ms`} color={COLORS.teal} />
              <KpiCard label="Total Tokens" value={totalTokens.toLocaleString()} color={COLORS.lime} />
              <KpiCard
                label="Error Rate"
                value={`${errorRate}%`}
                color={Number(errorRate) > 5 ? COLORS.coral : COLORS.lime}
              />
            </div>

            {/* KPIs Row 2 */}
            <div className="flex gap-4 flex-wrap mb-6">
              <KpiCard
                label="Cache Hit Rate"
                value={`${cacheRate}%`}
                sub={`${totalCacheTokens.toLocaleString()} / ${totalInputTokens.toLocaleString()} input tokens`}
                color={Number(cacheRate) > 0 ? COLORS.lime : COLORS.amber}
              />
              <KpiCard
                label="Output / Input Ratio"
                value={avgRatio}
                sub="Higher = more detailed responses"
                color={COLORS.teal}
              />
              <KpiCard
                label="Avg Spans"
                value={total ? (traces.reduce((s, t) => s + t.num_spans, 0) / total).toFixed(1) : "0"}
                sub="8 = direct, 10 = KA route"
                color={COLORS.petrol}
              />
              <KpiCard
                label="Avg Trace Size"
                value={total ? `${(traces.reduce((s, t) => s + t.trace_size_bytes, 0) / total / 1024).toFixed(1)}KB` : "0KB"}
                sub="Processing complexity"
                color={COLORS.gray}
              />
            </div>

            {/* Charts Row 1: Requests + Tokens */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">
                  Requests Over Time
                  <span className="text-[11px] text-petrol-400 font-normal ml-2">by sub-agent</span>
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={timeData}>
                    <XAxis dataKey="time" tick={{ fontSize: 11, fill: "#337781" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#337781" }} />
                    <Tooltip />
                    <Bar dataKey="general" stackId="a" fill={COLORS.teal} name="General Assistant" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="knowledge" stackId="a" fill={COLORS.lime} name="Knowledge Assistant" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="genie" stackId="a" fill={COLORS.amber} name="Genie · ASX Data" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">
                  Cumulative Token Consumption
                  <span className="text-[11px] text-petrol-400 font-normal ml-2">by sub-agent</span>
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={tokenData}>
                    <XAxis dataKey="time" tick={{ fontSize: 11, fill: "#337781" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#337781" }} />
                    <Tooltip />
                    <Area type="monotone" dataKey="general" stackId="1" fill={COLORS.teal} stroke={COLORS.teal} fillOpacity={0.3} name="General Assistant" />
                    <Area type="monotone" dataKey="knowledge" stackId="1" fill={COLORS.lime} stroke={COLORS.lime} fillOpacity={0.3} name="Knowledge Assistant" />
                    <Area type="monotone" dataKey="genie" stackId="1" fill={COLORS.amber} stroke={COLORS.amber} fillOpacity={0.3} name="Genie · ASX Data" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Charts Row 2: Latency + Agent Delegation */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">
                  Latency Distribution
                  <span className="text-[11px] text-petrol-400 font-normal ml-2">by sub-agent</span>
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={latencyData}>
                    <XAxis dataKey="ms" tick={{ fontSize: 11, fill: "#337781" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#337781" }} />
                    <Tooltip />
                    <Bar dataKey="general" stackId="a" fill={COLORS.teal} name="General Assistant" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="knowledge" stackId="a" fill={COLORS.lime} name="Knowledge Assistant" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="genie" stackId="a" fill={COLORS.amber} name="Genie · ASX Data" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">Sub-Agent Delegation</h3>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={agentData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={3}
                      dataKey="value"
                      label={({ name, percent }) =>
                        `${name} ${(percent * 100).toFixed(0)}%`
                      }
                    >
                      {agentData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Charts Row 3: Token Efficiency + Latency vs Complexity */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">
                  Token Efficiency
                  <span className="text-[11px] text-petrol-400 font-normal ml-2">Input vs Output tokens per request</span>
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <ScatterChart>
                    <XAxis dataKey="input" name="Input Tokens" tick={{ fontSize: 11, fill: "#337781" }} />
                    <YAxis dataKey="output" name="Output Tokens" tick={{ fontSize: 11, fill: "#337781" }} />
                    <Tooltip
                      content={({ payload }) => {
                        if (!payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-white border border-ui-gray rounded-lg p-2 text-[11px] shadow-sm">
                            <div className="font-semibold text-petrol-700">{d.question || "N/A"}</div>
                            <div className="text-petrol-500">In: {d.input} → Out: {d.output}</div>
                            <div className="text-petrol-400">{d.agent}</div>
                          </div>
                        );
                      }}
                    />
                    <Scatter data={tokenScatter} fill={COLORS.teal}>
                      {tokenScatter.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">
                  Latency vs Complexity
                  <span className="text-[11px] text-petrol-400 font-normal ml-2">Span count vs execution time</span>
                </h3>
                {complexityScatter.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <ScatterChart>
                      <XAxis dataKey="spans" name="Spans" tick={{ fontSize: 11, fill: "#337781" }} />
                      <YAxis dataKey="latency" name="Latency (ms)" tick={{ fontSize: 11, fill: "#337781" }} />
                      <Tooltip
                        content={({ payload }) => {
                          if (!payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div className="bg-white border border-ui-gray rounded-lg p-2 text-[11px] shadow-sm">
                              <div className="text-petrol-700">{d.spans} spans · {d.latency}ms</div>
                              <div className="text-petrol-400">{d.agent}</div>
                            </div>
                          );
                        }}
                      />
                      <Scatter data={complexityScatter} fill={COLORS.petrol}>
                        {complexityScatter.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-[220px] text-petrol-400 text-[12px]">
                    No span data available
                  </div>
                )}
              </div>
            </div>

            {/* Charts Row 4: Trace Size + Span Breakdown */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">
                  Trace Size Over Time
                  <span className="text-[11px] text-petrol-400 font-normal ml-2">KB per request</span>
                </h3>
                {traceSizeData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={traceSizeData}>
                      <XAxis dataKey="time" tick={{ fontSize: 11, fill: "#337781" }} />
                      <YAxis tick={{ fontSize: 11, fill: "#337781" }} unit="KB" />
                      <Tooltip />
                      <Area type="monotone" dataKey="size" fill={COLORS.petrol} stroke={COLORS.petrol} fillOpacity={0.2} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-[220px] text-petrol-400 text-[12px]">
                    No size data available
                  </div>
                )}
              </div>

              <div className="bg-white rounded-xl border border-ui-gray p-5">
                <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">
                  Routing Complexity
                  <span className="text-[11px] text-petrol-400 font-normal ml-2">Span count distribution</span>
                </h3>
                {spanData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={spanData}>
                      <XAxis dataKey="spans" tick={{ fontSize: 11, fill: "#337781" }} />
                      <YAxis tick={{ fontSize: 11, fill: "#337781" }} />
                      <Tooltip />
                      <Bar dataKey="count" fill={COLORS.lime} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-[220px] text-petrol-400 text-[12px]">
                    No span data available
                  </div>
                )}
              </div>
            </div>

            {/* Traces Table */}
            <div className="bg-white rounded-xl border border-ui-gray p-5">
              <h3 className="text-[13px] font-semibold text-petrol-700 mb-4">Recent Traces</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-ui-gray text-left text-petrol-400">
                      <th className="pb-2 pr-4 font-semibold">Time</th>
                      <th className="pb-2 pr-4 font-semibold">Status</th>
                      <th className="pb-2 pr-4 font-semibold">Latency</th>
                      <th className="pb-2 pr-4 font-semibold">Tokens</th>
                      <th className="pb-2 pr-4 font-semibold">Spans</th>
                      <th className="pb-2 pr-4 font-semibold">Agent</th>
                      <th className="pb-2 pr-4 font-semibold">Model</th>
                      <th className="pb-2 font-semibold">Question</th>
                    </tr>
                  </thead>
                  <tbody>
                    {traces.slice(0, 50).map((t, i) => (
                      <tr key={i} className="border-b border-ui-gray/50 hover:bg-cream/50">
                        <td className="py-2 pr-4 text-petrol-600">{t.timestamp.slice(0, 19).replace("T", " ")}</td>
                        <td className="py-2 pr-4">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                              t.status === "OK"
                                ? "bg-teal-50 text-teal-700"
                                : "bg-red-50 text-coral-500"
                            }`}
                          >
                            {t.status}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-petrol-600">{t.latency_ms.toLocaleString()}ms</td>
                        <td className="py-2 pr-4 text-petrol-600">{t.total_tokens.toLocaleString()}</td>
                        <td className="py-2 pr-4 text-petrol-600">{t.num_spans || "-"}</td>
                        <td className="py-2 pr-4 text-petrol-600">{t.routed_agent}</td>
                        <td className="py-2 pr-4 text-petrol-400">{t.model}</td>
                        <td className="py-2 text-petrol-600 truncate max-w-[200px]">{t.question}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Activity({ size, className }: { size: number; className?: string }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" className={className}
    >
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}
