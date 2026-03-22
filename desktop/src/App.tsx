import { Eye, EyeOff, History, Lightbulb, Loader2, Play, Plus, Settings, UserCheck, Zap } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import logoUrl from "/logo.png";
import { apiGet, apiPost, applySetup, createRun, IdeaItem, Provider, RunMode, SetupPayload, streamRunEvents, TicketTypeHint } from "./api/client";
import { bootstrapDesktopBackend, restartDesktopBackend } from "./desktop/bootstrap";

// ── Types ──────────────────────────────────────────────────────────────────
type View = "create" | "pipeline" | "history" | "ideas" | "settings";

type RunSummary = {
  run_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  request: { mode: string; input_text: string; jira_issue_key: string };
  result: Record<string, unknown> & { cost_usd?: number };
  error: string;
  events_count: number;
};

type RunEvent = { type: string; [key: string]: unknown };

type ReviewData = {
  ticket_text: string;
  ticket_type: string;
  module: string;
  revision: number;
};

// ── Constants ──────────────────────────────────────────────────────────────
const TERMINAL = new Set(["run_completed", "run_failed", "run_discarded"]);

const EVENT_LABEL: Record<string, string> = {
  run_queued: "En cola",
  run_started: "Pipeline iniciado",
  review_required: "Esperando revisión humana",
  review_approved: "Aprobado — continuando",
  review_feedback: "Feedback recibido — reescribiendo",
  review_discarded: "Run descartado",
  run_completed: "Completado y publicado ✓",
  run_failed: "Error en el pipeline",
};

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  queued:        { label: "En cola",      cls: "badge--queued"  },
  running:       { label: "Ejecutando",   cls: "badge--running" },
  waiting_human: { label: "Revisión",     cls: "badge--warning" },
  completed:     { label: "Completado",   cls: "badge--success" },
  failed:        { label: "Error",        cls: "badge--error"   },
  discarded:     { label: "Descartado",   cls: "badge--muted"   },
};

const DOMAIN_BADGE: Record<string, string> = {
  App: "badge--running",
  "Analítica": "badge--info",
  Ambos: "badge--warning",
};

// ── Utils ──────────────────────────────────────────────────────────────────
function extractJiraKey(v: string): string {
  const m = v.match(/\/browse\/([A-Z][A-Z0-9_]+-\d+)/i);
  return m ? m[1].toUpperCase() : v.trim();
}

