export type RunMode = "manual" | "jira";
export type TicketTypeHint = "auto" | "user_story" | "design_task";

export type IdeaPayload = {
  title: string;
  description: string;
  domain: "App" | "Analítica" | "Ambos";
  origin: string;
};

export type IdeaItem = {
  filename: string;
  title: string;
  date: string;
  domain: string;
  status: string;
  origin: string;
};
export type Provider = "google" | "openai" | "anthropic";

export type SetupPayload = {
  provider: Provider;
  default_model: string;
  language: "es" | "en";
  GOOGLE_API_KEY?: string;
  OPENAI_API_KEY?: string;
  ANTHROPIC_API_KEY?: string;
  JIRA_BASE_URL?: string;
  JIRA_EMAIL?: string;
  JIRA_API_TOKEN?: string;
  JIRA_PROJECT_KEY?: string;
  JIRA_PROJECT_KEY_SECONDARY?: string;
  DOMAIN_PRIMARY?: string;
  DOMAIN_SECONDARY?: string;
};

export type SetupResponse = {
  status: string;
  provider: string;
  default_model: string;
  workspace: string;
  env_path: string;
  api_token: string;
  token_path: string;
};

export async function apiGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`http://127.0.0.1:8765${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`GET ${path} failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export async function createRun(
  token: string,
  mode: RunMode,
  input: string,
  jiraIssueKey = "",
  ticketTypeHint: TicketTypeHint = "auto",
) {
  // Prepend type hint to input so Orquestador picks it up
  let finalInput = input;
  if (mode === "manual" && ticketTypeHint !== "auto") {
    const label = ticketTypeHint === "design_task" ? "Design Task" : "User Story";
    finalInput = `TIPO SOLICITADO: ${label}\n\n${input}`;
  }

  const payload = mode === "manual"
    ? { mode, input: finalInput }
    : { mode, jira_issue_key: jiraIssueKey };

  const res = await fetch("http://127.0.0.1:8765/runs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`POST /runs failed (${res.status})`);
  }
  return res.json();
}

export async function apiPost<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`http://127.0.0.1:8765${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST ${path} failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export async function* streamRunEvents(runId: string, token: string, afterId = 0) {
  const res = await fetch(`http://127.0.0.1:8765/runs/${runId}/events?after_id=${afterId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok || !res.body) throw new Error(`SSE failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      if (part.includes(": heartbeat")) continue;
      const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
      if (dataLine) yield JSON.parse(dataLine.slice(6)) as Record<string, unknown>;
    }
  }
}

export async function applySetup(payload: SetupPayload, token = ""): Promise<SetupResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token.trim()) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch("http://127.0.0.1:8765/setup", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`POST /setup failed (${res.status})`);
  }
  return (await res.json()) as SetupResponse;
}
