export type BackendBootstrap = {
  status: string;
  api_base_url: string;
  api_token: string;
  runtime_root: string;
  workspace_dir: string;
  env_path: string;
  log_path: string;
};

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function bootstrapDesktopBackend(): Promise<BackendBootstrap | null> {
  if (!isTauriRuntime()) {
    return null;
  }

  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<BackendBootstrap>("bootstrap_local_backend");
}

export async function restartDesktopBackend(): Promise<BackendBootstrap | null> {
  if (!isTauriRuntime()) {
    return null;
  }

  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("stop_local_backend");
  return invoke<BackendBootstrap>("bootstrap_local_backend");
}

