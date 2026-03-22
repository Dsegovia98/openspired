from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

import config
from application.artifacts_service import get_ticket_history, list_artifacts
from application.config_service import get_config_status
from application.ideas_service import capture_idea, list_ideas
from application.models import ReviewAction, RunRequest
from application.run_manager import InvalidRunStateError, RunManager, RunNotFoundError
from application.setup_service import apply_setup
from utils.jira_client import JiraClient, JiraAPIError


class RunOptions(BaseModel):
    publish_to_jira: bool = True
    tags: list[str] = Field(default_factory=list)
    include_jira_labels: bool = True


class RunCreateRequest(BaseModel):
    mode: Literal["manual", "jira"]
    input: str = ""
    jira_issue_key: str = ""
    options: RunOptions = Field(default_factory=RunOptions)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.mode == "manual" and not self.input.strip():
            raise ValueError("'input' es requerido para mode=manual")
        if self.mode == "jira" and not self.jira_issue_key.strip():
            raise ValueError("'jira_issue_key' es requerido para mode=jira")
        return self


class ReviewRequest(BaseModel):
    action: Literal["approve", "feedback", "discard"]
    feedback: str = ""


class SetupRequest(BaseModel):
    provider: str = "google"
    default_model: str = ""
    language: str = "en"
    profile_name: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    JIRA_BASE_URL: str = ""
    JIRA_EMAIL: str = ""
    JIRA_API_TOKEN: str = ""
    JIRA_PROJECT_KEY: str = ""
    JIRA_PROJECT_KEY_SECONDARY: str = ""
    DOMAIN_PRIMARY: str = ""
    DOMAIN_SECONDARY: str = ""


class IdeaCreateRequest(BaseModel):
    title: str
    description: str
    domain: str = "App"
    origin: str = "Manual"


class RunSummary(BaseModel):
    run_id: str
    status: str
    created_at: str
    updated_at: str
    request: dict[str, Any]
    result: dict[str, Any]
    error: str
    events_count: int


def _record_to_dict(record) -> dict[str, Any]:
    created_at = record.created_at.isoformat().replace("+00:00", "Z")
    updated_at = record.updated_at.isoformat().replace("+00:00", "Z")
    return {
        "run_id": record.run_id,
        "status": record.status,
        "created_at": created_at,
        "updated_at": updated_at,
        "request": {
            "mode": record.request.mode,
            "input_text": record.request.input_text,
            "jira_issue_key": record.request.jira_issue_key,
            "options": record.request.options,
        },
        "result": record.result,
        "error": record.error,
        "events_count": record.events_count,
    }


