import { useEffect, useState } from "react";
import { useQuery } from "convex/react";
import { api } from "../../../convex/_generated/api.js";
import { IntegrationLogo } from "../lib/branding.js";

interface Provider {
  name: string;
  configured: boolean;
  scopes: string[];
  redirectUri: string;
}

const STATUS_COLORS: Record<string, { dot: string; label: string; badge: string }> = {
  active: {
    dot: "bg-emerald-400",
    label: "Connected",
    badge: "bg-emerald-400/10 text-emerald-500",
  },
  revoked: {
    dot: "bg-slate-500",
    label: "Disconnected",
    badge: "bg-slate-400/10 text-slate-500",
  },
  error: {
    dot: "bg-rose-400",
    label: "Error",
    badge: "bg-rose-400/10 text-rose-500",
  },
};

export function ConnectionsPanel({ isDark }: { isDark: boolean }) {
  const connections = useQuery(api.connections.list, {}) ?? [];
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch("/api/oauth/providers")
      .then((r) => r.json())
      .then((p) => setProviders(p))
      .catch(() => setProviders([]))
      .finally(() => setLoaded(true));
  }, []);

  const cardBg = isDark
    ? "bg-slate-900/50 border-slate-800"
    : "bg-white border-slate-200";
  const muted = isDark ? "text-slate-500" : "text-slate-400";

  function openOAuth(name: string) {
    const w = 600;
    const h = 700;
    const left = window.screenX + (window.outerWidth - w) / 2;
    const top = window.screenY + (window.outerHeight - h) / 2;
    window.open(
      `/api/oauth/${name}/start`,
      "oauth",
      `width=${w},height=${h},left=${left},top=${top}`,
    );
  }

  return (
    <div className="h-full overflow-y-auto debug-scroll space-y-8">
      {/* Services */}
      <section>
        <SectionHeader title="Services" count={providers.length} isDark={isDark} />
        {!loaded ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className={`h-20 rounded-xl border ${cardBg} shimmer`}
              />
            ))}
          </div>
        ) : providers.length === 0 ? (
          <p className={`text-sm py-6 ${muted}`}>No providers configured.</p>
        ) : (
          <div className="grid gap-3">
            {providers.map((p) => {
              const myConns = connections.filter((c: any) => c.service === p.name);
              return (
                <div
                  key={p.name}
                  className={`border rounded-xl px-4 py-3 fade-in ${cardBg}`}
                >
                  <div className="flex items-center gap-4">
                    <IntegrationLogo raw={p.name} size={32} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-sm font-medium ${
                            isDark ? "text-slate-200" : "text-slate-800"
                          }`}
                        >
                          {humanize(p.name)}
                        </span>
                      </div>
                      <span className={`text-xs ${muted}`}>
                        {p.scopes.slice(0, 2).join(", ")}
                        {p.scopes.length > 2 && `  +${p.scopes.length - 2} more`}
                      </span>
                    </div>
                    <button
                      onClick={() => openOAuth(p.name)}
                      disabled={!p.configured}
                      className={`px-3 py-1.5 text-xs rounded-md transition-colors shrink-0 ${
                        p.configured
                          ? "bg-sky-600 hover:bg-sky-500 text-white"
                          : isDark
                            ? "bg-slate-800 text-slate-600 cursor-not-allowed"
                            : "bg-slate-200 text-slate-400 cursor-not-allowed"
                      }`}
                    >
                      {myConns.length > 0 ? "+ Add" : "Connect"}
                    </button>
                  </div>

                  {!p.configured && (
                    <div
                      className={`mt-2 text-xs ${
                        isDark ? "text-amber-500/70" : "text-amber-700/80"
                      }`}
                    >
                      Set {p.name.toUpperCase()}_CLIENT_ID + _CLIENT_SECRET in .env.local
                    </div>
                  )}

                  {myConns.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {myConns.map((conn: any) => {
                        const status =
                          STATUS_COLORS[conn.status] ?? STATUS_COLORS.revoked;
                        return (
                          <div
                            key={conn._id}
                            className={`flex items-center justify-between rounded-lg px-3 py-2 ${
                              isDark ? "bg-slate-800/50" : "bg-slate-50"
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0 flex-1">
                              <span
                                className={`w-1.5 h-1.5 rounded-full shrink-0 ${status.dot}`}
                              />
                              <span
                                className={`text-sm truncate ${
                                  isDark ? "text-slate-300" : "text-slate-700"
                                }`}
                              >
                                {conn.accountLabel ?? conn.connectionId}
                              </span>
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${status.badge}`}
                              >
                                {status.label}
                              </span>
                              {conn.tokenExpiresAt && (
                                <span className={`text-[10px] mono ${muted}`}>
                                  exp {new Date(conn.tokenExpiresAt).toLocaleDateString()}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className={`mt-2 text-[10px] mono ${muted} truncate`}>
                    Redirect URI: {p.redirectUri}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Environment-driven integrations (listed in registry.ts) */}
      <section>
        <SectionHeader
          title="Integrations"
          count={0}
          isDark={isDark}
          hint="Enabled by uncommenting in server/integrations/registry.ts"
        />
        <p className={`text-xs ${muted}`}>
          Gmail, Google Calendar, Notion, and Slack ship disabled. See each
          folder's README under <code>/integrations/</code> for how to enable
          them and which env vars or OAuth flow they need.
        </p>
      </section>
    </div>
  );
}

function humanize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/-/g, " ");
}

function SectionHeader({
  title,
  count,
  hint,
  isDark,
}: {
  title: string;
  count: number;
  hint?: string;
  isDark: boolean;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <h2
        className={`text-xs font-semibold uppercase tracking-wider ${
          isDark ? "text-slate-500" : "text-slate-400"
        }`}
      >
        {title}
      </h2>
      {count > 0 && (
        <span
          className={`text-xs mono font-medium ${
            isDark ? "text-slate-600" : "text-slate-300"
          }`}
        >
          {count}
        </span>
      )}
      {hint && (
        <span className={`text-[10px] ${isDark ? "text-slate-600" : "text-slate-400"}`}>
          {hint}
        </span>
      )}
    </div>
  );
}