function labelFor(type: string): string {
  return EVENT_LABEL[type] ?? type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function rowClass(type: string): string {
  if (["run_completed", "review_approved"].includes(type)) return "event-row--success";
  if (["run_failed", "review_discarded"].includes(type)) return "event-row--error";
  if (type === "review_required") return "event-row--warning";
  if (type === "review_feedback") return "event-row--info";
  if (type === "run_started") return "event-row--live";
  return "";
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("es-CO", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function truncate(s: string, n = 52): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function runTitle(r: RunSummary): string {
  if (r.request.mode === "jira") return r.request.jira_issue_key || "Jira run";
  return truncate(r.request.input_text || "Run manual");
}

// ── App ────────────────────────────────────────────────────────────────────
export default function App() {
  const [view, setView] = useState<View>("create");

  // Backend / auth
  const [token, setToken] = useState("");
  const [booting, setBooting] = useState(false);
  const [backendOk, setBackendOk] = useState(false);
  const [error, setError] = useState("");

  // Create form
  const [mode, setMode] = useState<RunMode>("manual");
  const [input, setInput] = useState("");
  const [jiraKey, setJiraKey] = useState("");
  const [creating, setCreating] = useState(false);
  const [ticketTypeHint, setTicketTypeHint] = useState<TicketTypeHint>("auto");

  // Pipeline
  const [runId, setRunId] = useState("");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [reviewData, setReviewData] = useState<ReviewData | null>(null);
  const [reviewFeedback, setReviewFeedback] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState("");
  const [runResult, setRunResult] = useState<RunSummary | null>(null);
  const cancelStream = useRef<() => void>(() => {});
  const eventsEndRef = useRef<HTMLDivElement>(null);

  // History
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);

  // Ideas
  const [ideas, setIdeas] = useState<IdeaItem[]>([]);
  const [loadingIdeas, setLoadingIdeas] = useState(false);
  const [ideaTitle, setIdeaTitle] = useState("");
  const [ideaDescription, setIdeaDescription] = useState("");
  const [ideaDomain, setIdeaDomain] = useState<"App" | "Analítica" | "Ambos">("App");
  const [ideaOrigin, setIdeaOrigin] = useState("Manual");
  const [savingIdea, setSavingIdea] = useState(false);
  const [ideaSaved, setIdeaSaved] = useState(false);

  // Settings
  const [setupProvider, setSetupProvider] = useState<Provider>("google");
  const [setupModel, setSetupModel] = useState("gemini-2.5-flash-lite");
  const [setupLanguage, setSetupLanguage] = useState<"es" | "en">("es");
  const [setupKey, setSetupKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [jiraBaseUrl, setJiraBaseUrl] = useState("");
  const [jiraEmail, setJiraEmail] = useState("");
  const [jiraToken, setJiraToken] = useState("");
  const [showJiraToken, setShowJiraToken] = useState(false);
  const [showJiraTokenInput, setShowJiraTokenInput] = useState(false);
  const [jiraProjectKey, setJiraProjectKey] = useState("");
  const [savedConfig, setSavedConfig] = useState<Record<string, string> | null>(null);
  const [savingSetup, setSavingSetup] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [setupSaved, setSetupSaved] = useState(false);
  const [jiraTestResult, setJiraTestResult] = useState<Record<string, unknown> | null>(null);
  const [testingJira, setTestingJira] = useState(false);

  // ── Bootstrap ────────────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    async function boot() {
      setBooting(true);
      try {
        const res = await bootstrapDesktopBackend();
        if (!alive || !res) return;
        const tok = res.api_token?.trim();
        if (tok) {
          setToken(tok);
          setBackendOk(true);
          try {
            const saved = await apiGet<Record<string, string>>("/setup", tok);
            if (!alive) return;
            setSavedConfig(saved);
            if (saved.PROVIDER) setSetupProvider(saved.PROVIDER as Provider);
            if (saved.DEFAULT_MODEL) setSetupModel(saved.DEFAULT_MODEL);
            if (saved.JIRA_BASE_URL) setJiraBaseUrl(saved.JIRA_BASE_URL);
            if (saved.JIRA_EMAIL) setJiraEmail(saved.JIRA_EMAIL);
            if (saved.JIRA_PROJECT_KEY) setJiraProjectKey(saved.JIRA_PROJECT_KEY);
          } catch { /* first run, no config yet */ }
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Error iniciando backend");
      } finally {
        if (alive) setBooting(false);
      }
    }
    boot();
    return () => { alive = false; };
  }, []);

  // ── SSE subscription ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!runId || !token) return;
    setEvents([]);
    setReviewData(null);
    setReviewFeedback("");
    setPipelineStatus("running");
    setRunResult(null);

    let dead = false;
    cancelStream.current = () => { dead = true; };

    (async () => {
      try {
        for await (const ev of streamRunEvents(runId, token)) {
          if (dead) break;
          const e = ev as RunEvent;
          setEvents((p) => [...p, e]);
          eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });

          if (e.type === "review_required") { setReviewData((e.payload ?? e) as unknown as ReviewData); setPipelineStatus("waiting_human"); }
          if (e.type === "review_approved" || e.type === "review_feedback") { setReviewData(null); setPipelineStatus("running"); }
          if (TERMINAL.has(e.type)) {
            setPipelineStatus(e.type === "run_completed" ? "completed" : e.type === "run_discarded" ? "discarded" : "failed");
            try { const f = await apiGet<RunSummary>(`/runs/${runId}`, token); if (!dead) setRunResult(f); } catch { /**/ }
            break;
          }
        }
      } catch (e) { if (!dead) setError(e instanceof Error ? e.message : "Error en stream de eventos"); }
    })();

    return () => { dead = true; };
  }, [runId, token]);

  // ── History load ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (view === "history" && token) loadRuns();
  }, [view, token]);

  // ── Ideas load ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (view === "ideas" && token) loadIdeas();
  }, [view, token]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  async function loadRuns() {
    setLoadingRuns(true);
    try { const d = await apiGet<{ items: RunSummary[] }>("/runs?limit=50", token); setRuns(d.items ?? []); }
    catch { /**/ } finally { setLoadingRuns(false); }
  }

  async function loadIdeas() {
    setLoadingIdeas(true);
    try { const d = await apiGet<{ items: IdeaItem[] }>("/ideas", token); setIdeas(d.items ?? []); }
    catch { /**/ } finally { setLoadingIdeas(false); }
  }

  async function submitRun(e: FormEvent) {
    e.preventDefault();
    setError("");
    setCreating(true);
    cancelStream.current();
    try {
      const created = await createRun(token, mode, input, jiraKey, ticketTypeHint);
      setRunId(created.run_id);
      setView("pipeline");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error creando run");
    } finally { setCreating(false); }
  }

  async function submitIdea(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSavingIdea(true);
    setIdeaSaved(false);
    try {
      await apiPost<unknown>("/ideas", token, { title: ideaTitle, description: ideaDescription, domain: ideaDomain, origin: ideaOrigin });
      setIdeaTitle("");
      setIdeaDescription("");
      setIdeaDomain("App");
      setIdeaOrigin("Manual");
      setIdeaSaved(true);
      await loadIdeas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error guardando idea");
    } finally { setSavingIdea(false); }
  }

  async function sendReview(action: "approve" | "feedback" | "discard") {
    setReviewLoading(true);
    try {
      await apiPost(`/runs/${runId}/review`, token, { action, feedback: action === "feedback" ? reviewFeedback : "" });
      setReviewData(null);
      setReviewFeedback("");
    } catch (e) { setError(e instanceof Error ? e.message : "Error enviando revisión"); }
    finally { setReviewLoading(false); }
  }

  async function saveSetup(e: FormEvent) {
    e.preventDefault();
    setError(""); setSetupSaved(false); setSavingSetup(true);
    try {
      const p: SetupPayload = { provider: setupProvider, default_model: setupModel.trim(), language: setupLanguage };
      if (setupProvider === "google" && setupKey.trim()) p.GOOGLE_API_KEY = setupKey.trim();
      if (setupProvider === "openai" && setupKey.trim()) p.OPENAI_API_KEY = setupKey.trim();
      if (setupProvider === "anthropic" && setupKey.trim()) p.ANTHROPIC_API_KEY = setupKey.trim();
      if (jiraBaseUrl.trim()) p.JIRA_BASE_URL = jiraBaseUrl.trim();
      if (jiraEmail.trim()) p.JIRA_EMAIL = jiraEmail.trim();
      if (jiraToken.trim()) p.JIRA_API_TOKEN = jiraToken.trim();
      if (jiraProjectKey.trim()) p.JIRA_PROJECT_KEY = jiraProjectKey.trim();
      await applySetup(p, token);
      setSetupKey(""); setJiraToken(""); setSetupSaved(true);
      setShowKeyInput(false); setShowJiraTokenInput(false);
      setRestarting(true);
      try {
        const rb = await restartDesktopBackend();
        const newToken = rb?.api_token?.trim() ?? token;
        if (newToken) setToken(newToken);
        // Wait for backend to be ready before fetching config
        for (let i = 0; i < 20; i++) {
          try {
            await fetch("http://127.0.0.1:8765/health");
            break;
          } catch {
            await new Promise((r) => setTimeout(r, 500));
          }
        }
        const saved = await apiGet<Record<string, string>>("/setup", newToken);
        setSavedConfig(saved);
      } catch { /**/ } finally { setRestarting(false); }
    } catch (e) { setError(e instanceof Error ? e.message : "Error guardando configuración"); }
    finally { setSavingSetup(false); }
  }

  async function testJiraConnection(issueKey = "") {
    setTestingJira(true); setJiraTestResult(null);
    try {
      const path = issueKey ? `/jira/test?issue_key=${encodeURIComponent(issueKey)}` : "/jira/test";
      const result = await apiGet<Record<string, unknown>>(path, token);
      setJiraTestResult(result);
    } catch (e) {
      setJiraTestResult({ ok: false, error: e instanceof Error ? e.message : "Error al conectar" });
    } finally { setTestingJira(false); }
  }

  const isSet = (k: string) => savedConfig?.[k] === "***set***";
  const jiraConfigured = !!(savedConfig?.JIRA_BASE_URL);
  const canCreate = !!token.trim() && (mode === "manual" ? !!input.trim() : !!jiraKey.trim());
  const isRunning = pipelineStatus === "running" || pipelineStatus === "waiting_human";

  // ── Render: Nav ──────────────────────────────────────────────────────────
  function Nav() {
    return (
      <nav className="nav">
        <div className="nav__brand">
          <img src={logoUrl} className="nav__brand-icon" alt="Openspired logo" />
          <div>
            <span className="nav__brand-name">Openspired</span>
            <span className="nav__brand-sub">AI Pipeline</span>
          </div>
        </div>

        <ul className="nav__links">
          <li>
            <button className={`nav__item${view === "create" ? " nav__item--active" : ""}`} onClick={() => setView("create")}>
              <Plus size={16} /> <span>Nueva US</span>
            </button>
          </li>
          <li>
            <button className={`nav__item${view === "pipeline" ? " nav__item--active" : ""}`} onClick={() => setView("pipeline")}>
              <Zap size={16} /> <span>Pipeline</span>
              {isRunning && <span className="nav__live-dot" />}
            </button>
          </li>
          <li>
            <button className={`nav__item${view === "ideas" ? " nav__item--active" : ""}`} onClick={() => setView("ideas")}>
              <Lightbulb size={16} /> <span>Ideas</span>
            </button>
          </li>
          <li>
            <button className={`nav__item${view === "history" ? " nav__item--active" : ""}`} onClick={() => setView("history")}>
              <History size={16} /> <span>Historial</span>
            </button>
          </li>
        </ul>

        <div className="nav__divider" />

        <div className="nav__bottom">
          <button className={`nav__item${view === "settings" ? " nav__item--active" : ""}`} onClick={() => setView("settings")}>
            <Settings size={16} /> <span>Ajustes</span>
          </button>
          <p className="nav__status">
            {booting ? "Iniciando backend…" : backendOk ? "● Backend activo" : "○ Sin conexión"}
          </p>
        </div>
      </nav>
    );
  }

  // ── Render: Create ───────────────────────────────────────────────────────
  function CreateView() {
    return (
      <div className="view view--centered">
        <div className="view-header">
          <h1 className="view-title">Nueva User Story</h1>
          <p className="view-subtitle">El pipeline de agentes redactará y publicará el ticket en Jira.</p>
        </div>

        <div className="card">
          <form className="form" onSubmit={submitRun}>
            {/* Mode toggle */}
            <div className="field">
              <span className="field__label">Modo</span>
              <div className="mode-toggle">
                <button type="button" className={`mode-toggle__opt${mode === "manual" ? " mode-toggle__opt--active" : ""}`} onClick={() => setMode("manual")}>
                  Manual
                </button>
                <button type="button" className={`mode-toggle__opt${mode === "jira" ? " mode-toggle__opt--active" : ""}`} onClick={() => setMode("jira")}>
                  Desde Jira
                </button>
              </div>
            </div>

            {/* Ticket type hint selector */}
            <div className="field">
              <span className="field__label">Tipo de ticket</span>
              <div className="mode-toggle">
                <button
                  type="button"
                  className={`mode-toggle__opt${ticketTypeHint === "auto" ? " mode-toggle__opt--active" : ""}`}
                  onClick={() => setTicketTypeHint("auto")}
                >
                  Auto (IA decide)
                </button>
                <button
                  type="button"
                  className={`mode-toggle__opt${ticketTypeHint === "user_story" ? " mode-toggle__opt--active" : ""}`}
                  onClick={() => setTicketTypeHint("user_story")}
                >
                  User Story
                </button>
                <button
                  type="button"
                  className={`mode-toggle__opt${ticketTypeHint === "design_task" ? " mode-toggle__opt--active" : ""}`}
                  onClick={() => setTicketTypeHint("design_task")}
                >
                  Design Task
                </button>
              </div>
              <span className="field__hint">
                Design Task: para requerimientos visuales/UI. User Story: para funcionalidad. Auto: el Orquestador clasifica.
              </span>
            </div>

            {mode === "manual" ? (
              <div className="field">
                <label className="field__label" htmlFor="input-text">Descripción del ticket</label>
                <textarea
                  id="input-text"
                  className="textarea"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Describe la funcionalidad que quieres construir. El agente analizará el contexto del módulo, diseñará la solución y redactará las USs completas."
                  rows={6}
                />
              </div>
            ) : (
              <div className="field">
                <label className="field__label" htmlFor="jira-key">
                  Jira Issue Key o URL
                  {!jiraConfigured && (
                    <span style={{ color: "var(--warning)", fontWeight: 500, fontSize: 11 }}>
                      — configura Jira en Ajustes primero
                    </span>
                  )}
                </label>
                <input
                  id="jira-key"
                  className="input"
                  value={jiraKey}
                  onChange={(e) => setJiraKey(extractJiraKey(e.target.value))}
                  placeholder="CAKE-123 o https://tuempresa.atlassian.net/browse/CAKE-123"
                />
                {jiraKey && (
                  <span className="field__hint">Key detectado: <strong>{jiraKey}</strong></span>
                )}
              </div>
            )}

            <button type="submit" className="btn btn--primary btn--lg btn--full" disabled={!canCreate || creating}>
              {creating ? <><Loader2 size={16} className="spin" /> Creando run…</> : <><Play size={16} /> Ejecutar pipeline</>}
            </button>
          </form>
        </div>

        {!backendOk && !booting && (
          <div className="empty-state">
            <div className="empty-state__icon"><Settings size={22} /></div>
            <h3>Backend no disponible</h3>
            <p>Configura tu API key en Ajustes para empezar.</p>
            <button className="btn btn--ghost btn--sm" onClick={() => setView("settings")}>Ir a Ajustes</button>
          </div>
        )}
      </div>
    );
  }

  // ── Render: Pipeline ─────────────────────────────────────────────────────
  function PipelineView() {
    if (!runId) {
      return (
        <div className="view view--centered">
          <div className="empty-state">
            <div className="empty-state__icon"><Zap size={22} /></div>
            <h3>Sin run activo</h3>
            <p>Crea una nueva US para ver el pipeline en tiempo real.</p>
            <button className="btn btn--ghost btn--sm" onClick={() => setView("create")}>Nueva US</button>
          </div>
        </div>
      );
    }

    const badge = STATUS_BADGE[pipelineStatus] ?? { label: pipelineStatus, cls: "badge--muted" };

    return (
      <div className="view">
        {/* Header */}
        <div className="pipeline-header">
          <div className="view-header">
            <h1 className="view-title">Pipeline en vivo</h1>
            <p className="view-subtitle">
              Agentes procesando tu ticket en tiempo real.
            </p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
            <span className={`badge ${badge.cls}`}>{badge.label}</span>
            <span className="pipeline-run-id">{runId}</span>
          </div>
        </div>

        {/* Review panel — aparece inline cuando waiting_human */}
        {reviewData && (
          <div className="review-card">
            <div className="review-card__header">
              <div className="review-card__icon"><UserCheck size={18} /></div>
              <div className="review-card__header-text">
                <h3>Revisión humana requerida</h3>
                <p>
                  Módulo: <strong>{reviewData.module}</strong> · Tipo: <strong>{reviewData.ticket_type}</strong>
                  {reviewData.revision > 0 && ` · Revisión #${reviewData.revision + 1}`}
                </p>
              </div>
            </div>

            <div className="review-card__body">
              <pre className="review-ticket">{reviewData.ticket_text}</pre>
            </div>

            <div className="review-card__footer">
              <div className="review-feedback-row">
                <textarea
                  className="textarea"
                  value={reviewFeedback}
                  onChange={(e) => setReviewFeedback(e.target.value)}
                  placeholder="Escribe feedback para que el agente reescriba... (opcional)"
                  rows={2}
                />
              </div>
              <div className="review-actions-row">
                <button className="btn btn--success" onClick={() => sendReview("approve")} disabled={reviewLoading}>
                  ✓ Aprobar y publicar
                </button>
                <button
                  className="btn btn--ghost"
                  onClick={() => sendReview("feedback")}
                  disabled={reviewLoading || !reviewFeedback.trim()}
                >
                  ↩ Reescribir con feedback
                </button>
                <button className="btn btn--danger btn--sm" onClick={() => sendReview("discard")} disabled={reviewLoading}>
                  ✕ Descartar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Event log */}
        <div className="card">
          <div className="card__header">
            <span className="card__title">Progreso del pipeline</span>
            <span className="card__label">{events.length} eventos</span>
          </div>
          {events.length === 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-muted)", fontSize: 13, padding: "8px 0" }}>
              <Loader2 size={14} className="spin" /> Conectando al pipeline…
            </div>
          ) : (
            <div className="event-log">
              {events.map((ev, i) => (
                <div key={i} className={`event-row ${rowClass(ev.type)}`}>
                  <span className="event-row__dot" />
                  <span className="event-row__label">{labelFor(ev.type)}</span>
                  <span className="event-row__type">{ev.type}</span>
                </div>
              ))}
              <div ref={eventsEndRef} />
            </div>
          )}
        </div>

        {/* Final result */}
        {runResult && pipelineStatus === "completed" && (
          <div className="card">
            <div className="card__header">
              <span className="card__title">Resultado final</span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {runResult.result?.cost_usd != null && (
                  <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-muted)", background: "var(--n-100)", padding: "2px 8px", borderRadius: 5 }}>
                    ${Number(runResult.result.cost_usd).toFixed(4)} USD
                  </span>
                )}
                <span className="badge badge--success">Publicado en Jira</span>
              </div>
            </div>
            <details>
              <summary style={{ cursor: "pointer", fontSize: 13, color: "var(--text-muted)", userSelect: "none" }}>Ver JSON completo</summary>
              <div className="run-detail" style={{ marginTop: 8, borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
                <pre>{JSON.stringify(runResult.result, null, 2)}</pre>
              </div>
            </details>
          </div>
        )}

        {runResult && pipelineStatus === "failed" && (
          <div className="card" style={{ borderColor: "oklch(54% 0.22 28 / 0.3)" }}>
            <div className="card__header">
              <span className="card__title" style={{ color: "var(--error)" }}>Error en el pipeline</span>
              <span className="badge badge--error">Fallido</span>
            </div>
            <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--error)", whiteSpace: "pre-wrap" }}>{runResult.error}</pre>
          </div>
        )}
      </div>
    );
  }

  // ── Render: History ──────────────────────────────────────────────────────
  function HistoryView() {
    return (
      <div className="view">
        <div className="view-header">
          <h1 className="view-title">Historial</h1>
          <p className="view-subtitle">Todos los runs ejecutados en esta workspace.</p>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button className="btn btn--ghost btn--sm" onClick={loadRuns} disabled={loadingRuns}>
            {loadingRuns ? <Loader2 size={14} className="spin" /> : "Actualizar"}
          </button>
        </div>

        {loadingRuns && runs.length === 0 && (
          <div className="empty-state"><Loader2 size={22} className="spin" /><p>Cargando historial…</p></div>
        )}

        {!loadingRuns && runs.length === 0 && (
          <div className="empty-state">
            <div className="empty-state__icon"><History size={22} /></div>
            <h3>Sin historial aún</h3>
            <p>Los runs aparecerán aquí después del primer pipeline.</p>
          </div>
        )}

        {runs.length > 0 && (
          <div className="run-list">
            {runs.map((r) => {
              const badge = STATUS_BADGE[r.status] ?? { label: r.status, cls: "badge--muted" };
              const expanded = expandedRun === r.run_id;
              return (
                <div key={r.run_id}>
                  <div
                    className={`run-row${expanded ? " run-row--expanded" : ""}`}
                    onClick={() => setExpandedRun(expanded ? null : r.run_id)}
                  >
                    <div>
                      <div className="run-row__title">{runTitle(r)}</div>
                      <div className="run-row__sub">{r.run_id}</div>
                    </div>
                    <span className="badge badge--muted" style={{ fontSize: 11 }}>{r.request.mode}</span>
                    {r.result?.cost_usd != null && (
                      <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                        ${Number(r.result.cost_usd).toFixed(4)}
                      </span>
                    )}
                    <span className={`badge ${badge.cls}`}>{badge.label}</span>
                    <span className="run-row__date">{fmtDate(r.created_at)}</span>
                  </div>
                  {expanded && (
                    <div className="run-detail">
                      {r.error && (
                        <p style={{ color: "var(--error)", fontSize: 12, marginBottom: 8 }}>Error: {r.error}</p>
                      )}
                      <pre>{JSON.stringify(r.result && Object.keys(r.result).length ? r.result : { events: r.events_count, status: r.status }, null, 2)}</pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // ── Render: Ideas ────────────────────────────────────────────────────────
  function IdeasView() {
    return (
      <div className="view">
        <div className="view-header">
          <h1 className="view-title">Ideas</h1>
          <p className="view-subtitle">Captura y gestiona ideas de producto antes de convertirlas en tickets.</p>
        </div>

        {/* New idea form */}
        <div className="card">
          <div className="card__header">
            <span className="card__title">Nueva idea</span>
          </div>
          <form className="form" onSubmit={submitIdea}>
            <div className="field">
              <label className="field__label" htmlFor="idea-title">Título <span style={{ color: "var(--error)" }}>*</span></label>
              <input
                id="idea-title"
                className="input"
                value={ideaTitle}
                onChange={(e) => setIdeaTitle(e.target.value)}
                placeholder="¿Qué idea tienes?"
                required
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor="idea-description">Descripción <span style={{ color: "var(--error)" }}>*</span></label>
              <textarea
                id="idea-description"
                className="textarea"
                value={ideaDescription}
                onChange={(e) => setIdeaDescription(e.target.value)}
                placeholder="Describe la idea con más detalle: contexto, problema que resuelve, valor esperado…"
                rows={4}
                required
              />
            </div>

            <div className="grid-2">
              <div className="field">
                <label className="field__label" htmlFor="idea-domain">Dominio</label>
                <select
                  id="idea-domain"
                  className="select"
                  value={ideaDomain}
                  onChange={(e) => setIdeaDomain(e.target.value as "App" | "Analítica" | "Ambos")}
                >
                  <option value="App">App</option>
                  <option value="Analítica">Analítica</option>
                  <option value="Ambos">Ambos</option>
                </select>
              </div>

              <div className="field">
                <label className="field__label" htmlFor="idea-origin">Origen</label>
                <select
                  id="idea-origin"
                  className="select"
                  value={ideaOrigin}
                  onChange={(e) => setIdeaOrigin(e.target.value)}
                >
                  <option value="Manual">Manual</option>
                  <option value="Reunión">Reunión</option>
                  <option value="Chat">Chat</option>
                  <option value="Insight">Insight</option>
                </select>
              </div>
            </div>

            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={savingIdea || !ideaTitle.trim() || !ideaDescription.trim()}
              >
                {savingIdea ? <><Loader2 size={14} className="spin" /> Guardando…</> : <><Lightbulb size={14} /> Guardar idea</>}
              </button>
              {ideaSaved && !savingIdea && (
                <span style={{ color: "var(--success)", fontSize: 13, fontWeight: 600 }}>✓ Idea guardada</span>
              )}
            </div>
          </form>
        </div>

        {/* Ideas list */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 500 }}>
            {ideas.length} idea{ideas.length !== 1 ? "s" : ""}
          </span>
          <button className="btn btn--ghost btn--sm" onClick={loadIdeas} disabled={loadingIdeas}>
            {loadingIdeas ? <Loader2 size={14} className="spin" /> : "Actualizar"}
          </button>
        </div>

        {loadingIdeas && ideas.length === 0 && (
          <div className="empty-state"><Loader2 size={22} className="spin" /><p>Cargando ideas…</p></div>
        )}

        {!loadingIdeas && ideas.length === 0 && (
          <div className="empty-state">
            <div className="empty-state__icon"><Lightbulb size={22} /></div>
            <h3>Sin ideas aún</h3>
            <p>Captura tu primera idea con el formulario de arriba.</p>
          </div>
        )}

        {ideas.length > 0 && (
          <div className="run-list" style={{ marginTop: 8 }}>
            {ideas.map((idea) => (
              <div key={idea.filename} className="card" style={{ padding: "14px 16px", marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4, color: "var(--text)" }}>{idea.title}</div>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{idea.date}</span>
                      <span style={{ color: "var(--text-muted)", fontSize: 11 }}>·</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{idea.origin}</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                    {idea.domain && (
                      <span className={`badge ${DOMAIN_BADGE[idea.domain] ?? "badge--muted"}`} style={{ fontSize: 11 }}>
                        {idea.domain}
                      </span>
                    )}
                    {idea.status && (
                      <span className="badge badge--muted" style={{ fontSize: 11 }}>
                        {idea.status}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Render: Settings ─────────────────────────────────────────────────────
  function SettingsView() {
    const keyHint = setupProvider === "google" ? "AIza..." : setupProvider === "openai" ? "sk-..." : "sk-ant-...";
    const apiKeyName = `${setupProvider.toUpperCase()}_API_KEY`;
    const apiKeyAlreadySet = isSet(apiKeyName);
    const jiraTokenAlreadySet = isSet("JIRA_API_TOKEN");

    return (
      <div className="view">
        <div className="view-header">
          <h1 className="view-title">Ajustes</h1>
          <p className="view-subtitle">Configuración del provider de IA y la integración con Jira.</p>
        </div>

        <form className="form" onSubmit={saveSetup}>
          {/* AI Provider */}
          <div className="card">
            <div className="settings-section">
              <div className="settings-section__title">
                Provider de IA
                <span className={`tag${savedConfig?.PROVIDER ? " tag--ok" : ""}`}>
                  {savedConfig?.PROVIDER ?? "no configurado"}
                </span>
              </div>

              <div className="grid-2">
                <div className="field">
                  <label className="field__label" htmlFor="provider">Provider</label>
                  <select id="provider" className="select" value={setupProvider} onChange={(e) => { setSetupProvider(e.target.value as Provider); setShowKeyInput(false); setSetupKey(""); }}>
                    <option value="google">Google (Gemini)</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                  </select>
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="model">Modelo</label>
                  <input id="model" className="input" value={setupModel} onChange={(e) => setSetupModel(e.target.value)} placeholder="gemini-2.5-flash-lite" />
                </div>
              </div>

              {/* API Key — smart display */}
              <div className="field">
                <label className="field__label" htmlFor="api-key">API Key</label>

                {apiKeyAlreadySet && !showKeyInput ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 13, color: "var(--success)", fontWeight: 600 }}>✓ Configurada</span>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => { setShowKeyInput(true); setSetupKey(""); }}
                    >
                      Cambiar
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="input-group">
                      <input
                        id="api-key"
                        className="input input--mono"
                        type={showKey ? "text" : "password"}
                        value={setupKey}
                        onChange={(e) => setSetupKey(e.target.value)}
                        placeholder={keyHint}
                        autoFocus={showKeyInput}
                      />
                      <button type="button" className="input-group__btn" onClick={() => setShowKey(!showKey)} title="Mostrar/ocultar">
                        {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                    {apiKeyAlreadySet && (
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        style={{ marginTop: 6 }}
                        onClick={() => { setShowKeyInput(false); setSetupKey(""); }}
                      >
                        Cancelar
                      </button>
                    )}
                  </>
                )}

                <span className="field__hint">La key se guarda localmente y nunca sale de tu máquina.</span>
              </div>

              <div className="field">
                <label className="field__label" htmlFor="lang">Idioma de salida</label>
                <select id="lang" className="select" value={setupLanguage} onChange={(e) => setSetupLanguage(e.target.value as "es" | "en")} style={{ width: 160 }}>
                  <option value="es">Español</option>
                  <option value="en">English</option>
                </select>
              </div>
            </div>
          </div>

          {/* Jira */}
          <div className="card">
            <div className="settings-section">
              <div className="settings-section__title">
                Integración Jira
                <span className={`tag${jiraConfigured ? " tag--ok" : ""}`}>
                  {jiraConfigured ? "configurado" : "opcional"}
                </span>
              </div>

              <div className="grid-2">
                <div className="field">
                  <label className="field__label" htmlFor="jira-url">Base URL</label>
                  <input id="jira-url" className="input" value={jiraBaseUrl} onChange={(e) => setJiraBaseUrl(e.target.value)} placeholder="https://tuempresa.atlassian.net" />
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="jira-email">Email</label>
                  <input id="jira-email" className="input" type="email" value={jiraEmail} onChange={(e) => setJiraEmail(e.target.value)} placeholder="tu@empresa.com" />
                </div>
              </div>

              <div className="grid-2">
                <div className="field">
                  <label className="field__label" htmlFor="jira-token">API Token</label>

                  {jiraTokenAlreadySet && !showJiraTokenInput ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 13, color: "var(--success)", fontWeight: 600 }}>✓ Configurada</span>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => { setShowJiraTokenInput(true); setJiraToken(""); }}
                      >
                        Cambiar
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="input-group">
                        <input
                          id="jira-token"
                          className="input input--mono"
                          type={showJiraToken ? "text" : "password"}
                          value={jiraToken}
                          onChange={(e) => setJiraToken(e.target.value)}
                          placeholder="atlassian.com/manage-profile/security"
                          autoFocus={showJiraTokenInput}
                        />
                        <button type="button" className="input-group__btn" onClick={() => setShowJiraToken(!showJiraToken)}>
                          {showJiraToken ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                      {jiraTokenAlreadySet && (
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          style={{ marginTop: 6 }}
                          onClick={() => { setShowJiraTokenInput(false); setJiraToken(""); }}
                        >
                          Cancelar
                        </button>
                      )}
                    </>
                  )}
                </div>

                <div className="field">
                  <label className="field__label" htmlFor="jira-project">Project Key</label>
                  <input id="jira-project" className="input" value={jiraProjectKey} onChange={(e) => setJiraProjectKey(e.target.value)} placeholder="CAKE" />
                </div>
              </div>
              {/* Jira connectivity test — inline inside Jira card */}
              {jiraConfigured && (
                <div style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => testJiraConnection()}
                    disabled={testingJira}
                  >
                    {testingJira ? <><Loader2 size={13} className="spin" /> Probando…</> : "Probar conexión"}
                  </button>
                  {jiraTestResult && (
                    <div style={{ marginTop: 10, background: "var(--surface-2)", borderRadius: 8, padding: "10px 14px", fontSize: 12, fontFamily: "var(--font-mono)" }}>
                      {jiraTestResult.ok ? (
                        <div style={{ color: "var(--success)" }}>
                          ✓ Conexión OK
                          {jiraTestResult.myself && (
                            <div style={{ color: "var(--fg-muted)", marginTop: 4 }}>
                              {(jiraTestResult.myself as Record<string, string>).displayName} · {(jiraTestResult.myself as Record<string, string>).emailAddress}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div style={{ color: "var(--error)" }}>
                          ✗ {String(jiraTestResult.error || "Error desconocido")}
                          {jiraTestResult.config && (
                            <pre style={{ marginTop: 8, fontSize: 11, color: "var(--fg-muted)", whiteSpace: "pre-wrap" }}>
                              {JSON.stringify(jiraTestResult.config, null, 2)}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Save */}
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button type="submit" className="btn btn--primary" disabled={savingSetup || restarting}>
              {savingSetup ? <><Loader2 size={14} className="spin" /> Guardando…</> :
               restarting ? <><Loader2 size={14} className="spin" /> Reiniciando backend…</> :
               "Guardar configuración"}
            </button>
            {setupSaved && !savingSetup && !restarting && (
              <span style={{ color: "var(--success)", fontSize: 13, fontWeight: 600 }}>✓ Configuración guardada</span>
            )}
          </div>
        </form>
      </div>
    );
  }

  // ── Root render ───────────────────────────────────────────────────────────
  return (
    <div className="shell">
      {Nav()}
      <main className="main">
        {error && (
          <div className="alert alert--error">
            <span>{error}</span>
            <button className="alert__close" onClick={() => setError("")}>×</button>
          </div>
        )}
        {booting && <div className="alert alert--info"><Loader2 size={14} className="spin" /> Iniciando backend local…</div>}

        {view === "create" && CreateView()}
        {view === "pipeline" && PipelineView()}
        {view === "ideas" && IdeasView()}
        {view === "history" && HistoryView()}
        {view === "settings" && SettingsView()}
      </main>
    </div>
  );
}
