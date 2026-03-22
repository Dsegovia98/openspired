#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::{
    collections::HashSet,
    fs,
    fs::OpenOptions,
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager, RunEvent, State};

struct BackendState {
    child: Mutex<Option<Child>>,
}

#[derive(Clone)]
struct RuntimeLayout {
    bundle_root: PathBuf,
    engine_dir: PathBuf,
    agents_dir: PathBuf,
    requirements_path: PathBuf,
    runtime_root: PathBuf,
    workspace_dir: PathBuf,
    env_path: PathBuf,
    token_path: PathBuf,
    log_path: PathBuf,
    venv_dir: PathBuf,
    venv_python: PathBuf,
}

#[derive(Serialize)]
struct BootstrapResponse {
    status: String,
    api_base_url: String,
    api_token: String,
    runtime_root: String,
    workspace_dir: String,
    env_path: String,
    log_path: String,
}

fn api_addr() -> SocketAddr {
    "127.0.0.1:8765".parse().expect("valid loopback socket")
}

fn is_api_reachable() -> bool {
    TcpStream::connect_timeout(&api_addr(), Duration::from_millis(400)).is_ok()
}

fn wait_for_api(timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if is_api_reachable() {
            return true;
        }
        thread::sleep(Duration::from_millis(300));
    }
    false
}

fn wait_for_token(path: &Path, timeout: Duration) -> Option<String> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if let Ok(raw) = fs::read_to_string(path) {
            let token = raw.trim();
            if !token.is_empty() {
                return Some(token.to_string());
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
    None
}

fn run_command(mut cmd: Command, context: &str) -> Result<(), String> {
    let status = cmd
        .status()
        .map_err(|e| format!("{context}: cannot execute command ({e})"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("{context}: command failed with status {status}"))
    }
}

fn find_dir_named(root: &Path, dir_name: &str, max_depth: usize) -> Option<PathBuf> {
    let mut stack = vec![(root.to_path_buf(), 0usize)];
    while let Some((current, depth)) = stack.pop() {
        let entries = match fs::read_dir(&current) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let file_type = match entry.file_type() {
                Ok(ft) => ft,
                Err(_) => continue,
            };
            if !file_type.is_dir() {
                continue;
            }
            if path
                .file_name()
                .and_then(|n| n.to_str())
                .map(|n| n == dir_name)
                .unwrap_or(false)
            {
                return Some(path);
            }
            if depth < max_depth {
                stack.push((path, depth + 1));
            }
        }
    }
    None
}

fn find_file_named(root: &Path, file_name: &str, max_depth: usize) -> Option<PathBuf> {
    let mut stack = vec![(root.to_path_buf(), 0usize)];
    while let Some((current, depth)) = stack.pop() {
        let entries = match fs::read_dir(&current) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let file_type = match entry.file_type() {
                Ok(ft) => ft,
                Err(_) => continue,
            };
            if file_type.is_file()
                && path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n == file_name)
                    .unwrap_or(false)
            {
                return Some(path);
            }
            if file_type.is_dir() && depth < max_depth {
                stack.push((path, depth + 1));
            }
        }
    }
    None
}

