import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../api/client";
import { useSimulatedProgress, AGENT_STEPS } from "../hooks/useSSE";

const LOG = "[ResultsPage]";

const TABS = [
  { label: "Gap Analysis",     icon: "📊" },
  { label: "Tailored Bullets", icon: "✏️"  },
  { label: "Cover Letter",     icon: "✉️"  },
  { label: "Interview Q&A",   icon: "🎤" },
];

/* ── Tiny reusable copy button ─────────────────────────────── */
function CopyButton({ text, label = "Copy" }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch((err) => {
      console.error("[CopyButton] Clipboard write failed:", err);
    });
  };
  return (
    <button className={`res-copy-btn${copied ? " res-copy-btn--done" : ""}`} onClick={copy}>
      {copied ? (
        <><span className="res-copy-icon">✓</span> Copied</>
      ) : (
        <><span className="res-copy-icon">⎘</span> {label}</>
      )}
    </button>
  );
}

/* ── SVG match ring ────────────────────────────────────────── */
function MatchRing({ pct, size = 96, stroke = 7 }) {
  const r    = (size - stroke * 2) / 2;
  const circ = 2 * Math.PI * r;
  const fill = ((pct || 0) / 100) * circ;
  const color = pct >= 65 ? "#10b981" : pct >= 40 ? "#f59e0b" : "#f87171";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#1e2e45" strokeWidth={stroke} />
      <circle
        cx={size/2} cy={size/2} r={r} fill="none"
        stroke={color} strokeWidth={stroke}
        strokeDasharray={`${fill} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`}
        style={{ transition: "stroke-dasharray 0.8s ease" }}
      />
      <text x={size/2} y={size/2 + 5} textAnchor="middle" fontSize={size * 0.2} fontWeight="700" fill={color}>
        {Math.round(pct || 0)}%
      </text>
    </svg>
  );
}

/* ── Skill chip ────────────────────────────────────────────── */
function Chip({ label, variant }) {
  return <span className={`skill-chip skill-chip--${variant}`}>{label}</span>;
}

/* ── Render **bold** markdown as <strong> ───────────────────── */
function renderBold(text) {
  if (!text || !text.includes("**")) return text;
  return text.split(/\*\*(.+?)\*\*/g).map((part, i) =>
    i % 2 === 1 ? <strong key={i}>{part}</strong> : part
  );
}