def _sse_pack(event_id: int, payload: dict[str, Any]) -> str:
    return f"id: {event_id}\nevent: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app(
    run_manager: RunManager | None = None,
    api_token: str | None = None,
    enforce_localhost: bool = True,
) -> FastAPI:
    manager = run_manager or RunManager()
    token = api_token or secrets.token_urlsafe(24)

    token_path = config.WORKSPACE_DIR / "logs" / ".api_token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")

    app = FastAPI(title="Openspired Local API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1", "tauri://localhost"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def local_auth_guard(request: Request, call_next):
        if enforce_localhost:
            host = request.client.host if request.client else ""
            if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
                return JSONResponse(status_code=403, content={"error": "Forbidden host"})

        # CORS preflight — dejar pasar para que CORSMiddleware lo resuelva
        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path in {"/health", "/setup"}:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {token}":
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

        return await call_next(request)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "workspace": str(config.WORKSPACE_DIR),
            "runtime_project_root": str(config.RUNTIME_PROJECT_ROOT),
            "profile_root": str(config.PROFILE_ROOT),
            "env_file": str(config.ENV_FILE),
        }

    @app.get("/config/status")
    def config_status():
        status = get_config_status()
        status["auth_required"] = True
        status["token_path"] = str(token_path)
        return status

    @app.get("/setup")
    def get_setup():
        env_path = config.ENV_FILE
        if not env_path.exists():
            return {
                "env_path": str(env_path),
                "profile_root": str(config.PROFILE_ROOT),
                "workspace_dir": str(config.WORKSPACE_DIR),
                "runtime_project_root": str(config.RUNTIME_PROJECT_ROOT),
            }
        data: dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                data[k.strip()] = v.strip()
        # Mask secrets — return only whether they're set
        for secret in ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "JIRA_API_TOKEN"]:
            if data.get(secret):
                data[secret] = "***set***"
        data["env_path"] = str(env_path)
        data["profile_root"] = str(config.PROFILE_ROOT)
        data["workspace_dir"] = str(config.WORKSPACE_DIR)
        data["runtime_project_root"] = str(config.RUNTIME_PROJECT_ROOT)
        return data

    @app.post("/setup")
    def setup(payload: SetupRequest):
        result = apply_setup(payload.model_dump())
        result["api_token"] = token
        result["token_path"] = str(token_path)
        return result

    @app.post("/runs")
    def create_run(payload: RunCreateRequest):
        request = RunRequest(
            mode=payload.mode,
            input_text=payload.input,
            jira_issue_key=payload.jira_issue_key,
            options=payload.options.model_dump(),
        )
        run_id = manager.submit_run(request)
        return {"run_id": run_id, "status": "queued"}

    @app.get("/runs/{run_id}", response_model=RunSummary)
    def get_run(run_id: str):
        try:
            record = manager.get_run(run_id)
        except RunNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found")
        return _record_to_dict(record)

    @app.get("/runs")
    def get_runs(limit: int = 50):
        records = manager.list_runs(limit=limit)
        return {"items": [_record_to_dict(r) for r in records], "count": len(records)}

    @app.get("/runs/{run_id}/events")
    def stream_run_events(run_id: str, after_id: int = 0):
        try:
            manager.get_run(run_id)
        except RunNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found")

        def _generator():
            cursor = max(0, after_id)
            terminal = False
            while not terminal:
                got = manager.wait_for_event(run_id, after_id=cursor, timeout_secs=20.0)
                if got is None:
                    yield ": heartbeat\n\n"
                    continue

                event_id, payload = got
                cursor = event_id
                yield _sse_pack(event_id, payload)

                event_type = payload.get("type", "")
                if event_type in {"run_completed", "run_failed", "run_discarded"}:
                    terminal = True

        return StreamingResponse(_generator(), media_type="text/event-stream")

    @app.post("/runs/{run_id}/review")
    def review_run(run_id: str, payload: ReviewRequest):
        try:
            manager.submit_review(
                run_id,
                ReviewAction(action=payload.action, feedback=payload.feedback),
            )
            return {"status": "accepted", "run_id": run_id}
        except RunNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found")
        except InvalidRunStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @app.get("/artifacts")
    def artifacts(
        ticket_type: str = "",
        module: str = "",
        tags: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 200,
        group_by: str = "",
    ):
        return list_artifacts(
            ticket_type=ticket_type,
            module=module,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            group_by=group_by,
        )

    @app.get("/artifacts/{ticket_id}/history")
    def artifact_history(ticket_id: str, include_content: bool = False):
        return get_ticket_history(ticket_id=ticket_id, include_content=include_content)

    @app.get("/jira/test")
    def jira_test(issue_key: str = ""):
        """Diagnostic endpoint: verify Jira connectivity and credentials."""
        env_path = config.ENV_FILE
        if not env_path.exists():
            return {"ok": False, "error": "No .env file found", "env_path": str(env_path)}

        env: dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

        base_url = env.get("JIRA_BASE_URL", "")
        email = env.get("JIRA_EMAIL", "")
        api_token = env.get("JIRA_API_TOKEN", "")
        project_key = env.get("JIRA_PROJECT_KEY", "")

        result: dict[str, Any] = {
            "config": {
                "JIRA_BASE_URL": base_url or "(not set)",
                "JIRA_EMAIL": email or "(not set)",
                "JIRA_API_TOKEN": "***set***" if api_token else "(not set)",
                "JIRA_PROJECT_KEY": project_key or "(not set)",
            }
        }

        if not base_url or not email or not api_token:
            result["ok"] = False
            result["error"] = "Missing required Jira config fields"
            return result

        client = JiraClient(base_url, email, api_token)

        # Test 1: /myself — verifies auth
        try:
            import urllib.request as _ureq
            import base64 as _b64
            import json as _json
            _auth_token = _b64.b64encode(f"{email}:{api_token}".encode()).decode()
            _req = _ureq.Request(
                f"{base_url.rstrip('/')}/rest/api/3/myself",
                headers={"Authorization": f"Basic {_auth_token}", "Accept": "application/json"},
            )
            with _ureq.urlopen(_req, timeout=10) as resp:
                me = _json.loads(resp.read())
            result["myself"] = {
                "ok": True,
                "displayName": me.get("displayName", ""),
                "emailAddress": me.get("emailAddress", ""),
                "accountId": me.get("accountId", ""),
            }
        except Exception as e:
            result["myself"] = {"ok": False, "error": str(e)}
            result["ok"] = False
            result["error"] = f"Auth failed: {e}"
            return result

        # Test 2: fetch specific issue if provided
        if issue_key:
            try:
                data = client.get_issue(issue_key)
                result["issue"] = {
                    "ok": True,
                    "key": data["key"],
                    "summary": data["summary"],
                    "project_key": data["project_key"],
                    "issue_type": data["issue_type"],
                    "status": data["status"],
                }
            except JiraAPIError as e:
                result["issue"] = {"ok": False, "error": str(e), "status_code": e.status}
            except Exception as e:
                result["issue"] = {"ok": False, "error": str(e)}

        result["ok"] = result.get("myself", {}).get("ok", False)
        return result

    @app.get("/ideas")
    def get_ideas(limit: int = 50):
        return {"items": list_ideas(limit=limit)}

    @app.post("/ideas")
    def create_idea(payload: IdeaCreateRequest):
        return capture_idea(
            title=payload.title,
            description=payload.description,
            domain=payload.domain,
            origin=payload.origin,
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="127.0.0.1", port=8765, reload=False)