fn resolve_layout(app: &AppHandle) -> Result<RuntimeLayout, String> {
    let (bundle_root, engine_dir, agents_dir, requirements_path, env_example_path) = if cfg!(debug_assertions) {
        let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .map_err(|e| format!("Cannot resolve repo root in dev mode: {e}"))?;
        (
            repo_root.clone(),
            repo_root.join("engine"),
            repo_root.join("agents"),
            repo_root.join("requirements.txt"),
            repo_root.join(".env.example"),
        )
    } else {
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|e| format!("Cannot resolve resource directory: {e}"))?;

        // In release bundles, external resources may be nested under `_up_/_up_`.
        // Discover a project-like root dynamically from the bundled engine files.
        let run_py = find_file_named(&resource_dir, "run.py", 8)
            .ok_or_else(|| format!("Cannot find bundled engine/run.py under {}", resource_dir.display()))?;
        let discovered_engine = run_py
            .parent()
            .ok_or_else(|| "Cannot resolve engine directory from run.py".to_string())?
            .to_path_buf();
        let discovered_root = discovered_engine
            .parent()
            .ok_or_else(|| "Cannot resolve bundled project root from engine directory".to_string())?
            .to_path_buf();

        let discovered_agents = if discovered_root.join("agents").is_dir() {
            discovered_root.join("agents")
        } else {
            find_dir_named(&resource_dir, "agents", 8)
                .ok_or_else(|| format!("Cannot find bundled agents directory under {}", resource_dir.display()))?
        };

        let discovered_requirements = if discovered_root.join("requirements.txt").is_file() {
            discovered_root.join("requirements.txt")
        } else if discovered_engine.join("requirements.txt").is_file() {
            discovered_engine.join("requirements.txt")
        } else {
            find_file_named(&resource_dir, "requirements.txt", 8).ok_or_else(|| {
                format!(
                    "Cannot find bundled requirements.txt under {}",
                    resource_dir.display()
                )
            })?
        };

        let discovered_env_example = if discovered_root.join(".env.example").is_file() {
            discovered_root.join(".env.example")
        } else if discovered_engine.join(".env.example").is_file() {
            discovered_engine.join(".env.example")
        } else {
            find_file_named(&resource_dir, ".env.example", 8).unwrap_or_default()
        };

        (
            discovered_root,
            discovered_engine,
            discovered_agents,
            discovered_requirements,
            discovered_env_example,
        )
    };

    if !engine_dir.exists() {
        return Err(format!(
            "Engine directory not found at {}",
            engine_dir.display()
        ));
    }
    if !agents_dir.exists() {
        return Err(format!(
            "Agents directory not found at {}",
            agents_dir.display()
        ));
    }
    if !requirements_path.exists() {
        return Err(format!(
            "requirements.txt not found at {}",
            requirements_path.display()
        ));
    }

    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("Cannot resolve app data dir: {e}"))?;
    let runtime_root = app_data_dir.join("runtime");
    let workspace_dir = runtime_root.join("workspace");
    let logs_dir = workspace_dir.join("logs");
    let env_path = runtime_root.join(".env");
    let token_path = logs_dir.join(".api_token");
    let log_path = logs_dir.join("desktop_backend.log");
    let venv_dir = runtime_root.join(".venv");
    let venv_python = venv_dir.join("bin/python3");

    for rel in [
        "context/.reasoning_bank",
        "context/modules",
        "context/artifacts",
        "context/tickets",
        "artifacts/ideas",
        "artifacts/research",
        "artifacts/prds",
        "artifacts/dts",
        "artifacts/uss",
        "links",
        "logs/pipeline_runs",
        // Legacy folders kept for current backend compatibility.
        "modules",
        "tickets",
    ] {
        fs::create_dir_all(workspace_dir.join(rel))
            .map_err(|e| format!("Cannot create workspace dir '{rel}': {e}"))?;
    }

    let relations_path = workspace_dir.join("links/relations.ndjson");
    if !relations_path.exists() {
        OpenOptions::new()
            .create(true)
            .write(true)
            .open(&relations_path)
            .map_err(|e| format!("Cannot create relations file {}: {e}", relations_path.display()))?;
    }

    if !env_path.exists() && env_example_path.exists() {
        fs::copy(&env_example_path, &env_path).map_err(|e| {
            format!(
                "Cannot create initial .env from template {}: {e}",
                env_example_path.display()
            )
        })?;
    }

    Ok(RuntimeLayout {
        bundle_root,
        engine_dir,
        agents_dir,
        requirements_path,
        runtime_root,
        workspace_dir,
        env_path,
        token_path,
        log_path,
        venv_dir,
        venv_python,
    })
}