/* ═══════════════════════════════════════════════════════════ */
export default function ResultsPage() {
  const { id } = useParams();
  const [app, setApp]           = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [tab, setTab]           = useState(0);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState("");
  const [reanalyzing, setReanalyzing]     = useState(false);
  const [reanalyzeDone, setReanalyzeDone] = useState(false);
  const [reanalyzeError, setReanalyzeError] = useState("");
  const { currentStep, progress } = useSimulatedProgress(reanalyzing, reanalyzeDone);
  const [reanalyzeModal, setReanalyzeModal] = useState(false);
  const [newResumeFile, setNewResumeFile]   = useState(null);
  const [newResumeText, setNewResumeText]   = useState("");
  const [editedBullets, setEditedBullets] = useState({});
  const [editingIdx, setEditingIdx]       = useState(null);
  const [chatOpen, setChatOpen]       = useState(false);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [messages, setMessages]       = useState([]);
  const [question, setQuestion]       = useState("");
  const [coachLoading, setCoachLoading] = useState(false);
  const chatBottomRef = useRef(null);

  useEffect(() => {
    const load = async () => {
      console.log(`${LOG} Loading application id=${id}`);
      try {
        const res = await api.get(`/applications/${id}`);
        setApp(res.data);
        if (res.data.analyses?.length > 0) {
          const latest = res.data.analyses[res.data.analyses.length - 1];
          setAnalysis(latest);
          console.log(`${LOG} Loaded analysis id=${latest.id}, match=${latest.match_percentage}%`);
        } else {
          console.warn(`${LOG} No analyses found for application id=${id}`);
        }
      } catch (err) {
        const msg = err.response?.data?.detail || "Could not load results.";
        console.error(`${LOG} Failed to load application id=${id}:`, msg, err);
        setError(msg);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  if (loading) return <div className="center-msg">Loading results…</div>;
  if (error)   return <div className="center-msg error">{error}</div>;
  if (!analysis) return <div className="center-msg">No analysis found for this application.</div>;

  const downloadText = (text, filename) => {
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };

  const getBulletText = (b, i) => editedBullets[i] ?? b.tailored;

  const gap      = analysis.gap_analysis    || {};
  const bullets  = (analysis.tailored_bullets || []).filter(b => b.tailored?.trim());
  const qa       = analysis.interview_qa    || [];
  const matchPct = gap.match_percentage ?? null;

  /* handlers ── unchanged logic, same as before */
  const handleNewResumePDF = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    console.log(`${LOG} New resume PDF selected: ${file.name}`);
    setNewResumeFile(file);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await api.post("/resume/extract", form, { headers: { "Content-Type": "multipart/form-data" } });
      console.log(`${LOG} New resume extracted: ${res.data.text?.length ?? 0} chars`);
      setNewResumeText(res.data.text);
    } catch (err) {
      console.error(`${LOG} Failed to extract new resume PDF:`, err.response?.data?.detail || err.message, err);
      setNewResumeText("");
    }
  };

  const reanalyze = async () => {
    if (reanalyzing) return;
    console.log(`${LOG} Starting re-analysis for app id=${id}`);
    setReanalyzing(true);
    setReanalyzeModal(false);
    try {
      if (newResumeText.trim()) {
        await api.patch(`/applications/${id}/resume`, { resume_text: newResumeText });
      }
      await api.post("/analyze", { application_id: Number(id) });
      console.log(`${LOG} Re-analysis pipeline completed`);
      setReanalyzeDone(true);
      await new Promise((r) => setTimeout(r, 800));
      const res = await api.get(`/applications/${id}`);
      setApp(res.data);
      if (res.data.analyses?.length > 0) {
        const latest = res.data.analyses[res.data.analyses.length - 1];
        setAnalysis(latest);
        console.log(`${LOG} Re-analysis saved: match=${latest.match_percentage}%`);
      }
    } catch (err) {
      console.error(`${LOG} Re-analysis failed:`, err.response?.data?.detail || err.message, err);
      setReanalyzeError(err.response?.data?.detail || "Re-analysis failed. Please try again.");
    } finally {
      setReanalyzing(false);
      setReanalyzeDone(false);
      setNewResumeFile(null);
      setNewResumeText("");
    }
  };

  const askCoach = async (e) => {
    e.preventDefault();
    if (!question.trim() || coachLoading) return;
    const q = question.trim();
    console.log(`${LOG} Coach question for app id=${id}:`, q);
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setQuestion("");
    setCoachLoading(true);
    try {
      const res = await api.post("/coach", { application_id: Number(id), question: q });
      console.log(`${LOG} Coach answer received`);
      setMessages((prev) => [...prev, { role: "coach", text: res.data.answer }]);
    } catch (err) {
      console.error(`${LOG} Coach failed:`, err.response?.data?.detail || err.message, err);
      setMessages((prev) => [...prev, { role: "coach", text: "Sorry, I couldn't answer that right now. Try again." }]);
    } finally {
      setCoachLoading(false);
      setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  /* ── render ─────────────────────────────────────────────── */
  return (
    <div className="rp-page">

      {/* ══ HEADER ══════════════════════════════════════════ */}
      <div className="rp-header">
        <div className="rp-header-left">
          <div className="rp-breadcrumb">
            <Link to="/tracker" className="rp-back-link">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6"/>
              </svg>
              All Applications
            </Link>
          </div>
          <h1 className="rp-title">{app.job_title}</h1>
          <div className="rp-meta">
            <span className="rp-company">{app.company}</span>
            <span className="rp-status-pill">Analyzed</span>
          </div>
        </div>

        <div className="rp-header-right">
          <div className="rp-header-actions">
            <button
              className="rp-btn-reanalyze"
              onClick={() => { setReanalyzeError(""); setReanalyzeModal(true); }}
              disabled={reanalyzing}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
              {reanalyzing ? "Re-analyzing…" : "Re-analyze"}
            </button>
            {reanalyzeError && (
              <div className="error" style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>{reanalyzeError}</div>
            )}
          </div>
        </div>
      </div>

      {/* ══ TABS ════════════════════════════════════════════ */}
      <div className="rp-tabs">
        {TABS.map((t, i) => (
          <button
            key={t.label}
            className={`rp-tab${tab === i ? " rp-tab--active" : ""}`}
            onClick={() => { console.log(`${LOG} Tab: ${t.label}`); setTab(i); }}
          >
            <span className="rp-tab-icon">{t.icon}</span>
            <span className="rp-tab-label">{t.label}</span>
          </button>
        ))}
      </div>

      {/* ══ CONTENT ═════════════════════════════════════════ */}
      <div key={tab} className="rp-content tab-panel-fade">

        {/* ── GAP ANALYSIS ── */}
        {tab === 0 && (
          <div className="rp-gap">
            {/* Top: ring + summary */}
            <div className="rp-gap-top">
              <div className="rp-gap-ring-wrap">
                <MatchRing pct={matchPct ?? 0} size={120} stroke={8} />
                <div className="rp-gap-ring-label">Overall Match</div>
              </div>
              {gap.summary && (
                <div className="rp-gap-summary-box">
                  <div className="rp-gap-summary-eyebrow">AI Summary</div>
                  <p className="rp-gap-summary-text">{gap.summary}</p>
                </div>
              )}
            </div>

            {/* Skills grid */}
            <div className="rp-skills-grid">
              <div className="rp-skills-col">
                <div className="rp-skills-col-header rp-skills-col-header--match">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  Matching Skills
                  <span className="rp-skills-count">{(gap.matching_skills||[]).length}</span>
                </div>
                <div className="rp-chips-wrap">
                  {(gap.matching_skills || []).length === 0
                    ? <span className="rp-empty-note">None detected</span>
                    : (gap.matching_skills || []).map(s => <Chip key={s} label={s} variant="match" />)}
                </div>
              </div>

              <div className="rp-skills-col">
                <div className="rp-skills-col-header rp-skills-col-header--miss">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                  Missing Skills
                  <span className="rp-skills-count">{(gap.missing_skills||[]).length}</span>
                </div>
                <div className="rp-chips-wrap">
                  {(gap.missing_skills || []).length === 0
                    ? <span className="rp-empty-note">None — great fit!</span>
                    : (gap.missing_skills || []).map(s => <Chip key={s} label={s} variant="miss" />)}
                </div>
              </div>

              {(gap.partial_matches || []).length > 0 && (
                <div className="rp-skills-col rp-skills-col--full">
                  <div className="rp-skills-col-header rp-skills-col-header--partial">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    Partial Matches
                    <span className="rp-skills-count">{gap.partial_matches.length}</span>
                  </div>
                  <div className="rp-chips-wrap">
                    {gap.partial_matches.map(s => <Chip key={s} label={s} variant="partial" />)}
                  </div>
                </div>
              )}
            </div>

            {/* Formatting tips */}
            {(gap.formatting_tips || []).length > 0 && (
              <div className="rp-tips">
                <div className="rp-tips-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  Resume Formatting
                </div>
                <ol className="rp-tips-list">
                  {gap.formatting_tips.map((tip, i) => <li key={i}>{tip}</li>)}
                </ol>
              </div>
            )}
          </div>
        )}

        {/* ── TAILORED BULLETS ── */}
        {tab === 1 && (
          <div className="rp-bullets">
            <div className="rp-section-toolbar">
              <div>
                <div className="rp-section-title">Tailored Resume Bullets</div>
                <div className="rp-section-sub">{bullets.length} bullet{bullets.length !== 1 ? "s" : ""} rewritten to match this role</div>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <CopyButton
                  text={bullets.map((b, i) => getBulletText(b, i)).join("\n\n")}
                  label="Copy All"
                />
                <button
                  className="res-copy-btn"
                  onClick={() => downloadText(bullets.map((b, i) => `• ${getBulletText(b, i)}`).join("\n\n"), "tailored-bullets.txt")}
                >
                  <span className="res-copy-icon">↓</span> Download
                </button>
              </div>
            </div>

            {bullets.length === 0 && (
              <div className="rp-empty-state">
                <div className="rp-empty-icon">✏️</div>
                <p>No tailored bullets — the resume may not have enough experience bullet points to rewrite.</p>
              </div>
            )}

            {bullets.map((b, i) => (
              <div key={i} className="rp-bullet-card">
                <div className="rp-bullet-num">#{i + 1}</div>
                <div className="rp-bullet-body">
                  <div className="rp-bullet-row rp-bullet-row--before">
                    <span className="rp-bullet-badge rp-bullet-badge--before">Before</span>
                    <p className="rp-bullet-text rp-bullet-text--before">{renderBold(b.original)}</p>
                  </div>
                  <div className="rp-bullet-arrow">↓</div>
                  <div className="rp-bullet-row rp-bullet-row--after">
                    <span className="rp-bullet-badge rp-bullet-badge--after">After</span>
                    {editingIdx === i ? (
                      <textarea
                        className="rp-bullet-edit-area"
                        value={getBulletText(b, i)}
                        onChange={(e) => setEditedBullets(prev => ({ ...prev, [i]: e.target.value }))}
                        onBlur={() => setEditingIdx(null)}
                        autoFocus
                      />
                    ) : (
                      <p
                        className="rp-bullet-text rp-bullet-text--after rp-bullet-editable"
                        onClick={() => setEditingIdx(i)}
                        title="Click to edit"
                      >
                        {renderBold(getBulletText(b, i))}
                        <span className="rp-bullet-edit-hint">✎</span>
                      </p>
                    )}
                    <CopyButton text={getBulletText(b, i)} />
                  </div>
                  {b.reasoning && (
                    <div className="rp-bullet-why">
                      <span className="rp-bullet-why-label">Why:</span> {renderBold(b.reasoning)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── COVER LETTER ── */}
        {tab === 2 && (
          <div className="rp-cover">
            <div className="rp-section-toolbar">
              <div>
                <div className="rp-section-title">Cover Letter</div>
                <div className="rp-section-sub">Personalized for {app.job_title} at {app.company}</div>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <CopyButton text={analysis.cover_letter} label="Copy Letter" />
                <button
                  className="res-copy-btn"
                  onClick={() => downloadText(analysis.cover_letter, `cover-letter-${app.company.replace(/\s+/g, "-")}.txt`)}
                >
                  <span className="res-copy-icon">↓</span> Download
                </button>
              </div>
            </div>
            <div className="rp-cover-doc">
              <pre className="rp-cover-text">{analysis.cover_letter}</pre>
            </div>
          </div>
        )}

        {/* ── INTERVIEW Q&A ── */}
        {tab === 3 && (
          <div className="rp-qa">
            <div className="rp-section-toolbar">
              <div>
                <div className="rp-section-title">Interview Preparation</div>
                <div className="rp-section-sub">{qa.length} likely question{qa.length !== 1 ? "s" : ""} with model answers</div>
              </div>
              <CopyButton
                text={qa.map((item, i) => `Q${i+1}: ${item.question}\n\nA: ${item.model_answer}`).join("\n\n---\n\n")}
                label="Copy All Q&A"
              />
            </div>

            {qa.length === 0 && (
              <div className="rp-empty-state">
                <div className="rp-empty-icon">🎤</div>
                <p>No interview questions generated.</p>
              </div>
            )}

            {qa.map((item, i) => (
              <div key={i} className="rp-qa-card">
                <div className="rp-qa-header">
                  <span className="rp-qa-num">Q{i + 1}</span>
                  {item.type && (
                    <span className={`rp-qa-type rp-qa-type--${item.type?.toLowerCase().replace(/\s+/g,"-")}`}>
                      {item.type}
                    </span>
                  )}
                  <CopyButton text={item.model_answer} label="Copy Answer" />
                </div>
                <p className="rp-qa-question">{item.question}</p>
                <div className="rp-qa-answer-wrap">
                  <div className="rp-qa-answer-label">Model Answer</div>
                  <p className="rp-qa-answer">{item.model_answer}</p>
                </div>
              </div>
            ))}
          </div>
        )}

      </div>

      {/* ══ RE-ANALYZE OVERLAY ══════════════════════════════ */}
      {reanalyzing && (
        <div className="reanalyze-overlay">
          <div className="stream-card" style={{ maxWidth: "520px", width: "100%" }}>
            <h2 className={reanalyzeDone ? "stream-title done" : "stream-title"}>
              {reanalyzeDone ? "Analysis complete!" : "Re-analyzing your application..."}
            </h2>
            <div className="progress-wrap">
              <div className="progress-bar-track">
                <div
                  className={`progress-bar-fill${reanalyzeDone ? " finishing" : ""}`}
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </div>
              <span className={`progress-pct${reanalyzeDone ? " done" : ""}`}>
                {Math.round(progress * 100)}%
              </span>
            </div>
            <ul className="step-list">
              {AGENT_STEPS.map((s, i) => {
                const isDone   = i < currentStep;
                const isActive = i === currentStep && !reanalyzeDone;
                return (
                  <li key={s.key} className={isDone ? "done" : isActive ? "active" : ""}>
                    <span className="step-icon">{s.icon}</span>
                    <span className="step-label">{s.label}</span>
                    <span className="step-status">
                      {isDone ? "✓" : isActive ? <span className="pulse-dot" /> : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}

      {/* ══ RE-ANALYZE MODAL ════════════════════════════════ */}
      {reanalyzeModal && (
        <div className="modal-overlay" onClick={() => setReanalyzeModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>Re-analyze Application</h3>
            <p className="modal-sub">Optionally upload an updated resume, or re-run with the existing one.</p>
            <label className={`upload-zone2 upload-zone2--modal${newResumeFile ? " upload-zone2--done" : ""}`} style={{ marginTop: "1rem" }}>
              <input type="file" accept="application/pdf" onChange={handleNewResumePDF} style={{ display: "none" }} />
              {newResumeFile ? (
                <div className="uz2-body">
                  <div className="uz2-icon uz2-icon--done">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </div>
                  <div className="uz2-text">
                    <span className="uz2-title">{newResumeFile.name}</span>
                    <span className="uz2-sub">{newResumeText.length} chars extracted</span>
                  </div>
                </div>
              ) : (
                <div className="uz2-idle">
                  <span className="uz2-idle-title">Upload new resume (optional)</span>
                  <span className="uz2-idle-sub">Leave blank to re-run with existing resume</span>
                </div>
              )}
            </label>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setReanalyzeModal(false)}>Cancel</button>
              <button className="btn-primary" onClick={reanalyze}>
                {newResumeFile ? "Update & Re-analyze" : "Re-analyze"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══ CAREER COACH FAB + PANEL ════════════════════════ */}
      {!chatOpen && (
        <button className="coach-fab" onClick={() => setChatOpen(true)} title="Career Coach">
          🎤 <span className="coach-fab-label">Career Coach</span>
        </button>
      )}

      {chatOpen && (
        <div className={`coach-panel${chatExpanded ? " coach-panel--expanded" : ""}`}>
          <div className="coach-panel-header">
            <div>
              <span>🎤 Career Coach</span>
              <span className="coach-panel-sub">Ask anything about this application</span>
            </div>
            <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
              <button className="coach-expand-btn" onClick={() => setChatExpanded(e => !e)} title={chatExpanded ? "Collapse" : "Expand"}>
                {chatExpanded ? "⊡" : "⊞"}
              </button>
              <button className="coach-expand-btn" onClick={() => { setChatOpen(false); setChatExpanded(false); }} title="Close">
                ✕
              </button>
            </div>
          </div>
          <div className="coach-messages">
            {messages.length === 0 && (
              <div className="coach-empty">
                <p>Ask me anything about your application — interview tips, how to address skill gaps, cover letter advice, salary negotiation, or anything else.</p>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`coach-msg coach-msg--${m.role}`}>{m.text}</div>
            ))}
            {coachLoading && (
              <div className="coach-msg coach-msg--coach coach-typing">
                <span /><span /><span />
              </div>
            )}
            <div ref={chatBottomRef} />
          </div>
          <form className="coach-input-row" onSubmit={askCoach}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. How do I address the missing skills?"
              disabled={coachLoading}
            />
            <button type="submit" className="coach-send" disabled={coachLoading || !question.trim()}>↑</button>
          </form>
        </div>
      )}
    </div>
  );
}