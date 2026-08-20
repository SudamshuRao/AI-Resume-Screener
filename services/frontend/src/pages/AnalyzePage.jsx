import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import { AGENT_STEPS } from "../hooks/useSSE";

const LOG = "[AnalyzePage]";
const JD_MIN_CHARS = 80;

export default function AnalyzePage() {
  const navigate = useNavigate();
  const [jobTitle, setJobTitle]           = useState("");
  const [company, setCompany]             = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [resumeFile, setResumeFile]       = useState(null);
  const [resumeText, setResumeText]       = useState("");
  const [step, setStep]                   = useState("form"); // form | streaming
  const [applicationId, setApplicationId] = useState(null);
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [currentStep, setCurrentStep]     = useState(0);
  const [error, setError]                 = useState("");
  const [pdfFailed, setPdfFailed]         = useState(false);
  const [pdfExtracting, setPdfExtracting] = useState(false);
  const [companyData, setCompanyData]     = useState(null);
  const [revealedText, setRevealedText]   = useState("");
  const [revealedChips, setRevealedChips] = useState([]);
  const [revealedCulture, setRevealedCulture] = useState("");
  const [revealedWhy, setRevealedWhy]     = useState("");

  // Field-level validation errors
  const [fieldErrors, setFieldErrors] = useState({});
  const [touched, setTouched]         = useState({});

  const progress = analysisComplete ? 1 : currentStep / AGENT_STEPS.length;

  const revealRef = useRef({ timer: null });

  useEffect(() => {
    if (!companyData?.what_they_do) return;

    setRevealedText("");
    setRevealedChips([]);
    setRevealedCulture("");
    setRevealedWhy("");

    const revealWords = (text, setter, delay, onDone) => {
      const words = text.split(" ");
      let i = 0;
      const tick = () => {
        i += 1;
        setter(words.slice(0, i).join(" "));
        if (i < words.length) {
          revealRef.current.timer = setTimeout(tick, delay);
        } else {
          onDone();
        }
      };
      revealRef.current.timer = setTimeout(tick, delay);
    };

    const revealItems = (items, setter, delay, onDone) => {
      if (!items.length) { onDone(); return; }
      items.forEach((item, ci) => {
        setTimeout(() => setter((prev) => [...prev, item]), ci * delay);
      });
      setTimeout(onDone, items.length * delay + 400);
    };

    revealWords(companyData.what_they_do, setRevealedText, 120, () => {
      revealItems(companyData.recent_projects || [], setRevealedChips, 500, () => {
        const culture = companyData.culture_notes || "";
        const why = companyData.why_apply || "";
        if (culture) {
          revealWords(culture, setRevealedCulture, 120, () => {
            if (why) revealWords(why, setRevealedWhy, 120, () => {});
          });
        } else if (why) {
          revealWords(why, setRevealedWhy, 120, () => {});
        }
      });
    });

    return () => clearTimeout(revealRef.current.timer);
  }, [companyData]);

  useEffect(() => {
    if (analysisComplete && currentStep === AGENT_STEPS.length && applicationId) {
      console.log(`${LOG} Analysis complete — navigating to /results/${applicationId}`);
      const t = setTimeout(() => navigate(`/results/${applicationId}`), 700);
      return () => clearTimeout(t);
    }
  }, [analysisComplete, currentStep, applicationId, navigate]);

  const validateFields = () => {
    const errs = {};
    if (!jobTitle.trim())   errs.jobTitle = "Job title is required.";
    if (!company.trim())    errs.company  = "Company name is required.";
    if (!jobDescription.trim()) {
      errs.jobDescription = "Job description is required.";
    } else if (jobDescription.trim().length < JD_MIN_CHARS) {
      errs.jobDescription = `Please paste the full job description (at least ${JD_MIN_CHARS} characters).`;
    }
    if (!resumeText.trim()) errs.resume   = "Please upload your resume PDF or paste the text.";
    return errs;
  };

  const handleBlur = (field) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    setFieldErrors(validateFields());
  };

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const MAX_MB = 5;
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`PDF must be under ${MAX_MB} MB.`);
      return;
    }
    console.log(`${LOG} PDF selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`);
    setResumeFile(file);
    setPdfFailed(false);
    setPdfExtracting(true);
    setResumeText("");
    setError("");

    const form = new FormData();
    form.append("file", file);
    try {
      const res = await api.post("/resume/extract", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const chars = res.data.text?.length ?? 0;
      console.log(`${LOG} PDF extracted: ${chars} chars from ${res.data.pages} pages`);
      setResumeText(res.data.text);
      setTouched((prev) => ({ ...prev, resume: true }));
      setFieldErrors((prev) => ({ ...prev, resume: undefined }));
    } catch (err) {
      const msg = err.response?.data?.detail || "Could not extract text from PDF.";
      console.error(`${LOG} PDF extraction failed:`, msg, err);
      setPdfFailed(true);
      setError(msg);
    } finally {
      setPdfExtracting(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");

    // Mark all fields touched
    setTouched({ jobTitle: true, company: true, jobDescription: true, resume: true });
    const errs = validateFields();
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      console.warn(`${LOG} Submit blocked — validation errors:`, errs);
      return;
    }

    console.log(`${LOG} Submitting application: "${jobTitle}" at "${company}"`);

    try {
      const appRes = await api.post("/applications", {
        job_title: jobTitle,
        company,
        job_description: jobDescription,
        resume_text: resumeText,
      });
      const appId = appRes.data.id;
      console.log(`${LOG} Application created: id=${appId}`);
      setApplicationId(appId);
      setStep("streaming");

      // Fire company preview and full analysis in parallel
      console.log(`${LOG} Starting company preview for: "${company}"`);
      api.post("/company-preview", { company, job_description: jobDescription })
        .then((r) => {
          console.log(`${LOG} Company preview received:`, r.data?.company_name);
          setCompanyData(r.data);
        })
        .catch((err) => {
          console.warn(`${LOG} Company preview failed (non-critical):`, err.message);
        });

      console.log(`${LOG} Starting SSE analysis pipeline for app id=${appId}`);
      try {
        const token = localStorage.getItem("token");
        const baseURL = import.meta.env.VITE_API_URL;
        const response = await fetch(`${baseURL}/api/v1/analyze/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ application_id: appId }),
        });
        if (!response.ok) throw new Error(`Stream HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";
          for (const block of blocks) {
            for (const line of block.split("\n")) {
              if (!line.startsWith("data: ")) continue;
              try {
                const event = JSON.parse(line.slice(6));
                if (event.status === "completed") {
                  const idx = AGENT_STEPS.findIndex(s => s.key === event.agent);
                  if (idx !== -1) setCurrentStep(idx + 1);
                } else if (event.status === "saved") {
                  setCurrentStep(AGENT_STEPS.length);
                  setAnalysisComplete(true);
                  return;
                } else if (event.status === "error") {
                  throw new Error(event.detail || "Pipeline error");
                }
              } catch (_) { /* ignore parse errors */ }
            }
          }
        }
      } catch (sseErr) {
        // Fallback to blocking call if SSE fails
        console.warn(`${LOG} SSE failed, falling back to blocking call:`, sseErr.message);
        try {
          await api.post("/analyze", { application_id: appId });
        } catch (fallbackErr) {
          setError("Analysis failed. Please try again.");
          setStep("form");
          return;
        }
      }
      console.log(`${LOG} Analysis pipeline completed for app id=${appId}`);
      setCurrentStep(AGENT_STEPS.length);
      setAnalysisComplete(true);
    } catch (err) {
      const msg = err.response?.data?.detail || "Analysis failed. Please try again.";
      console.error(`${LOG} Analysis submission failed:`, msg, err);
      setError(msg);
      setStep("form");
    }
  };

  const fe = (field) =>
    touched[field] && fieldErrors[field] ? fieldErrors[field] : null;

  if (step === "streaming") {
    const pct = Math.round(progress * 100);
    const isFinishing = pct === 100;

    return (
      <div className="stream-page">
        <div className="stream-card">
          <h2 className={isFinishing ? "stream-title done" : "stream-title"}>
            {isFinishing ? "Analysis complete!" : "Analyzing your application..."}
          </h2>

          <div className="progress-wrap">
            <div className="progress-bar-track">
              <div
                className={`progress-bar-fill${isFinishing ? " finishing" : ""}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className={`progress-pct${isFinishing ? " done" : ""}`}>{pct}%</span>
          </div>

          <ul className="step-list">
            {AGENT_STEPS.map((s, i) => {
              const isDone   = i < currentStep;
              const isActive = i === currentStep && !isFinishing;
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

          {companyData ? (
            <div className="company-preview-card">
              <p className="company-preview-label">While you wait — here's what we found about</p>
              <h3 className="company-preview-name">{companyData.company_name || company}</h3>

              {revealedText && (
                <p className="company-preview-about">
                  {revealedText}
                  {revealedChips.length === 0 && !revealedCulture && <span className="cursor-blink">|</span>}
                </p>
              )}

              {revealedChips.length > 0 && (
                <div className="company-preview-projects">
                  <p className="company-preview-projects-label">What they're working on:</p>
                  <ul className="company-preview-projects-list">
                    {revealedChips.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}

              {revealedCulture && (
                <div className="company-preview-extra">
                  <p className="company-preview-projects-label">Culture &amp; Values</p>
                  <p className="company-preview-extra-text">
                    {revealedCulture}
                    {!revealedWhy && <span className="cursor-blink">|</span>}
                  </p>
                </div>
              )}

              {revealedWhy && (
                <div className="company-preview-extra">
                  <p className="company-preview-projects-label">Why Apply</p>
                  <p className="company-preview-extra-text">
                    {revealedWhy}<span className="cursor-blink">|</span>
                  </p>
                </div>
              )}
            </div>
          ) : (
            <p className="company-preview-loading">Researching {company}...</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="analyze-page">
      <div className="analyze-header">
        <div>
          <h2>New Application Analysis</h2>
          <p className="analyze-sub">Paste the job details and your resume — our AI agents will do the rest.</p>
        </div>
      </div>

      <form onSubmit={submit} className="analyze-form" noValidate>
        {/* Row: Job Title + Company */}
        <div className="analyze-section">
          <div className="row-2">
            <div className="form-field">
              <label>Job Title <span className="req">*</span></label>
              <div className={`icon-input-wrap${fe("jobTitle") ? " icon-input-wrap--invalid" : jobTitle.trim() ? " icon-input-wrap--valid" : ""}`}>
                <span className="icon-input-prefix" aria-hidden="true">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
                  </svg>
                </span>
                <input
                  type="text"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  onBlur={() => handleBlur("jobTitle")}
                  placeholder="e.g. Senior Software Engineer"
                  className="icon-input"
                  autoComplete="off"
                />
                {jobTitle.trim() && !fe("jobTitle") && (
                  <span className="icon-input-check" aria-hidden="true">✓</span>
                )}
              </div>
              {fe("jobTitle") && <span className="field-error">{fe("jobTitle")}</span>}
            </div>
            <div className="form-field">
              <label>Company <span className="req">*</span></label>
              <div className={`icon-input-wrap${fe("company") ? " icon-input-wrap--invalid" : company.trim() ? " icon-input-wrap--valid" : ""}`}>
                <span className="icon-input-prefix" aria-hidden="true">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 21h18M3 7h18M9 21V7m6 14V7M3 7l9-4 9 4"/>
                  </svg>
                </span>
                <input
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  onBlur={() => handleBlur("company")}
                  placeholder="e.g. Google, Stripe, Acme Corp"
                  className="icon-input"
                  autoComplete="organization"
                />
                {company.trim() && !fe("company") && (
                  <span className="icon-input-check" aria-hidden="true">✓</span>
                )}
              </div>
              {fe("company") && <span className="field-error">{fe("company")}</span>}
            </div>
          </div>
        </div>

        {/* Two-column: JD left, Resume right */}
        <div className="analyze-cols">

          {/* ── Job Description ── */}
          <div className={`jd-field-wrap${fe("jobDescription") ? " jd-field-wrap--invalid" : jobDescription.trim() ? " jd-field-wrap--filled" : ""}`}>
            <div className="jd-field-header">
              <span className="jd-field-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{marginRight:"0.4rem",flexShrink:0}}>
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
                </svg>
                Job Description <span className="req">*</span>
              </span>
              <span className={`jd-char-badge${jobDescription.length > 0 && jobDescription.length < JD_MIN_CHARS ? " jd-char-badge--warn" : jobDescription.trim().length >= JD_MIN_CHARS ? " jd-char-badge--ok" : ""}`}>
                {jobDescription.length > 0
                  ? jobDescription.length < JD_MIN_CHARS
                    ? `${JD_MIN_CHARS - jobDescription.length} more chars needed`
                    : `${jobDescription.length} chars`
                  : `min ${JD_MIN_CHARS} chars`}
              </span>
            </div>
            <textarea
              className="jd-textarea"
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              onBlur={() => handleBlur("jobDescription")}
              placeholder="Paste the full job description here — the more detail you provide, the better the analysis..."
            />
            {fe("jobDescription") && <span className="field-error" style={{padding:"0 0.9rem 0.6rem"}}>{fe("jobDescription")}</span>}
          </div>

          {/* ── Resume Upload ── */}
          <div className="resume-col">
            <div className="resume-field-label">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{marginRight:"0.4rem",flexShrink:0}}>
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
              </svg>
              Resume <span className="req">*</span>
            </div>

            <label className={`upload-zone2${resumeFile && !pdfFailed ? " upload-zone2--done" : resumeFile && pdfFailed ? " upload-zone2--error" : fe("resume") ? " upload-zone2--error" : pdfExtracting ? " upload-zone2--loading" : ""}`}>
              <input
                type="file"
                accept="application/pdf"
                onChange={handleFileChange}
                style={{ display: "none" }}
              />

              {pdfExtracting ? (
                <div className="uz2-body">
                  <div className="uz2-spinner" />
                  <div className="uz2-text">
                    <span className="uz2-title">Reading your PDF…</span>
                    <span className="uz2-sub">{resumeFile?.name}</span>
                  </div>
                </div>
              ) : resumeFile && !pdfFailed ? (
                <div className="uz2-body">
                  <div className="uz2-icon uz2-icon--done">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </div>
                  <div className="uz2-text">
                    <span className="uz2-title">{resumeFile.name}</span>
                    <span className="uz2-sub">{resumeText.length.toLocaleString()} characters extracted</span>
                  </div>
                  <span className="uz2-change">Change</span>
                </div>
              ) : resumeFile && pdfFailed ? (
                <div className="uz2-body">
                  <div className="uz2-icon uz2-icon--warn">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                    </svg>
                  </div>
                  <div className="uz2-text">
                    <span className="uz2-title">Extraction failed</span>
                    <span className="uz2-sub">Paste your resume text below instead</span>
                  </div>
                </div>
              ) : (
                <div className="uz2-idle">
                  <div className="uz2-cloud-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
                      <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
                    </svg>
                  </div>
                  <span className="uz2-idle-title">Drop your resume here</span>
                  <span className="uz2-idle-sub">or <u>click to browse</u> · PDF · max 5 MB</span>
                </div>
              )}
            </label>

            {fe("resume") && <span className="field-error">{fe("resume")}</span>}

            {/* Manual paste fallback after extraction failure */}
            {pdfFailed && (
              <textarea
                value={resumeText}
                onChange={(e) => {
                  setResumeText(e.target.value);
                  if (e.target.value.trim()) {
                    setFieldErrors((prev) => ({ ...prev, resume: undefined }));
                  }
                }}
                placeholder="Paste your resume text here..."
                className="fallback-textarea"
              />
            )}
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <button type="submit" className="btn-primary analyze-submit">
          Analyze Application →
        </button>
      </form>
    </div>
  );
}