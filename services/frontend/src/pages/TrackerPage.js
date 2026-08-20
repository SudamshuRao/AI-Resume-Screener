import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";

const LOG = "[TrackerPage]";

function guessDomain(company) {
  if (!company) return null;
  const cleaned = company
    .toLowerCase()
    .replace(/\b(inc|corp|llc|ltd|co|company|group|technologies|solutions|services|international|a)\b\.?/g, "")
    .replace(/[^a-z0-9]/g, "")
    .trim();
  if (!cleaned) return null;
  return cleaned + ".com";
}

function CompanyAvatar({ company }) {
  const [logoOk, setLogoOk] = useState(null);
  const domain   = guessDomain(company);
  const initials = (company || "?").slice(0, 2).toUpperCase();
  const logoUrl  = domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=128` : null;

  const handleLoad = (e) => {
    setLogoOk(e.target.naturalWidth > 16);
  };

  return (
    <div className={`app-card-avatar${logoOk ? " app-card-avatar--logo" : ""}`}>
      {logoUrl && (
        <img
          src={logoUrl}
          alt={company}
          onLoad={handleLoad}
          onError={() => setLogoOk(false)}
          style={{ display: logoOk ? "block" : "none", width: "26px", height: "26px", objectFit: "contain" }}
        />
      )}
      {!logoOk && initials}
    </div>
  );
}

const STATUS_META = {
  pending:  { color: "#f59e0b", bg: "rgba(245,158,11,0.12)",  label: "Pending"  },
  analyzed: { color: "#38bdf8", bg: "rgba(56,189,248,0.12)",  label: "Analyzed" },
  applied:  { color: "#10b981", bg: "rgba(16,185,129,0.12)",  label: "Applied"  },
  rejected: { color: "#ef4444", bg: "rgba(239,68,68,0.12)",   label: "Rejected" },
  offered:  { color: "#8b5cf6", bg: "rgba(139,92,246,0.12)",  label: "Offered"  },
};

const HAS_RESULTS = new Set(["analyzed", "applied", "rejected", "offered"]);

const FILTERS = [
  { value: "",         label: "All"      },
  { value: "pending",  label: "Pending"  },
  { value: "analyzed", label: "Analyzed" },
  { value: "applied",  label: "Applied"  },
  { value: "rejected", label: "Rejected" },
  { value: "offered",  label: "Offered"  },
];

function MatchRing({ pct }) {
  const r     = 22;
  const circ  = 2 * Math.PI * r;
  const fill  = ((pct || 0) / 100) * circ;
  const color = pct >= 60 ? "#10b981" : pct >= 35 ? "#f59e0b" : "#ef4444";
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" style={{ flexShrink: 0 }}>
      <circle cx="28" cy="28" r={r} fill="none" stroke="#1e293b" strokeWidth="5" />
      <circle
        cx="28" cy="28" r={r} fill="none"
        stroke={color} strokeWidth="5"
        strokeDasharray={`${fill} ${circ}`}
        strokeLinecap="round"
        transform="rotate(-90 28 28)"
        style={{ transition: "stroke-dasharray 0.6s ease" }}
      />
      <text x="28" y="33" textAnchor="middle" fontSize="11" fontWeight="700" fill={color}>
        {Math.round(pct || 0)}%
      </text>
    </svg>
  );
}

export default function TrackerPage() {
  const [apps, setApps]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter]   = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    const load = async () => {
      console.log(`${LOG} Loading applications (filter="${filter}")`);
      try {
        const params = filter ? { status: filter } : {};
        const res = await api.get("/applications", { params });
        setApps(res.data);
        console.log(`${LOG} Loaded ${res.data.length} applications`);
      } catch (err) {
        const msg = err.response?.data?.detail || "Failed to load applications.";
        console.error(`${LOG} Failed to load applications:`, msg, err);
        setActionError(msg);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [filter]);

  const updateStatus = async (id, newStatus) => {
    console.log(`${LOG} Updating app id=${id} status → "${newStatus}"`);
    setActionError("");
    try {
      await api.patch(`/applications/${id}/status`, { status: newStatus });
      setApps((prev) => prev.map((a) => (a.id === id ? { ...a, status: newStatus } : a)));
      console.log(`${LOG} Status updated: app id=${id} is now "${newStatus}"`);
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to update status.";
      console.error(`${LOG} Failed to update status for app id=${id}:`, msg, err);
      setActionError(msg);
    }
  };

  const deleteApp = async (id) => {
    if (!window.confirm("Delete this application? This cannot be undone.")) return;
    console.log(`${LOG} Deleting app id=${id}`);
    setActionError("");
    try {
      await api.delete(`/applications/${id}`);
      setApps((prev) => prev.filter((a) => a.id !== id));
      console.log(`${LOG} Deleted app id=${id}`);
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to delete application.";
      console.error(`${LOG} Failed to delete app id=${id}:`, msg, err);
      setActionError(msg);
    }
  };

  const counts = apps.reduce((acc, a) => {
    acc[a.status] = (acc[a.status] || 0) + 1;
    return acc;
  }, {});

  if (loading) return <div className="center-msg">Loading...</div>;

  return (
    <div className="tracker-page">
      {/* Header */}
      <div className="tracker-header">
        <div>
          <h2>Job Applications</h2>
          <p className="tracker-sub">{apps.length} application{apps.length !== 1 ? "s" : ""} tracked</p>
        </div>
        {apps.length > 0 && <Link to="/analyze" className="btn-primary">+ New Analysis</Link>}
      </div>

      {/* Inline action error banner */}
      {actionError && (
        <div className="error-banner">
          {actionError}
          <button className="error-banner-close" onClick={() => setActionError("")}>✕</button>
        </div>
      )}

      {/* Stats row */}
      {apps.length > 0 && (
        <div className="tracker-stats">
          {[
            { key: "analyzed", label: "Analyzed",  icon: "📊" },
            { key: "applied",  label: "Applied",   icon: "📤" },
            { key: "offered",  label: "Offered",   icon: "🎉" },
            { key: "rejected", label: "Rejected",  icon: "✗"  },
          ].map(({ key, label, icon }) => (
            <div key={key} className="stat-card" style={{ borderColor: STATUS_META[key].color }}>
              <span className="stat-icon">{icon}</span>
              <span className="stat-count" style={{ color: STATUS_META[key].color }}>{counts[key] || 0}</span>
              <span className="stat-label">{label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Cards / Empty state */}
      {apps.length === 0 ? (
        <div className="welcome-empty">
          <div className="welcome-hero">
            <div className="welcome-logo">HireIQ</div>
            <h3 className="welcome-title">Welcome! Let's land your next role.</h3>
            <p className="welcome-sub">
              Paste a job description and your resume — HireIQ's AI agents will analyse
              your fit, rewrite your bullets, generate a cover letter, and prep you for
              interviews in under a minute.
            </p>
            <Link to="/analyze" className="btn-primary welcome-cta">
              Analyse your first application →
            </Link>
          </div>

          <div className="welcome-features">
            {[
              { icon: "📊", title: "Gap Analysis",      desc: "See exactly which skills you're missing for the role." },
              { icon: "✏️",  title: "Tailored Bullets",  desc: "Your resume bullets rewritten to match the JD."       },
              { icon: "✉️",  title: "Cover Letter",      desc: "A personalised cover letter in seconds."              },
              { icon: "🎤", title: "Interview Prep",    desc: "Likely questions with model answers for your resume." },
            ].map((f) => (
              <div key={f.title} className="welcome-feat">
                <span className="welcome-feat-icon">{f.icon}</span>
                <div>
                  <strong>{f.title}</strong>
                  <p>{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="app-cards">
          {apps.map((app, i) => {
            const meta   = STATUS_META[app.status] || STATUS_META.pending;
            const latest = app.analyses?.[app.analyses.length - 1];
            const pct    = latest?.match_percentage ?? null;

            return (
              <div key={app.id} className="app-card" style={{ animationDelay: `${i * 0.06}s` }}>
                {/* Card top: avatar + title/company */}
                <div className="app-card-top">
                  <CompanyAvatar company={app.company} />
                  <div className="app-card-info">
                    <div className="app-card-title">
                      {HAS_RESULTS.has(app.status)
                        ? <Link to={`/results/${app.id}`} className="app-card-link">{app.job_title}</Link>
                        : <span>{app.job_title}</span>}
                    </div>
                    <div className="app-card-company">{app.company}</div>
                  </div>
                  {pct !== null && <MatchRing pct={pct} />}
                </div>

                {/* Card bottom: status badge + dropdown + button */}
                <div className="app-card-bottom">
                  <span className="status-badge" style={{ color: meta.color, background: meta.bg }}>
                    {meta.label}
                  </span>

                  <select
                    className="applied-select"
                    value={["applied","rejected","offered"].includes(app.status) ? app.status : "not_applied"}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "not_applied") {
                        if (HAS_RESULTS.has(app.status)) updateStatus(app.id, "analyzed");
                      } else {
                        updateStatus(app.id, val);
                      }
                    }}
                    disabled={app.status === "pending"}
                  >
                    <option value="not_applied">Not Applied</option>
                    <option value="applied">Applied</option>
                    <option value="rejected">Rejected</option>
                    <option value="offered">Offered 🎉</option>
                  </select>

                  {HAS_RESULTS.has(app.status) && (
                    <Link to={`/results/${app.id}`} className="btn-secondary btn-sm">
                      View Results
                    </Link>
                  )}

                  <button
                    className="btn-delete"
                    onClick={() => deleteApp(app.id)}
                    title="Delete application"
                  >
                    ✕
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}