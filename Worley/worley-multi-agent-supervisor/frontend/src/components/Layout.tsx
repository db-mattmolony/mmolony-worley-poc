import { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { MessageSquare, Activity, Plus } from "lucide-react";

const TABS = [
  { path: "/", label: "Chat", icon: MessageSquare },
  { path: "/monitoring", label: "Monitoring", icon: Activity },
];

export default function Layout({ children, onNewChat }: { children: ReactNode; onNewChat?: () => void }) {
  const location = useLocation();

  return (
    <div className="flex flex-col h-screen bg-cream">
      <header className="bg-petrol-700 shrink-0">
        <div className="flex items-center justify-between px-5 h-14">
          <div className="flex items-center gap-3">
            <img src="/worley-logo.png" alt="Worley" className="h-7 bg-white rounded px-1.5 py-0.5" />
            <span className="text-white font-heading text-[15px] font-semibold tracking-wide">
              Multi-Agent Supervisor
            </span>
          </div>

          <div className="flex items-center gap-2">
            {location.pathname === "/" && onNewChat && (
              <button
                onClick={onNewChat}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-[13px] font-medium text-white/70 hover:text-white hover:bg-white/10 transition-colors"
              >
                <Plus size={15} />
                New Chat
              </button>
            )}
            <nav className="flex gap-1">
              {TABS.map((tab) => {
                const active = location.pathname === tab.path;
                return (
                  <Link
                    key={tab.path}
                    to={tab.path}
                    className={`flex items-center gap-2 px-4 py-1.5 rounded-pill text-[13px] font-medium transition-colors ${
                      active
                        ? "bg-teal-500 text-petrol-900"
                        : "text-white/70 hover:text-white hover:bg-white/10"
                    }`}
                  >
                    <tab.icon size={15} />
                    {tab.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