fn python_version(python: &Path) -> Option<(u8, u8)> {
    let output = Command::new(python)
        .args([
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let raw = String::from_utf8(output.stdout).ok()?;
    let mut parts = raw.trim().split('.');
    let major = parts.next()?.parse::<u8>().ok()?;
    let minor = parts.next()?.parse::<u8>().ok()?;
    Some((major, minor))
}

fn is_supported_python(version: (u8, u8)) -> bool {
    version.0 > 3 || (version.0 == 3 && version.1 >= 10)
}

fn python_candidates(layout: &RuntimeLayout) -> Vec<PathBuf> {
    let mut candidates = Vec::<PathBuf>::new();
    if let Ok(custom) = std::env::var("OPENSPIRED_PYTHON") {
        candidates.push(PathBuf::from(custom));
    }
    candidates.push(layout.venv_python.clone());
    for abs in [
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ] {
        candidates.push(PathBuf::from(abs));
    }
    candidates.push(PathBuf::from("python3"));
    candidates.push(PathBuf::from("python"));

    let mut seen = HashSet::<String>::new();
    let mut deduped = Vec::<PathBuf>::new();
    for candidate in candidates {
        let key = candidate.to_string_lossy().to_string();
        if !seen.contains(&key) {
            seen.insert(key);
            deduped.push(candidate);
        }
    }
    deduped
}

fn select_best_python(layout: &RuntimeLayout) -> Option<PathBuf> {
    let mut best: Option<(PathBuf, (u8, u8))> = None;
    for candidate in python_candidates(layout) {
        let version = match python_version(&candidate) {
            Some(v) => v,
            None => continue,
        };
        if !is_supported_python(version) {
            continue;
        }
        match &best {
            None => best = Some((candidate, version)),
            Some((_, best_v)) if version > *best_v => best = Some((candidate, version)),
            _ => {}
        }
    }
    best.map(|(path, _)| path)
}

fn python_has_backend_deps(python: &Path) -> bool {
    Command::new(python)
        .args(["-c", "import fastapi,uvicorn,dotenv,yaml"])
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn ensure_python_ready(layout: &RuntimeLayout) -> Result<PathBuf, String> {
    let creator = select_best_python(layout).ok_or_else(|| {
        "No se encontró Python 3.10+ para ejecutar Openspired Desktop. Instálalo desde python.org.".to_string()
    })?;

    if layout.venv_python.exists() {
        let venv_ok = python_version(&layout.venv_python)
            .map(is_supported_python)
            .unwrap_or(false);
        if !venv_ok {
            let _ = fs::remove_dir_all(&layout.venv_dir);
        }
    }

    if !layout.venv_python.exists() {
        run_command(
            {
                let mut cmd = Command::new(&creator);
                cmd.arg("-m").arg("venv").arg(&layout.venv_dir);
                cmd
            },
            "Creating backend virtualenv",
        )?;
    }

    let python = layout.venv_python.clone();

    let runtime_ok = python_version(&python)
        .map(is_supported_python)
        .unwrap_or(false);
    if !runtime_ok {
        return Err(
            "El entorno Python de la app no cumple 3.10+. Borra la app y reinstala Python 3.10+."
                .to_string(),
        );
    }

    if python_has_backend_deps(&python) {
        return Ok(python);
    }

    run_command(
        {
            let mut cmd = Command::new(&python);
            cmd.args(["-m", "pip", "install", "--upgrade", "pip"]);
            cmd
        },
        "Upgrading pip in backend virtualenv",
    )?;
    run_command(
        {
            let mut cmd = Command::new(&python);
            cmd.args(["-m", "pip", "install", "-r"]);
            cmd.arg(&layout.requirements_path);
            cmd
        },
        "Installing backend dependencies",
    )?;

    if python_has_backend_deps(&python) {
        Ok(python)
    } else {
        Err("No fue posible preparar las dependencias Python del backend.".to_string())
    }
}

fn start_backend_process(layout: &RuntimeLayout, python: &Path) -> Result<Child, String> {
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&layout.log_path)
        .map_err(|e| format!("Cannot open backend log file {}: {e}", layout.log_path.display()))?;
    let err_file = log_file
        .try_clone()
        .map_err(|e| format!("Cannot clone backend log handle: {e}"))?;

    let mut cmd = Command::new(python);
    cmd.arg(layout.engine_dir.join("run.py"))
        .arg("--serve-api")
        .current_dir(&layout.bundle_root)
        .env("OPENSPIRED_PROFILE_PATH", &layout.runtime_root)
        .env("WORKSPACE_PATH", &layout.workspace_dir)
        .env("PROJECT_PATH", &layout.runtime_root)
        .env("AGENTS_PATH", &layout.agents_dir)
        .env("OPENSPIRED_REQUIRE_PROFILE", "true")
        .env("OPENSPIRED_ALLOW_EMPTY_CONFIG", "true")
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::from(log_file))
        .stderr(Stdio::from(err_file));

    cmd.spawn()
        .map_err(|e| format!("Cannot spawn backend process: {e}"))
}

fn current_token_or_empty(layout: &RuntimeLayout) -> String {
    fs::read_to_string(&layout.token_path)
        .map(|s| s.trim().to_string())
        .unwrap_or_default()
}

#[tauri::command]
fn bootstrap_local_backend(app: AppHandle, state: State<BackendState>) -> Result<BootstrapResponse, String> {
    let layout = resolve_layout(&app)?;

    if is_api_reachable() {
        let token = wait_for_token(&layout.token_path, Duration::from_secs(2))
            .unwrap_or_else(|| current_token_or_empty(&layout));
        return Ok(BootstrapResponse {
            status: "ready".to_string(),
            api_base_url: "http://127.0.0.1:8765".to_string(),
            api_token: token,
            runtime_root: layout.runtime_root.to_string_lossy().to_string(),
            workspace_dir: layout.workspace_dir.to_string_lossy().to_string(),
            env_path: layout.env_path.to_string_lossy().to_string(),
            log_path: layout.log_path.to_string_lossy().to_string(),
        });
    }

    {
        let mut guard = state
            .child
            .lock()
            .map_err(|_| "Cannot lock backend process state".to_string())?;
        if let Some(child) = guard.as_mut() {
            match child.try_wait() {
                Ok(Some(_)) => {
                    *guard = None;
                }
                Ok(None) => {
                    // Child already running.
                }
                Err(_) => {
                    *guard = None;
                }
            }
        }

        if guard.is_none() {
            let python = ensure_python_ready(&layout)?;
            let child = start_backend_process(&layout, &python)?;
            *guard = Some(child);
        }
    }

    if !wait_for_api(Duration::from_secs(180)) {
        return Err(format!(
            "El backend no inició a tiempo (primer arranque puede tardar). Revisa el log: {}",
            layout.log_path.display()
        ));
    }

    let token = wait_for_token(&layout.token_path, Duration::from_secs(10))
        .unwrap_or_else(|| current_token_or_empty(&layout));

    Ok(BootstrapResponse {
        status: "ready".to_string(),
        api_base_url: "http://127.0.0.1:8765".to_string(),
        api_token: token,
        runtime_root: layout.runtime_root.to_string_lossy().to_string(),
        workspace_dir: layout.workspace_dir.to_string_lossy().to_string(),
        env_path: layout.env_path.to_string_lossy().to_string(),
        log_path: layout.log_path.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn stop_local_backend(state: State<BackendState>) -> Result<(), String> {
    let mut guard = state
        .child
        .lock()
        .map_err(|_| "Cannot lock backend process state".to_string())?;
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}

fn main() {
    let app = tauri::Builder::default()
        .manage(BackendState {
            child: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            bootstrap_local_backend,
            stop_local_backend
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            if let Ok(mut guard) = app_handle.state::<BackendState>().child.lock() {
                if let Some(mut child) = guard.take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
