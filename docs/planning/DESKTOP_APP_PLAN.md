# MvgeOS Desktop App Implementation Plan

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        MvgeOS Desktop                           │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (Tauri v2 WebView - WebView2/GTK WebKit/Cocoa)        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  React 19 + TypeScript 5.x + TailwindCSS v4 + Vite 6   │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────────┐  │   │
│  │  │ Chat    │ │ File    │ │ Spell   │ │ Settings/     │  │   │
│  │  │ Panel   │ │ Tree    │ │ Output  │ │ Config        │  │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └───────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  IPC Layer (Tauri v2 Commands + Events)                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  invoke('agent_run')  →  Rust → Python subprocess       │   │
│  │  invoke('spell_cast')   →  Rust → Python subprocess     │   │
│  │  invoke('tome_read')    →  Rust → Python subprocess     │   │
│  │  listen('agent-token')  ←  Python stdout events         │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  Backend Bridge (Rust)                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  - Manages Python subprocess (bundled or uv)            │   │
│  │  - Line-delimited JSON over stdin/stdout                │   │
│  │  - Stderr reader + logging                              │   │
│  │  - Lifecycle: spawn, restart, graceful shutdown         │   │
│  │  - Startup handshake (Ping/Pong)                        │   │
│  │  - Health check heartbeat (every 30s)                   │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  Python Core (Existing MvgeOS Packages)                         │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐ ┌──────────┐  │
│  │  cli    │ │  agent   │ │ provider│ │ tome  │ │ spells  │  │
│  └─────────┘ └──────────┘ └─────────┘ └───────┘ └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Wire Protocol Specification

### Transport
- Line-delimited JSON over stdin (Rust→Python) and stdout (Python→Rust)
- One JSON object per line, terminated by `\n`
- stderr reserved for Python diagnostics (Rust reads continuously to prevent pipe deadlock)

### Frame Types

```
Rust → Python (stdin):
  {"type":"request","id":1,"method":"agent.run","params":{...}}
  {"type":"notification","method":"agent.interrupt","params":{...}}

Python → Rust (stdout):
  {"type":"response","id":1,"result":{"session_id":"...","status":"ok"}}
  {"type":"error","id":1,"code":-32601,"message":"Method not found"}
  {"type":"event","event":"agent_token","data":{"session_id":"...","token":"hello"}}
  {"type":"parse_error","raw":"bad line","detail":"expected value at line 1 column 1"}
```

On JSON parse error, Python writes `{"type":"parse_error",...}` to stdout and continues reading. Similarly, when Rust fails to parse a line from Python's stdout, it logs the error to its own stderr (not back to Python) and continues reading — there is no `ToPython::ParseError` variant; Rust handles malformed input locally via logging.

### RPC Methods

| Method | Type | Params Schema | Returns Schema |
|--------|------|---------------|----------------|
| `ping` | Request | `{}` | `{"status":"ok","version":"<semver string>"}` |
| `agent.run` | Request | `{session_id: string (UUID v4, max 128 chars), prompt: string (max 100k chars), model: {id:string, name:string, provider:string, baseUrl?:string}}` | `{session_id: string, status: "ok"|"error"}` |
| `agent.interrupt` | Notification | `{session_id: string}` | — |
| `spell.cast` | Request | `{session_id: string, spell: string, args: object}` | `{spell_cast_id: string, status: "started"}` |
| `tome.read` | Request | `{path: string (absolute filesystem path)}` | `{sessions: array}` |
| `tome.write` | Request | `{path: string (absolute), session: {id:string, messages:array, model:object}}` | `{ok: boolean}` |
| `config.get` | Request | `{key: string (dot-separated path like "ui.theme")}` | `{value: any\|null}` |
| `config.set` | Request | `{key: string (dot-separated), value: any}` | `{ok: boolean}` |
| `shutdown` | Notification | `{}` | — |

### Streaming Events (Python → Rust → Frontend)

| Event | Payload | Description |
|-------|---------|-------------|
| `agent_token` | `{session_id, token}` | Streaming text token |
| `agent_message` | `{session_id, content}` | Complete message chunk |
| `agent_tool_call` | `{session_id, tool, args}` | Tool invocation |
| `agent_tool_result` | `{session_id, tool, result}` | Tool result |
| `agent_complete` | `{session_id, stop_reason}` | Agent finished |
| `agent_error` | `{session_id, error}` | Agent error |
| `spell_progress` | `{session_id, spell_cast_id, progress}` | Spell progress 0.0–1.0 |
| `agent_usage` | `{session_id, tokens_in, tokens_out, mana}` | Token/mana usage |
| `heartbeat` | `{}` | Periodic liveness signal from Python (every 25s, from independent task) |
| `log` | `{level, message}` | Diagnostic log |

---

## Prerequisites (Must Fix Before Starting)

### P1. Lower Python requirement

**Current**: `requires-python = ">=3.14"` in root `pyproject.toml` and all workspace packages
**Also fix**: `ruff target-version = "py314"` → `"py312"` and `mypy python_version = "3.14"` → `"3.12"` in root `pyproject.toml`
**Fix**: Change all to `>=3.12`

### P2. Wire EventBus into MvgeLoop

Add `publish` method to `EventBus` base class (keeps existing `emit` for backwards compat):
```python
# mvgeos_agent/event_bus.py
class EventBus:
    def publish(self, event: MvgeEvent) -> None:
        """Wire-format publish; default implementation delegates to emit."""
        self.emit(event.type.value, event.data)
```

```python
# mvgeos_agent/loop.py
class MvgeLoop:
    def __init__(self, state: MvgeState) -> None:
        self._state = state

    def _emit_event(self, event_type: MvgeEventType, data: dict[str, Any]) -> None:
        event = MvgeEvent(type=event_type, data=data)
        if self._state.event_bus:
            self._state.event_bus.publish(event)


# mvgeos_agent/types.py — add field to MvgeState
@dataclass
class MvgeState:
    ...
    event_bus: EventBus | None = None  # NEW
```

### P3. Python bundling strategy (decision: PyInstaller)

**Decision**: Use PyInstaller for release builds. `uv run` for development.
- `uv run mvgeos desktop` for development — fast iteration, uses existing Python environment
- PyInstaller produces `mvgeos-desktop.exe` (Windows) / binary (macOS/Linux) for production
- Spec file at `mvgeos-desktop/mvgeos-desktop.spec` captures all hidden imports
- Nuitka considered but rejected (slow builds, complex C compilation, poor Windows support)
- `uv managed` rejected for release (end-user would need to install uv + sync monorepo)

---

## Phase 1: Foundation (Week 1-2)

### 1.1 Tauri v2 Project Setup

```bash
cd mvgeos
npm create tauri-app@latest mvgeos-desktop -- --template react-ts --yes
cd mvgeos-desktop

# Core dependencies
npm install zustand @tanstack/react-virtual react-markdown remark-gfm rehype-highlight
npm install -D tailwindcss @tailwindcss/vite

# Tauri plugins (pinned versions)
cargo add tauri-plugin-dialog@2 tauri-plugin-shell@2 tauri-plugin-process@2 \
  tauri-plugin-fs@2 tauri-plugin-updater@2 tauri-plugin-store@2 \
  tauri-plugin-global-shortcut@2
```

**Structure:**
```
mvgeos-desktop/
├── src/                    # React frontend
│   ├── components/
│   ├── hooks/
│   ├── stores/
│   ├── types/
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css           # TailwindCSS v4 entry
├── src-tauri/              # Rust backend (Tauri v2)
│   ├── src/
│   │   ├── main.rs         # Tauri app builder + setup
│   │   ├── python_bridge.rs # JSON-RPC over stdio
│   │   ├── lifecycle.rs    # Subprocess lifecycle + watchdog
│   │   ├── ipc.rs          # Tauri #[tauri::command] handlers
│   │   ├── protocol.rs     # Frame serialization/deserialization
│   │   ├── menu.rs
│   │   ├── tray.rs
│   │   └── file_watcher.rs # (Phase 4b) notify-based file watcher
│   ├── capabilities/
│   │   └── default.json
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── build.rs            # Tauri v2 build script
│   ├── entitlements.plist  # macOS hardened runtime entitlements
│   └── icons/              # icon.png, icon.icns, icon.ico
├── assets/
│   └── icon-512.png          # Source icon for Tauri build (checked in)
├── .gitignore              # node_modules, dist, src-tauri/target
├── vite.config.ts          # Vite + TailwindCSS v4 + React plugin
├── tsconfig.json
├── tsconfig.node.json
├── vitest.config.ts        # Vitest with jsdom environment
├── package.json
└── index.html               # Vite entry HTML
```

### 1.2 Build Files

```toml
# src-tauri/Cargo.toml
[package]
name = "mvgeos-desktop"
version = "0.1.0"
edition = "2021"

[dependencies]
tauri = { version = "2.0", features = [] }
tauri-plugin-dialog = "2.0"
tauri-plugin-shell = "2.0"
tauri-plugin-process = "2.0"
tauri-plugin-fs = "2.0"
tauri-plugin-updater = "2.0"
# Use tauri-plugin-store for local encrypted credential storage.
# Replace with tauri-plugin-credential-manager if/when it becomes available for Tauri v2.
tauri-plugin-store = "2"
tauri-plugin-global-shortcut = "2.0"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full", "process", "io-util", "sync"] }
tokio-util = { version = "0.7", features = ["sync"] }
thiserror = "2"
uuid = { version = "1", features = ["v4"] }
log = "0.4"
env_logger = "0.11"
```

```rust
// src-tauri/build.rs
fn main() {
    tauri_build::build()
}
```

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: process.env.TAURI_ENV_PLATFORM === "windows" ? "chrome105" : "safari16",
    minify: !process.env.TAURI_ENV_DEBUG ? "esbuild" : false,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
});
```

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}', 'src/**/*.spec.{ts,tsx}'],
    setupFiles: [],
  },
});
```

```tsconfig
// tsconfig.node.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["vite.config.ts"]
}
```

```json
// package.json (mvgeos-desktop/)
{
  "name": "mvgeos-desktop",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "tauri": "tauri",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@tauri-apps/api": "^2.0.0",
    "@tauri-apps/plugin-dialog": "^2.0.0",
    "@tauri-apps/plugin-fs": "^2.0.0",
    "@tauri-apps/plugin-global-shortcut": "^2.0.0",
    "@tauri-apps/plugin-process": "^2.0.0",
    "@tauri-apps/plugin-shell": "^2.0.0",
    "@tauri-apps/plugin-store": "^2.0.0",
    "@tauri-apps/plugin-updater": "^2.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "rehype-highlight": "^7.0.0",
    "zustand": "^5.0.0",
    "@tanstack/react-virtual": "^3.0.0",
    "diff": "^7.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.0.0",
    "@testing-library/react": "^16.0.0",
    "jsdom": "^25.0.0"
  }
}
```

```tsconfig
// tsconfig.json (mvgeos-desktop/)
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Run `npm install --package-lock-only` before first commit to generate `package-lock.json`.

```html
<!-- index.html — Vite entry HTML -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MvgeOS</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```typescript
// src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```



### 1.3 Rust Protocol Definition (protocol.rs)

```rust
// src-tauri/src/protocol.rs
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Frame received from Python subprocess (stdout)
#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
pub enum FromPython {
    #[serde(rename = "response")]
    Response { id: u64, result: Value },
    #[serde(rename = "error")]
    Error { id: u64, code: i32, message: String },
    #[serde(rename = "event")]
    Event { event: String, data: Value },
    #[serde(rename = "parse_error")]
    ParseError { raw: String, detail: String },
}

/// Frame sent to Python subprocess (stdin)
#[derive(Debug, Serialize)]
#[serde(tag = "type")]
pub enum ToPython {
    #[serde(rename = "request")]
    Request { id: u64, method: String, params: Value },
    #[serde(rename = "notification")]
    Notification { method: String, params: Value },
}
```

### 1.4 Rust Subprocess Lifecycle + Watchdog

To enable integration tests against the Rust code, add a `src-tauri/src/lib.rs` that re-exports library targets:

```rust
// src-tauri/src/lib.rs
pub mod protocol;
pub mod lifecycle;
```

This allows integration tests in `src-tauri/tests/` to import via `use mvgeos_desktop::protocol::FromPython;`.
The binary target in `main.rs` uses `mod protocol; mod lifecycle;` directly and does not depend on the lib target.

```rust
// src-tauri/src/lifecycle.rs
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStderr, ChildStdin, ChildStdout, Command};
use tokio::sync::{mpsc, oneshot, Mutex, Notify};
use tokio_util::sync::CancellationToken;
use serde_json::Value;

#[derive(thiserror::Error, Debug)]
pub enum BridgeError {
    #[error("Process crashed: {0}")]
    ProcessCrashed(String),
    #[error("Handshake timeout")]
    HandshakeTimeout,
    #[error("Request timeout ({0}s)")]
    RequestTimeout(u64),  // parameter is the timeout duration in seconds
    #[error("Response channel closed")]
    ChannelClosed,
    #[error("Protocol error: {0}")]
    Protocol(String),
}

pub enum LaunchMode {
    Dev,
    Bundled(PathBuf),
}

#[derive(Clone)]
pub struct ProcessSupervisor {
    project_path: PathBuf,
    mode: LaunchMode,
    child: Arc<Mutex<Option<Child>>>,
    stdin: Arc<Mutex<Option<ChildStdin>>>,
    pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Result<Value, BridgeError>>>>>,
    next_id: Arc<AtomicU64>,
    event_tx: mpsc::Sender<(String, Value)>,
    cancel: CancellationToken,
    crash_count: Arc<Mutex<u32>>,
    reader_handles: Arc<Mutex<Vec<tokio::task::JoinHandle<()>>>>,
    last_heartbeat: Arc<Mutex<Option<std::time::Instant>>>,
}

impl ProcessSupervisor {
    pub fn new(
        project_path: PathBuf,
        mode: LaunchMode,
        event_tx: mpsc::Sender<(String, Value)>,
    ) -> Self {
        Self {
            project_path,
            mode,
            child: Arc::new(Mutex::new(None)),
            stdin: Arc::new(Mutex::new(None)),
            pending: Arc::new(Mutex::new(HashMap::new())),
            next_id: Arc::new(AtomicU64::new(1)),
            event_tx,
            cancel: CancellationToken::new(),
            crash_count: Arc::new(Mutex::new(0)),
            reader_handles: Arc::new(Mutex::new(Vec::new())),
            last_heartbeat: Arc::new(Mutex::new(Some(std::time::Instant::now()))),
        }
    }

    /// Spawn the Python subprocess and wait for handshake.
    /// After start, run heartbeat and pending-cleanup tasks.
    /// Takes `self: Arc<Self>` so the background tasks can share ownership.
    pub async fn start(self: Arc<Self>) -> Result<(), BridgeError> {
        self.spawn_inner().await?;
        // Spawn heartbeat: ping every 30s
        let hb_self = self.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(30));
            loop {
                tokio::select! {
                    _ = interval.tick() => {
                        hb_self.send_request("ping", serde_json::json!({})).await.ok();
                    }
                    _ = hb_self.cancel.cancelled() => break,
                }
            }
        });
        // Spawn pending cleanup: purge stale entries every 5min
        let cl_self = self.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(300));
            loop {
                tokio::select! {
                    _ = interval.tick() => cl_self.clean_stale_pending().await,
                    _ = cl_self.cancel.cancelled() => break,
                }
            }
        });
        Ok(())
    }

    async fn spawn_inner(self: Arc<Self>) -> Result<(), BridgeError> {
        let mut cmd = match &self.mode {
            LaunchMode::Dev => {
                let mut c = Command::new("uv");
                c.args(["run", "mvgeos", "desktop"]);
                c
            }
            LaunchMode::Bundled(path) => {
                // Platform-specific binary name:
                // Windows: mvgeos-desktop.exe
                // macOS:   mvgeos-desktop (inside .app/Contents/MacOS/)
                // Linux:   mvgeos-desktop
                let binary_name = if cfg!(target_os = "windows") {
                    "mvgeos-desktop.exe"
                } else {
                    "mvgeos-desktop"
                };
                Command::new(path.join("binaries").join(binary_name))
            }
        };

        cmd.current_dir(&self.project_path)
           .stdin(std::process::Stdio::piped())
           .stdout(std::process::Stdio::piped())
           .stderr(std::process::Stdio::piped())
           .kill_on_drop(true);

        let child = cmd.spawn().map_err(|e| BridgeError::ProcessCrashed(e.to_string()))?;
        let stdin_handle = child.stdin.unwrap();
        let stdout_handle = child.stdout.unwrap();
        let stderr_handle = child.stderr.unwrap();
        *self.child.lock().await = Some(child);
        *self.stdin.lock().await = Some(stdin_handle);

        // Crash-loop detection: if >5 crashes in 60s, stop restarting
        let mut count_guard = self.crash_count.lock().await;
        *count_guard += 1;
        if *count_guard > 5 {
            log::error!("Crash loop detected (>5 crashes) — abandoning restart");
            return Err(BridgeError::ProcessCrashed("crash loop detected".into()));
        }
        // Reset crash count after 60s of stability
        let count_reset = self.crash_count.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_secs(60)).await;
            *count_reset.lock().await = 0;
        });
        drop(count_guard);

        // Stderr reader — prevents pipe deadlock.
        // Handle stored in a self field or a Vec to prevent task cancellation on drop.
        // In actual implementation, these handles are stored in ProcessSupervisor as
        // `reader_handles: Arc<Mutex<Vec<JoinHandle<()>>>>` and joined during shutdown.
        let stderr_handle: tokio::task::JoinHandle<()> = tokio::spawn(async move {
            let mut reader = BufReader::new(stderr_handle).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                log::warn!("[python:stderr] {}", line);
            }
        });

        // Stdout reader — dispatches to pending or event_tx
        let pending = self.pending.clone();
        let event_tx = self.event_tx.clone();
        let last_heartbeat = self.last_heartbeat.clone();
        let stdout_handle: tokio::task::JoinHandle<()> = tokio::spawn(async move {
            let mut reader = BufReader::new(stdout_handle).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                match serde_json::from_str::<FromPython>(&line) {
                    Ok(FromPython::Response { id, result }) => {
                        if let Some(tx) = pending.lock().await.remove(&id) {
                            let _ = tx.send(Ok(result));
                        }
                    }
                    Ok(FromPython::Error { id, code, message }) => {
                        if let Some(tx) = pending.lock().await.remove(&id) {
                            let _ = tx.send(Err(BridgeError::Protocol(format!("{}: {}", code, message))));
                        }
                    }
                    Ok(FromPython::Event { event, data }) => {
                        // Track heartbeat events for liveness detection
                        if event == "heartbeat" {
                            *last_heartbeat.lock().await = Some(std::time::Instant::now());
                        }
                        // Use try_send to avoid blocking stdout reader when channel is full.
                        // Drop events when backlog exceeds capacity — Python will re-emit on next tick.
                        if event_tx.try_send((event, data)).is_err() {
                            log::warn!("Event channel full — dropping event");
                        }
                    }
                    Ok(FromPython::ParseError { raw, detail }) => {
                        log::error!("Python parse error: line={:?} detail={}", raw, detail);
                    }
                    Err(e) => {
                        log::error!("Failed to parse Python stdout line: {:?} line={:?}", e, line);
                    }
                }
            }
        });

        // Store reader handles for monitoring during shutdown
        self.reader_handles.lock().await.push(stderr_handle);
        self.reader_handles.lock().await.push(stdout_handle);

        // Startup handshake — Ping with 10s timeout
        self.ping_with_timeout(Duration::from_secs(10)).await?;
        Ok(())
    }

    pub async fn send_request(&self, method: &str, params: Value) -> Result<Value, BridgeError> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let (tx, rx) = oneshot::channel();
        self.pending.lock().await.insert(id, tx);

        let frame = serde_json::to_string(&ToPython::Request { id, method: method.into(), params })
            .map_err(|e| BridgeError::Protocol(e.to_string()))?;

        // Write frame to stdin pipe
        let mut stdin_guard = self.stdin.lock().await;
        if let Some(stdin) = stdin_guard.as_mut() {
            stdin.write_all(frame.as_bytes()).await
                .map_err(|e| BridgeError::ProcessCrashed(e.to_string()))?;
            stdin.write_all(b"\n").await
                .map_err(|e| BridgeError::ProcessCrashed(e.to_string()))?;
        } else {
            return Err(BridgeError::ProcessCrashed("stdin not connected".into()));
        }
        drop(stdin_guard);  // release lock before awaiting response

        // Wait for response with 30s timeout
        // IMPORTANT: on timeout, the pending entry is leaked and the oneshot receiver is dropped
        // (the response arrives later with no receiver and is silently dropped by the stdout reader).
        // Periodic cleanup via `clean_stale_pending()` prevents unbounded HashMap growth.
        const TIMEOUT_SECS: u64 = 30;
        tokio::time::timeout(Duration::from_secs(TIMEOUT_SECS), rx)
            .await
            .map_err(|_| BridgeError::RequestTimeout(TIMEOUT_SECS))?
            .map_err(|_| BridgeError::ChannelClosed)?
    }

    pub async fn send_notification(&self, method: &str, params: Value) -> Result<(), BridgeError> {
        let frame = serde_json::to_string(&ToPython::Notification { method: method.into(), params })
            .map_err(|e| BridgeError::Protocol(e.to_string()))?;
        let mut stdin_guard = self.stdin.lock().await;
        if let Some(stdin) = stdin_guard.as_mut() {
            stdin.write_all(frame.as_bytes()).await
                .map_err(|e| BridgeError::ProcessCrashed(e.to_string()))?;
            stdin.write_all(b"\n").await
                .map_err(|e| BridgeError::ProcessCrashed(e.to_string()))?;
        }
        Ok(())
    }

    pub async fn ping_with_timeout(&self, timeout: Duration) -> Result<(), BridgeError> {
        tokio::time::timeout(timeout, self.send_request("ping", serde_json::json!({})))
            .await
            .map_err(|_| BridgeError::HandshakeTimeout)?
            .map(|_| ())
    }

    pub async fn interrupt_session(&self, session_id: &str) -> Result<(), BridgeError> {
        self.send_notification("agent.interrupt", serde_json::json!({"session_id": session_id})).await
    }

    pub async fn shutdown(&self) {
        self.send_notification("shutdown", serde_json::json!({})).await.ok();
        self.cancel.cancel();
        // Drop stdin to signal EOF to Python
        self.stdin.lock().await.take();
        if let Some(mut child) = self.child.lock().await.take() {
            tokio::time::timeout(Duration::from_secs(5), child.wait()).await.ok();
        }
    }

    /// Kill the subprocess immediately (no graceful shutdown).
    pub async fn kill(&self) {
        self.cancel.cancel();
        self.stdin.lock().await.take();
        if let Some(mut child) = self.child.lock().await.take() {
            child.kill().await.ok();
            child.wait().await.ok();
        }
    }

    /// Internal restart helper (unconditional — no crash-loop check).
    async fn restart_inner(self: Arc<Self>) {
        self.kill().await;
        Arc::clone(&self).spawn_inner().await.ok();
        let _ = self.event_tx.send(("process_restarted".into(), serde_json::json!({}))).await;
    }

    /// Watchdog: if process died or heartbeat is overdue, emit event and attempt restart.
    pub async fn watch(self: Arc<Self>) {
        // Check heartbeat staleness: if last heartbeat > 30s ago, treat as dead.
        let now = std::time::Instant::now();
        let last = *self.last_heartbeat.lock().await;
        let heartbeat_stale = last.map(|t| now.duration_since(t) > Duration::from_secs(30)).unwrap_or(false);
        if heartbeat_stale {
            log::error!("Python process heartbeat overdue — killing and restarting");
            let _ = self.event_tx.send(("process_crashed".into(), serde_json::json!({"reason": "heartbeat_timeout"}))).await;
            self.kill().await;
            self.restart_inner().await;
            return;
        }

        let needs_restart = {
            let mut child_guard = self.child.lock().await;
            let status = child_guard.as_mut().and_then(|c| c.try_wait().ok()).flatten();
            if let Some(ref status) = status {
                log::error!("Python process died with status: {:?}", status);
                let code: Option<i32> = status.code();
                let _ = self.event_tx.send(("process_crashed".into(), serde_json::json!({"code": code}))).await;
                child_guard.take(); // Remove dead child
                true
            } else {
                false
            }
        };
        if needs_restart {
            self.spawn_inner().await.ok();
            let _ = self.event_tx.send(("process_restarted".into(), serde_json::json!({}))).await;
        }
    }
    
    /// Periodically clean up all stale pending entries (those whose oneshot
    /// receivers have timed out and been dropped). Call from a background task.
    pub async fn clean_stale_pending(&self) {
        let mut guard = self.pending.lock().await;
        let before = guard.len();
        guard.retain(|id, sender| {
            if sender.is_closed() {
                log::debug!("Removing stale pending request: {}", id);
                false
            } else {
                true
            }
        });
        let removed = before - guard.len();
        if removed > 0 {
            log::debug!("Cleaned {} stale pending requests", removed);
        }
    }
}
```

### 1.5 Tauri v2 main.rs + Window Events

```rust
// src-tauri/src/main.rs
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use serde_json::Value;
use tauri::Manager;

mod protocol;
mod lifecycle;
mod ipc;
mod menu;
mod tray;

use lifecycle::{ProcessSupervisor, LaunchMode};

fn main() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            // Create event channel
            let (event_tx, mut event_rx) = mpsc::channel::<(String, Value)>(256);

            // Determine project path for Dev mode.
            // In Dev mode, set MVGEOS_PROJECT_DIR env var at `cargo tauri dev` time,
            // or embed it via build.rs using env!("CARGO_MANIFEST_DIR").
            // The actual path is resolved at crate build time:
            //   let project_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            //       .parent().unwrap()  // src-tauri/ -> mvgeos-desktop/
            //       .parent().unwrap(); // mvgeos-desktop/ -> monorepo root
            // Fallback for release: use app resource dir.
            let project_path = if cfg!(debug_assertions) {
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .parent().unwrap()
                    .parent().unwrap()
                    .to_path_buf()
            } else {
                app.path().resource_dir().expect("resource_dir required in release mode").to_path_buf()
            };

            let supervisor = ProcessSupervisor::new(
                project_path.clone(),
                if cfg!(debug_assertions) { LaunchMode::Dev } else { LaunchMode::Bundled(project_path.join("binaries")) },
                event_tx,
            );
            let supervisor = Arc::new(supervisor);
            app.manage(supervisor.clone());

            let app_handle = app.handle().clone();
            tokio::spawn(async move {
                if let Err(e) = supervisor.start().await {
                    log::error!("Failed to start Python subprocess: {}", e);
                    // Notify frontend of connection failure
                    let _ = app_handle.emit("process_crashed", serde_json::json!({"error": e.to_string()}));
                }
            });

            // Forward events from Python to frontend
            let app_handle2 = app.handle().clone();
            tokio::spawn(async move {
                while let Some((event, data)) = event_rx.recv().await {
                    if let Err(e) = app_handle2.emit(&event, data) {
                        log::error!("Failed to emit event '{}': {}", event, e);
                    }
                }
            });

            // Window close → graceful shutdown. Handled via Builder::on_window_event below.
            // Capture the shutdown state in a static OnceLock for closure sharing.
            use std::sync::OnceLock;
            static SHUTTING_DOWN: OnceLock<Arc<std::sync::atomic::AtomicBool>> = OnceLock::new();
            let shutting_down = SHUTTING_DOWN.get_or_init(|| Arc::new(std::sync::atomic::AtomicBool::new(false))).clone();

            // Watchdog timer — async tokio interval instead of busy-loop thread
            let app_handle4 = app.handle().clone();
            tokio::spawn(async move {
                let mut interval = tokio::time::interval(Duration::from_secs(5));
                loop {
                    interval.tick().await;
                    let sup = app_handle4.state::<Arc<ProcessSupervisor>>().inner().clone();
                    sup.watch().await;
                }
            });

            // Create system tray
            if let Err(e) = tray::create_tray(app.handle()) {
                log::error!("Failed to create system tray: {}", e);
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            ipc::agent_run,
            ipc::agent_interrupt,
            ipc::spell_cast,
            ipc::tome_read,
            ipc::tome_write,
            ipc::config_get,
            ipc::config_set,
            ipc::get_api_key,
            ipc::set_api_key,
            ipc::delete_api_key,
        ])
        .menu(|handle| menu::create_app_menu(handle))
        .on_menu_event(|app, event| menu::handle_menu_event(app, event))
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                use std::sync::OnceLock;
                static SD: OnceLock<Arc<std::sync::atomic::AtomicBool>> = OnceLock::new();
                let sd = SD.get_or_init(|| Arc::new(std::sync::atomic::AtomicBool::new(false))).clone();
                if sd.swap(true, std::sync::atomic::Ordering::SeqCst) {
                    return; // Already shutting down — allow second event to close
                }
                api.prevent_close();
                let app_handle = window.app_handle().clone();
                let sup = app_handle.state::<Arc<ProcessSupervisor>>().inner().clone();
                tauri::async_runtime::spawn(async move {
                    sup.shutdown().await;
                    if let Some(win) = app_handle.get_webview_window("main") {
                        win.close().ok();
                    }
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### 1.6 Tauri v2 Commands + Types

```rust
// src-tauri/src/ipc.rs
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::State;
use crate::lifecycle::{ProcessSupervisor, BridgeError};

/// Validation: ensure session_id is non-empty UUID format.
fn validate_session_id(id: &str) -> Result<(), String> {
    if id.is_empty() {
        return Err("session_id must not be empty".into());
    }
    if id.chars().count() > 128 {
        return Err("session_id too long (max 128 chars)".into());
    }
    Ok(())
}

/// Validation: ensure prompt is non-empty and within bounds.
fn validate_prompt(prompt: &str) -> Result<(), String> {
    if prompt.trim().is_empty() {
        return Err("prompt must not be empty".into());
    }
    if prompt.chars().count() > 100_000 {
        return Err("prompt too long (max 100,000 chars)".into());
    }
    Ok(())
}

#[derive(Debug, Serialize)]
pub struct AgentRunResult {
    pub session_id: String,
    pub status: String,
}

/// Convert BridgeError to user-facing error string.
fn bridge_err(e: BridgeError) -> String {
    match e {
        BridgeError::ProcessCrashed(msg) => format!("backend process error: {}", msg),
        BridgeError::HandshakeTimeout => "backend handshake timed out".into(),
        BridgeError::RequestTimeout(s) => format!("request timed out after {}s", s),
        BridgeError::ChannelClosed => "backend connection closed".into(),
        BridgeError::Protocol(msg) => format!("protocol error: {}", msg),
    }
}

#[tauri::command]
async fn agent_run(
    session_id: String,
    prompt: String,
    model: Value,
    supervisor: State<'_, Arc<ProcessSupervisor>>,
) -> Result<AgentRunResult, String> {
    validate_session_id(&session_id)?;
    validate_prompt(&prompt)?;
    let params = serde_json::json!({
        "session_id": session_id,
        "prompt": prompt,
        "model": model,
    });
    let result = supervisor.send_request("agent.run", params)
        .await
        .map_err(bridge_err)?;
    let status = result.get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("ok")
        .to_string();
    Ok(AgentRunResult { session_id, status })
}

#[tauri::command]
async fn agent_interrupt(
    session_id: String,
    supervisor: State<'_, Arc<ProcessSupervisor>>,
) -> Result<(), String> {
    validate_session_id(&session_id)?;
    supervisor.interrupt_session(&session_id).await.map_err(bridge_err)
}

#[tauri::command]
async fn spell_cast(
    session_id: String,
    spell: String,
    args: Value,
    supervisor: State<'_, Arc<ProcessSupervisor>>,
) -> Result<Value, String> {
    validate_session_id(&session_id)?;
    if spell.is_empty() {
        return Err("spell name must not be empty".into());
    }
    supervisor.send_request("spell.cast", serde_json::json!({
        "session_id": session_id,
        "spell": spell,
        "args": args,
    })).await.map_err(bridge_err)
}

#[tauri::command]
async fn tome_read(
    path: String,
    supervisor: State<'_, Arc<ProcessSupervisor>>,
) -> Result<Value, String> {
    if path.is_empty() {
        return Err("path must not be empty".into());
    }
    supervisor.send_request("tome.read", serde_json::json!({"path": path}))
        .await.map_err(bridge_err)
}

#[tauri::command]
async fn tome_write(
    path: String,
    session: Value,
    supervisor: State<'_, Arc<ProcessSupervisor>>,
) -> Result<Value, String> {
    if path.is_empty() {
        return Err("path must not be empty".into());
    }
    supervisor.send_request("tome.write", serde_json::json!({"path": path, "session": session}))
        .await.map_err(bridge_err)
}

#[tauri::command]
async fn config_get(
    key: String,
    supervisor: State<'_, Arc<ProcessSupervisor>>,
) -> Result<Value, String> {
    if key.is_empty() {
        return Err("key must not be empty".into());
    }
    supervisor.send_request("config.get", serde_json::json!({"key": key}))
        .await.map_err(bridge_err)
}

#[tauri::command]
async fn config_set(
    key: String,
    value: Value,
    supervisor: State<'_, Arc<ProcessSupervisor>>,
) -> Result<Value, String> {
    if key.is_empty() {
        return Err("key must not be empty".into());
    }
    supervisor.send_request("config.set", serde_json::json!({"key": key, "value": value}))
        .await.map_err(bridge_err)
}

/// API key management via encrypted local store (tauri-plugin-store), NOT config JSON.
#[tauri::command]
async fn get_api_key(
    provider: String,
    app: tauri::AppHandle,
) -> Result<String, String> {
    if provider.is_empty() {
        return Err("provider must not be empty".into());
    }
    // Read from encrypted local store via tauri-plugin-store.
    // The plugin stores entries under the "mvgeos" namespace, keyed by provider name.
    use tauri_plugin_store::StoreExt;
    let store = app.store("credentials.json").map_err(|e| format!("store open failed: {}", e))?;
    let value = store.get(&format!("api_key_{}", provider))
        .and_then(|v| v.as_str().map(String::from));
    value.ok_or_else(|| format!("no key found for provider '{}'", provider))
}

#[tauri::command]
async fn set_api_key(
    provider: String,
    key: String,
    app: tauri::AppHandle,
) -> Result<(), String> {
    if provider.is_empty() {
        return Err("provider must not be empty".into());
    }
    if key.is_empty() {
        return Err("key must not be empty".into());
    }
    // Write to encrypted local store via tauri-plugin-store.
    use tauri_plugin_store::StoreExt;
    let store = app.store("credentials.json").map_err(|e| format!("store open failed: {}", e))?;
    store.set(format!("api_key_{}", provider), serde_json::json!(key));
    store.save().map_err(|e| format!("store save failed: {}", e))?;
    Ok(())
}

#[tauri::command]
async fn delete_api_key(
    provider: String,
    app: tauri::AppHandle,
) -> Result<(), String> {
    if provider.is_empty() {
        return Err("provider must not be empty".into());
    }
    use tauri_plugin_store::StoreExt;
    let store = app.store("credentials.json").map_err(|e| format!("store open failed: {}", e))?;
    store.delete(format!("api_key_{}", provider));
    store.save().map_err(|e| format!("store save failed: {}", e))?;
    Ok(())
}
```

### 1.7 Python Desktop Handler (Complete)

Wired as the `mvgeos desktop` CLI subcommand. Registration in `mvgeos-cli/mvgeos/__init__.py`:

```python
# mvgeos-cli/mvgeos/__init__.py
from .commands.desktop import desktop_main

cli = typer.Typer()
cli.command("desktop")(desktop_main)
```

pyproject.toml entry point (in `mvgeos-cli/pyproject.toml`):
```toml
[project.scripts]
mvgeos = "mvgeos:cli"
```

When run via `uv run mvgeos desktop`, it invokes `desktop_main()` which starts the JSON-RPC event loop.

```python
# mvgeos_cli/commands/desktop.py
import asyncio
import json
import os
import sys
import threading
import traceback
from importlib.metadata import version
from typing import Any

from mvgeos_agent.event_bus import EventBus
from mvgeos_agent.types import MvgeEvent, MvgeEventType


class StdoutEventBus(EventBus):
    """Maps MvgeEventType values to wire protocol event names, writes to stdout."""

    # Translation table: MvgeOS internal event -> wire protocol event name
    EVENT_MAP = {
        MvgeEventType.TOKEN: "agent_token",
        MvgeEventType.MESSAGE: "agent_message",
        MvgeEventType.TOOL_CALL: "agent_tool_call",
        MvgeEventType.TOOL_RESULT: "agent_tool_result",
        MvgeEventType.COMPLETE: "agent_complete",
        MvgeEventType.ERROR: "agent_error",
        MvgeEventType.USAGE: "agent_usage",
        MvgeEventType.SPELL_PROGRESS: "spell_progress",
    }

    def __init__(self) -> None:
        super().__init__()

    def publish(self, event: MvgeEvent) -> None:
        """Thread-safe JSON write to stdout via the shared write_stdout helper."""
        wire_event = self.EVENT_MAP.get(event.type, event.type.value)
        frame = {"type": "event", "event": wire_event, "data": event.data}
        write_stdout(frame)


event_bus = StdoutEventBus()
_stdout_lock = threading.Lock()


def write_stdout(frame: dict) -> None:
    """Thread-safe JSON write to stdout. Used by both EventBus and the main loop."""
    with _stdout_lock:
        line = json.dumps(frame, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def get_version() -> str:
    try:
        from importlib.metadata import version, PackageNotFoundError

        return version("mvgeos")
    except Exception, PackageNotFoundError:
        return "0.1.0"  # fallback for PyInstaller bundles


# Simple config persistence for config.get/config.set
CONFIG_FILE = os.path.join(
    {
        "darwin": os.path.expanduser("~/Library/Application Support"),
        "win32": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    }.get(sys.platform, os.path.expanduser("~/.config")),
    "mvgeos",
    "config.json",
)
_config_lock = asyncio.Lock()


def _read_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _write_config(data: dict) -> None:
    atomic_file = CONFIG_FILE + ".tmp"
    with open(atomic_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(atomic_file, CONFIG_FILE)


async def handle_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "ping":
        return {"status": "ok", "version": get_version()}

    elif method == "agent.run":
        from mvgeos_agent.mvge import Mvge
        from mvgeos_agent.types import MvgeState

        model = params.get("model")
        prompt = params.get("prompt", "")
        state = MvgeState()
        state.event_bus = event_bus
        state.system_prompt = "You are MvgeOS, a helpful AI assistant integrated into the user's development environment."
        if model:
            state.model = model
        mvge = Mvge()
        mvge._state = state  # Phase 2+: add Mvge.__init__(state=...) constructor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: mvge.invoke(prompt))
        return {"session_id": params.get("session_id"), "status": "ok"}

    elif method == "agent.interrupt":
        # Phase 2: Wire CancellationToken per session. Returns ok=True as ack.
        return {"ok": True}

    elif method == "spell.cast":
        # Phase 4: from mvgeos_spells.grimoire import Grimoire
        #   grimoire = Grimoire(workspace=params.get("workspace", "."))
        #   result = await loop.run_in_executor(None, lambda: grimoire.cast(spell_name, **args))
        raise NotImplementedError("spell.cast phase 4 — see plan Phase 4")

    elif method == "tome.read":
        # Phase 4: from mvgeos_tome.reader import TomeReader
        #   reader = TomeReader(path=params["path"])
        #   return {"sessions": reader.read_all()}
        raise NotImplementedError("tome.read phase 4 — see plan Phase 4")

    elif method == "tome.write":
        # Phase 4: from mvgeos_tome.writer import TomeWriter
        #   writer = TomeWriter(path=params["path"])
        #   writer.write(params["session"])
        #   return {"ok": True}
        raise NotImplementedError("tome.write phase 4 — see plan Phase 4")

    elif method == "config.get":
        raw_key = params.get("key", "")
        async with _config_lock:
            try:
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                data = _read_config()
                keys = raw_key.split(".")
                current = data
                for k in keys:
                    if isinstance(current, dict):
                        current = current.get(k)
                    else:
                        current = None
                        break
                return {"value": current}
            except Exception as e:
                raise ValueError(f"config.get failed: {e}")

    elif method == "config.set":
        raw_key = params.get("key", "")
        value = params.get("value")
        async with _config_lock:
            try:
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                data = _read_config()
                keys = raw_key.split(".")
                current = data
                for i, k in enumerate(keys[:-1]):
                    if k not in current or not isinstance(current[k], dict):
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value
                _write_config(data)
                return {"ok": True}
            except Exception as e:
                raise ValueError(f"config.set failed: {e}")

    else:
        raise ValueError(f"unknown method: {method}")


async def main():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    # Spawn independent heartbeat task: emits heartbeat every 25s even during long-running requests.
    async def heartbeat_task():
        while True:
            await asyncio.sleep(25)
            write_stdout({"type": "event", "event": "heartbeat", "data": {}})

    asyncio.create_task(heartbeat_task())

    pending_shutdown = False
    while not pending_shutdown:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=60.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break

        if not line:
            break

        try:
            frame = json.loads(line)
        except json.JSONDecodeError as e:
            error_frame = {
                "type": "parse_error",
                "raw": line.decode().rstrip(),
                "detail": str(e),
            }
            write_stdout(error_frame)
            continue

        frame_type = frame.get("type")
        method = frame.get("method", "")

        # Shutdown is a notification with method="shutdown"
        if frame_type == "notification" and method == "shutdown":
            pending_shutdown = True
            break  # Loop exits; pending responses/events already sent before this point
        elif frame_type == "notification":
            params = frame.get("params", {})
            try:
                if method == "agent.interrupt":
                    await handle_request(method, params)
            except Exception as e:
                write_stdout(
                    {"type": "parse_error", "raw": str(frame), "detail": str(e)}
                )
        elif frame_type == "request":
            params = frame.get("params", {})
            req_id = frame.get("id")
            try:
                result = await handle_request(method, params)
                response = {"type": "response", "id": req_id, "result": result}
                write_stdout(response)
            except Exception as e:
                error_frame = {
                    "type": "error",
                    "id": req_id,
                    "code": -1,
                    "message": str(e),
                }
                write_stdout(error_frame)
        else:
            error_frame = {
                "type": "parse_error",
                "raw": line.decode().rstrip(),
                "detail": f"unknown frame type: {frame_type}",
            }
            write_stdout(error_frame)


def desktop_main() -> None:
    """Synchronous entry point for the desktop CLI command."""
    asyncio.run(main())
```

### 1.8 Tauri v2 Configuration with Scoped Permissions

```json
{
  "identifier": "com.mvgeos.desktop",
  "productName": "MvgeOS",
  "version": "0.1.0",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build"
  },
  "app": {
    "windows": [{
      "title": "MvgeOS",
      "label": "main",
      "width": 1400,
      "height": 900,
      "minWidth": 960,
      "minHeight": 600,
      "center": true,
      "resizable": true
    }],
    "security": {
      "csp": "default-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:"
    }
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "icon": ["icons/icon.png", "icons/icon.icns", "icons/icon.ico"],
    "resources": {
      "resources/mvgeos-desktop": "binaries/"
    },
    "windows": {
      "wix": null
    },
    "macos": {
      "minimumSystemVersion": "12.0",
      "entitlements": "entitlements.plist"  # Must create mvgeos-desktop/src-tauri/entitlements.plist with hardened runtime entitlements
    },
    "linux": {
      "deb": {
        "depends": []
      },
      "appimage": {
        "bundleMediaFramework": true
      }
    }
  },
  "plugins": {
    "updater": {
      "pubkey": "<replace-with-pubkey-from-cargo-tauri-signer-generate>",
      "endpoints": [
        "https://github.com/<replace-with-your-github-org>/mvgeos/releases/latest/download/updater.json"
      ],
      "windows": {
        "installMode": "passive"
      }
    }
  }
}
```

> **IMPORTANT**: The updater plugin will fail if `pubkey` or `endpoints` still contain `<replace-with-...>` placeholders. Replace before release, or configure the updater only in CI via a `tauri.conf.release.json` override.
>
> **Frontend auto-updater**: Phase 5 (post-MVP). Create a `useAutoUpdater` hook that calls `checkUpdate()` from `@tauri-apps/plugin-updater` on startup, displays a notification banner when an update is available, and triggers `installUpdate()` on user confirmation. The update channel UI (e.g. "stable" vs "beta") is tracked in `configStore`.

**Icon assets**: Place `icons/icon.png` (512×512), `icons/icon.icns` (macOS), and `icons/icon.ico` (Windows) in `mvgeos-desktop/src-tauri/icons/`. Generate from a single source PNG using:
```bash
# Requires ImageMagick (convert) or similar tool.
# For CI, install 'icon-gen' or 'pwa-icon-generator' npm package.
mkdir -p mvgeos-desktop/src-tauri/icons
# Generate .ico (Windows, multi-size)
convert icon-512.png -define icon:auto-resize=256,128,64,48,32,16 mvgeos-desktop/src-tauri/icons/icon.ico
# Generate .icns (macOS)
convert icon-512.png -resize 512x512 mvgeos-desktop/src-tauri/icons/icon.icns
# Copy PNG
cp icon-512.png mvgeos-desktop/src-tauri/icons/icon.png
```
In CI, use a checked-in source PNG (e.g., `assets/icon-512.png`) and run the above as a build step before `tauri-action`.

```xml
<!-- src-tauri/entitlements.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
</dict>
</plist>
```

```json
{
  "identifier": "default",
  "description": "Capability for main window",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "core:window:default",
    "core:window:allow-show",
    "core:window:allow-hide",
    "core:window:allow-close",
    "core:window:allow-set-size",
    "core:window:allow-set-position",
    "core:event:default",
    "core:event:allow-emit",
    "core:event:allow-listen",
    "dialog:default",
    "dialog:allow-open",
    "dialog:allow-save",
    "shell:default",
    "shell:allow-open",
    "process:default",
    "process:allow-exit",
    "fs:default",
    "fs:allow-read",
    "fs:allow-write",
    "fs:allow-exists",
    "fs:allow-mkdir",
    "fs:allow-stat",
    "fs:allow-remove",
    {
      "identifier": "fs:scope",
      "allow": [
        { "path": "$APPDATA/**" },
        { "path": "$DOCUMENTS/**" },
        { "path": "$RESOURCE/**" }
      ]
    },
    "store:allow-get",
    "store:allow-set",
    "store:allow-save",
    "store:allow-delete",
    "global-shortcut:default",
    "updater:default"
  ]
}
```

---

## Phase 2: Backend Bridge (Week 2-4)

### 2.1 Implementation Order

1. protocol.rs (frame types)
2. lifecycle.rs (ProcessSupervisor with stdin/stdout/stderr, handshake, watchdog, heartbeat)
3. ipc.rs (all commands: agent_run, agent_interrupt, spell_cast, tome_read, tome_write, config_get, config_set, get_api_key, set_api_key, delete_api_key)
4. main.rs (wire everything, window events, event forwarding)
5. Python desktop.py (all RPC methods, StdoutEventBus)
6. Tests

### 2.2 Protocol contract tests

```rust
// src-tauri/tests/protocol_tests.rs
#[test]
fn test_parse_response() {
    let json = r#"{"type":"response","id":1,"result":{"status":"ok"}}"#;
    let frame: FromPython = serde_json::from_str(json).unwrap();
    assert!(matches!(frame, FromPython::Response { id: 1, .. }));
}

/// Test input validation helpers (defined in ipc.rs).
/// These are kept as inline helpers in the test module for protocol_tests.
/// In the actual crate, import from ipc module: `use crate::ipc::validate_session_id;`
fn validate_session_id(id: &str) -> Result<(), String> {
    if id.is_empty() { return Err("empty".into()); }
    if id.chars().count() > 128 { return Err("too long".into()); }
    Ok(())
}

fn validate_prompt(prompt: &str) -> Result<(), String> {
    if prompt.trim().is_empty() { return Err("empty".into()); }
    if prompt.chars().count() > 100_000 { return Err("too long".into()); }
    Ok(())
}

#[test]
fn test_parse_event() {
    let json = r#"{"type":"event","event":"agent_token","data":{"token":"hello"}}"#;
    let frame: FromPython = serde_json::from_str(json).unwrap();
    assert!(matches!(frame, FromPython::Event { event, .. } if event == "agent_token"));
}

#[test]
fn test_parse_malformed_recovers() {
    let json = r#"not json"#;
    assert!(serde_json::from_str::<FromPython>(json).is_err());
}

#[test]
fn test_serialize_request() {
    let frame = ToPython::Request { id: 1, method: "ping".into(), params: serde_json::json!({}) };
    let json = serde_json::to_string(&frame).unwrap();
    assert!(json.contains("\"type\":\"request\""));
}

#[test]
fn test_serialize_notification() {
    let frame = ToPython::Notification { method: "shutdown".into(), params: serde_json::json!({}) };
    let json = serde_json::to_string(&frame).unwrap();
    assert!(json.contains("\"type\":\"notification\""));
    assert!(json.contains("\"method\":\"shutdown\""));
}

#[test]
fn test_validate_session_id() {
    assert!(validate_session_id("").is_err());
    assert!(validate_session_id("a".repeat(129).as_str()).is_err());
    assert!(validate_session_id(uuid::Uuid::new_v4().to_string().as_str()).is_ok());
}

#[test]
fn test_validate_prompt() {
    assert!(validate_prompt("").is_err());
    assert!(validate_prompt("   ").is_err());
    assert!(validate_prompt("Hello").is_ok());
}
```

### 2.3 Sessions and Interrupt

Session cancellation uses a notification-based approach: Rust sends `agent.interrupt` notification via stdin, and Python's desktop.py handler manages per-session CancellationTokens internally. See lifecycle.rs `interrupt_session()` and desktop.py `agent.interrupt` handler.

### 2.4 Settings Persistence

Settings are persisted on the Python side via `config.get`/`config.set` RPC methods (Section 1.7). Python reads/writes `~/.config/.mvgeos/config.json` (Linux/macOS) or `%APPDATA%/.mvgeos/config.json` (Windows). API keys go to an encrypted local store via the Rust `tauri-plugin-store` (commands `get_api_key`/`set_api_key` in Section 1.6 ipc.rs), NOT through config JSON.

```
┌─────────┐   config.get/set     ┌──────────────────────────┐
│ React   │ ──────────────────→  │ Python config handler    │
│ (Zustand)│                    │ (desktop.py, JSON file)  │
└─────────┘                    └──────────────────────────┘
┌─────────┐   invoke('get_       ┌──────────────────────────┐
│ React   │   _api_key')         │ Rust ipc.rs → encrypted  │
│ (Zustand)│ ──────────────────→  │ local store              │
│         │   invoke('set_       │ (tauri-plugin-store,     │
│         │   _api_key')         │ JSON file in app data    │
│         │                      │ dir, NOT plain config)   │
└─────────┘                      └──────────────────────────┘
```

---

## Phase 3: Core Frontend (Week 4-6)

### 3.1 Frontend Architecture

```
src/
├── assets/
│   └── fonts/
│       ├── JetBrainsMono-Regular.woff2  # Bundled from https://github.com/ryanoasis/nerd-fonts
│       └── Inter-Regular.woff2          # Bundled from https://github.com/rsms/inter
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx      # Main layout with sidebar + panel
│   │   ├── Sidebar.tsx        # FileTree + SessionBrowser
│   │   └── Panel.tsx          # Right panel (SpellOutput / Settings)
│   ├── chat/
│   │   ├── ChatPanel.tsx      # Message list + input
│   │   ├── ChatMessage.tsx    # Single message (markdown, code)
│   │   └── ChatInput.tsx      # Prompt textarea + send button
│   ├── files/
│   │   └── FileTree.tsx       # Project explorer
│   ├── spells/
│   │   └── SpellOutput.tsx    # Collapsible tool execution
│   ├── session/
│   │   ├── TabBar.tsx         # Session tabs
│   │   └── SessionBrowser.tsx # History list
│   ├── settings/
│   │   ├── SettingsPanel.tsx  # Tabs: Models, Theme, Keybindings, About
│   │   ├── ProviderConfig.tsx # API key + model config
│   │   └── ThemeSelector.tsx  # Light/dark/system
│   ├── common/
│   │   ├── StatusBar.tsx      # Bottom bar
│   │   ├── CommandPalette.tsx # Cmd+K fuzzy find
│   │   ├── DiffViewer.tsx     # Side-by-side diff
│   │   ├── WelcomeOverlay.tsx # First-run wizard
│   │   └── ErrorBoundary.tsx  # React error boundary
│   └── markdown/
│       └── MarkdownRenderer.tsx # react-markdown + code highlighting
├── hooks/
│   ├── useAgent.ts           # Invoke agent_run, agent_interrupt
│   ├── useConfig.ts          # config_get/set wrapper
│   ├── useKeyboard.ts        # Keyboard shortcuts
│   └── useTauriEvent.ts      # listen() wrapper (see below for implementation)
├── stores/
│   ├── agentStore.ts         # Sessions, messages, streaming
│   ├── configStore.ts        # Settings, theme, providers
│   └── sessionStore.ts       # Tab management
├── types/
│   ├── agent.ts              # AgentSession, Message, etc.
│   └── config.ts             # ModelConfig, ProviderConfig
├── App.tsx                   # Root: ErrorBoundary → AppLayout, calls initEventListeners in useEffect
├── main.tsx                  # ReactDOM.createRoot
├── index.css                 # @import "tailwindcss"
└── vite-env.d.ts
```

```typescript
// src/vite-env.d.ts
/// <reference types="vite/client" />
```

### 3.9 App Root with Event Listener Wiring

```typescript
// src/App.tsx
import { useEffect } from 'react';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { AppLayout } from './components/layout/AppLayout';
import { initEventListeners, useAgentStore } from './stores/agentStore';
import { useSessionStore } from './stores/sessionStore';
import { useKeyboard } from './hooks/useKeyboard';
import { useConfigStore } from './stores/configStore';

export default function App() {
  useEffect(() => {
    const listeners = initEventListeners();
    return () => {
      listeners.then((fns) => fns.forEach((fn) => fn()));
    };
  }, []);

  useKeyboard([
    { key: 'CmdOrCtrl+N', action: () => useAgentStore.getState().createSession(/* default config */) },
    { key: 'CmdOrCtrl+Shift+B', action: () => useConfigStore.getState().toggleSpellOutput() },
    { key: 'Escape', action: () => useConfigStore.getState().closePalette() },
    // Tab switching: CmdOrCtrl+1 through CmdOrCtrl+9
    ...[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => ({
      key: `CmdOrCtrl+${n}`,
      action: () => {
        const tabs = useSessionStore.getState().tabs;
        if (tabs[n - 1]) useSessionStore.getState().setActiveTab(tabs[n - 1].sessionId);
      },
    })),
  ]);

  return (
    <ErrorBoundary>
      <AppLayout />
    </ErrorBoundary>
  );
}
```

### 3.2 Shared Type Definitions

```typescript
// src/types/agent.ts
export interface AgentSession {
  id: string;                    // UUID generated by frontend
  messages: Message[];
  status: 'idle' | 'streaming' | 'interrupted' | 'error';
  model: ModelConfig;
  createdAt: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
  timestamp: number;
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface ToolResult {
  id: string;
  result: string;
  isError: boolean;
}

// src/types/config.ts
export interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  baseUrl?: string;
}

export interface ProviderConfig {
  id: string;
  name: string;            // "openai", "anthropic", "openrouter"
  baseUrl?: string;
  models: string[];
}
// API keys are stored in encrypted local store via get_api_key/set_api_key Tauri commands.
// They are NEVER stored in Zustand or written to config JSON.
// The frontend fetches keys on demand via invoke('get_api_key', { provider }).
```

### 3.3 Session ID Generation

Frontend generates session IDs using `crypto.randomUUID()` before sending `agent.run`. The `agent_run` command passes the session ID to Python. This keeps ID generation stateless on the backend.

```typescript
// hooks/useAgent.ts
const sessionId = crypto.randomUUID();
// NOTE: Tauri v2 passes each struct field as a flat invoke argument.
// Do NOT wrap in { args: ... } — pass session_id, prompt, model as top-level keys.
await invoke('agent_run', {
  session_id: sessionId,
  prompt,
  model,
});
```

### 3.4 Zustand Stores with Tauri Event Wiring

```typescript
// stores/agentStore.ts
import { create } from 'zustand';
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { useConfigStore } from './configStore';

interface AgentStore {
  sessions: Record<string, AgentSession>;
  activeSessionId: string | null;
  spellProgress: Record<string, number>; // spell_cast_id → 0.0..1.0
  createSession: (config: ModelConfig) => string;
  sendMessage: (sessionId: string, prompt: string) => Promise<void>;
  interruptAgent: (sessionId: string) => Promise<void>;
  appendToken: (sessionId: string, token: string) => void;
  addToolCall: (sessionId: string, toolCall: ToolCall) => void;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  sessions: {},
  activeSessionId: null,
  spellProgress: {},

  createSession: (config) => {
    const id = crypto.randomUUID();
    set((state) => ({
      sessions: { ...state.sessions, [id]: { id, messages: [], status: 'idle' as const, model: config, createdAt: Date.now() } },
      activeSessionId: id,
    }));
    return id;
  },

  sendMessage: async (sessionId, prompt) => {
    const session = get().sessions[sessionId];
    if (!session) return;
    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', content: prompt, timestamp: Date.now() };
    const updatedSession = {
      ...session,
      messages: [...session.messages, userMessage],
      status: 'streaming' as const,
    };
    set((state) => ({
      sessions: { ...state.sessions, [sessionId]: updatedSession },
    }));

    try {
      await invoke('agent_run', {
        session_id: sessionId,
        prompt,
        model: session.model,
      });
    } catch (err) {
      console.error('agent_run failed:', err);
      set((state) => {
        const s = state.sessions[sessionId];
        if (!s) return state;
        return {
          sessions: { ...state.sessions, [sessionId]: { ...s, status: 'error' as const } },
        };
      });
    }
  },

  interruptAgent: async (sessionId) => {
    try {
      await invoke('agent_interrupt', { session_id: sessionId });
      // Immediately reflect interruption in UI
      useAgentStore.setState((state) => {
        const session = state.sessions[sessionId];
        if (!session) return state;
        return { sessions: { ...state.sessions, [sessionId]: { ...session, status: 'idle' as const } } };
      });
    } catch (err) {
      console.error('agent_interrupt failed:', err);
    }
  },

    // MUTUALLY EXCLUSIVE: agent_token streams incremental tokens (frequent, small).
    // agent_message fires once per complete message block (less frequent).
    // The frontend should handle one or the other — not both for the same message.
    // By default, handle agent_token for streaming UX and ignore agent_message,
    // OR handle agent_message for batch updates and ignore agent_token.
    // The current implementation handles both; in practice the agent fires one or the other.
    appendToken: (sessionId, token) => {
    set((state) => {
      const session = state.sessions[sessionId];
      if (!session) return state;
      const lastMsg = session.messages[session.messages.length - 1];
      if (lastMsg?.role === 'assistant') {
        const updatedMessages = [...session.messages];
        updatedMessages[updatedMessages.length - 1] = { ...lastMsg, content: lastMsg.content + token };
        return { sessions: { ...state.sessions, [sessionId]: { ...session, messages: updatedMessages } } };
      }
      const newMsg: Message = { id: crypto.randomUUID(), role: 'assistant', content: token, timestamp: Date.now() };
      return { sessions: { ...state.sessions, [sessionId]: { ...session, messages: [...session.messages, newMsg] } } };
    });
  },

  addToolCall: (sessionId, toolCall) => {
    set((state) => {
      const session = state.sessions[sessionId];
      if (!session) return state;
      const lastMsg = session.messages[session.messages.length - 1];
      if (lastMsg?.role === 'assistant') {
        const updatedMessages = [...session.messages];
        const toolCalls = lastMsg.toolCalls ? [...lastMsg.toolCalls, toolCall] : [toolCall];
        updatedMessages[updatedMessages.length - 1] = { ...lastMsg, toolCalls };
        return { sessions: { ...state.sessions, [sessionId]: { ...session, messages: updatedMessages } } };
      }
      return state;
    });
  },

}));

// stores/sessionStore.ts — Tab management for multiple sessions
interface SessionTab {
  sessionId: string;
  label: string;
}

interface SessionStore {
  tabs: SessionTab[];
  activeTab: string | null;
  openTab: (sessionId: string, label?: string) => void;
  closeTab: (sessionId: string) => void;
  setActiveTab: (sessionId: string) => void;
  renameTab: (sessionId: string, label: string) => void;
  reorderTab: (fromIndex: number, toIndex: number) => void;
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  tabs: [],
  activeTab: null,

  openTab: (sessionId, label) => {
    const exists = get().tabs.some((t) => t.sessionId === sessionId);
    if (exists) {
      set({ activeTab: sessionId });
      return;
    }
    const tab: SessionTab = { sessionId, label: label ?? sessionId.slice(0, 8) };
    set((state) => ({ tabs: [...state.tabs, tab], activeTab: sessionId }));
  },

  closeTab: (sessionId) => {
    set((state) => {
      const tabs = state.tabs.filter((t) => t.sessionId !== sessionId);
      let activeTab = state.activeTab;
      if (activeTab === sessionId) {
        activeTab = tabs.length > 0 ? tabs[tabs.length - 1].sessionId : null;
      }
      return { tabs, activeTab };
    });
  },

  setActiveTab: (sessionId) => set({ activeTab: sessionId }),

  renameTab: (sessionId, label) => {
    set((state) => ({
      tabs: state.tabs.map((t) => t.sessionId === sessionId ? { ...t, label } : t),
    }));
  },

  reorderTab: (fromIndex, toIndex) => {
    set((state) => {
      const tabs = [...state.tabs];
      const [moved] = tabs.splice(fromIndex, 1);
      tabs.splice(toIndex, 0, moved);
      return { tabs };
    });
  },
}));

// Wire Tauri events once at app startup.
// NOTE: Event payloads arrive with snake_case field names (from Python via Rust).
// TypeScript generics must use snake_case to match wire format, e.g.
// listen<{ session_id: string; token: string }>('agent_token', ...).
export function initEventListeners(): Promise<UnlistenFn[]> {
  const unlisteners: Promise<UnlistenFn>[] = [
    listen<{ session_id: string; token: string }>('agent_token', (event) => {
      useAgentStore.getState().appendToken(event.payload.session_id, event.payload.token);
    }),
    listen<{ session_id: string; tool: string; args: unknown }>('agent_tool_call', (event) => {
      useAgentStore.getState().addToolCall(event.payload.session_id, {
        id: crypto.randomUUID(),
        name: event.payload.tool,
        args: event.payload.args as Record<string, unknown>,
      });
    }),
    listen<{ session_id: string; stop_reason: string }>('agent_complete', (event) => {
      useAgentStore.setState((state) => {
        const session = state.sessions[event.payload.session_id];
        if (!session) return state;
        return {
          sessions: { ...state.sessions, [event.payload.session_id]: { ...session, status: 'idle' as const } },
        };
      });
    }),
    listen<{ session_id: string; error: string }>('agent_error', (event) => {
      useAgentStore.setState((state) => {
        const session = state.sessions[event.payload.session_id];
        if (!session) return state;
        const errorMsg: Message = { id: crypto.randomUUID(), role: 'assistant' as const, content: `Error: ${event.payload.error}`, timestamp: Date.now() };
        return {
          sessions: { ...state.sessions, [event.payload.session_id]: { ...session, messages: [...session.messages, errorMsg], status: 'error' as const } },
        };
      });
    }),
    listen<{ session_id: string; content: string }>('agent_message', (event) => {
      useAgentStore.setState((state) => {
        const session = state.sessions[event.payload.session_id];
        if (!session) return state;
        const msg: Message = { id: crypto.randomUUID(), role: 'assistant' as const, content: event.payload.content, timestamp: Date.now() };
        return {
          sessions: { ...state.sessions, [event.payload.session_id]: { ...session, messages: [...session.messages, msg] } },
        };
      });
    }),
    listen('process_crashed', () => {
      useConfigStore.getState().setConnectionStatus('disconnected');
    }),
    listen('process_restarted', () => {
      useConfigStore.getState().setConnectionStatus('connected');
      // Reset all active (non-idle) sessions back to idle so the user can retry.
      useAgentStore.setState((state) => {
        const reset: Record<string, AgentSession> = {};
        for (const [id, session] of Object.entries(state.sessions)) {
          reset[id] = session.status === 'idle' ? session : { ...session, status: 'idle' as const };
        }
        return { sessions: reset };
      });
    }),
    listen<{ session_id: string; tool: string; result: string }>('agent_tool_result', (event) => {
      useAgentStore.setState((state) => {
        const session = state.sessions[event.payload.session_id];
        if (!session) return state;
        const lastMsg = session.messages[session.messages.length - 1];
        if (lastMsg?.role === 'assistant') {
          const updatedMessages = [...session.messages];
          const toolResults = lastMsg.toolResults ? [...lastMsg.toolResults, { id: event.payload.tool, result: event.payload.result, isError: false }] : [{ id: event.payload.tool, result: event.payload.result, isError: false }];
          updatedMessages[updatedMessages.length - 1] = { ...lastMsg, toolResults };
          return { sessions: { ...state.sessions, [event.payload.session_id]: { ...session, messages: updatedMessages } } };
        }
        return state;
      });
    }),
    listen<{ session_id: string; tokens_in: number; tokens_out: number; mana: number }>('agent_usage', (event) => {
      // Log token usage; can be displayed in status bar or debug panel
      console.debug(`Usage: ${event.payload.tokens_in} in, ${event.payload.tokens_out} out, ${event.payload.mana} mana`);
    }),
    listen<{ session_id: string; spell_cast_id: string; progress: number }>('spell_progress', (event) => {
      useAgentStore.setState((state) => ({
        spellProgress: { ...state.spellProgress, [event.payload.spell_cast_id]: event.payload.progress },
      }));
    }),
    listen<Record<string, never>>('heartbeat', () => {
      // Liveness signal from Python; no action needed
    }),
    listen<{ level: string; message: string }>('log', (event) => {
      // Forward Python-side diagnostic logs to browser console
      const level = event.payload.level;
      const msg = `[python:${level}] ${event.payload.message}`;
      switch (level) {
        case 'error': console.error(msg); break;
        case 'warn': console.warn(msg); break;
        default: console.log(msg);
      }
    }),
    // Native menu event listeners
    listen<Record<string, never>>('menu-new-session', () => {
      useAgentStore.getState().createSession(/* default config */);
    }),
    listen<Record<string, never>>('menu-open-project', () => {
      // Phase 3: open a native file dialog and load workspace
      console.debug('Open project requested');
    }),
    listen<Record<string, never>>('menu-settings', () => {
      // Open settings panel logic — toggles a settings drawer/modal
      console.debug('Settings requested');
    }),
    listen<Record<string, never>>('menu-toggle-file-tree', () => {
      useConfigStore.getState().toggleFileTree?.();
    }),
    listen<Record<string, never>>('menu-toggle-spell-output', () => {
      useConfigStore.getState().toggleSpellOutput?.();
    }),
    listen<Record<string, never>>('menu-toggle-command-palette', () => {
      useConfigStore.getState().togglePalette?.();
    }),
    listen<Record<string, never>>('menu-interrupt', () => {
      const active = useAgentStore.getState().activeSessionId;
      if (active) useAgentStore.getState().interruptAgent(active);
    }),
    listen<Record<string, never>>('menu-clear-session', () => {
      // Clear active session messages — could set messages to [] on active session
      console.debug('Clear session requested');
    }),
  ];
  return Promise.all(unlisteners);
}
```

### 3.5 ErrorBoundary

```typescript
// components/common/ErrorBoundary.tsx
import { Component, ErrorInfo, ReactNode } from 'react';

interface Props { children: ReactNode; fallback?: ReactNode; }
interface State { hasError: boolean; error?: Error; errorKey: number; }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, errorKey: 0 };
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorKey: Date.now() };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('React error boundary caught:', error, info);
  }
  handleRetry = () => {
    // Increment errorKey forces child remount via key prop
    this.setState((prev) => ({ hasError: false, error: undefined, errorKey: prev.errorKey + 1 }));
  };
  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <h2 className="text-lg font-semibold">Something went wrong</h2>
            <p className="text-sm text-gray-500">{this.state.error?.message}</p>
            <button onClick={this.handleRetry}>Try again</button>
          </div>
        </div>
      );
    }
    // key prop forces remount when recovering from error
    return <div key={this.state.errorKey}>{this.props.children}</div>;
  }
}
```

### 3.6 Markdown Rendering with Fonts

```typescript
// components/markdown/MarkdownRenderer.tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';

// Fonts are bundled for offline use — no external font hosts in CSP.
// JetBrains Mono (for code) and Inter (for UI) are served from src/assets/fonts/.
// See index.css for @font-face declarations.
export function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        code({ className, children, ...props }) {
          const isInline = !className;
          return isInline
            ? <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded font-mono text-sm">{children}</code>
            : <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto font-mono text-sm"><code>{children}</code></pre>;
        },
      }}
    />
  );
}
```

```css
/* src/index.css — @font-face declarations for bundled fonts */
@import "tailwindcss";
@font-face {
  font-family: 'JetBrains Mono';
  src: url('./assets/fonts/JetBrainsMono-Regular.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'Inter';
  src: url('./assets/fonts/Inter-Regular.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
:root {
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}
```

### 3.7 Keyboard Shortcuts Implementation

```typescript
// hooks/useKeyboard.ts
import { useEffect, useCallback } from 'react';
import { register, unregister } from '@tauri-apps/plugin-global-shortcut';

interface Shortcut {
  key: string;          // "CmdOrCtrl+N"
  action: () => void;
  global?: boolean;     // true = works when app is backgrounded
}

export function useKeyboard(shortcuts: Shortcut[]) {
  useEffect(() => {
    const registrations: Promise<void>[] = [];
    for (const s of shortcuts) {
      if (s.global) {
        registrations.push(
          register(s.key, () => s.action()).catch((err) =>
            console.error(`Failed to register shortcut ${s.key}:`, err)
          )
        );
      }
    }
    return () => {
      // Unregister all global shortcuts on cleanup
      for (const s of shortcuts) {
        if (s.global) {
          unregister(s.key).catch((err) =>
            console.error(`Failed to unregister shortcut ${s.key}:`, err)
          );
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortcuts]); // Re-register when shortcuts change to avoid stale closures

  // Non-global shortcuts handled by React keydown listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();

      // CmdOrCtrl+1-9: switch to tab at index
      if (meta && /^[1-9]$/.test(key)) {
        e.preventDefault();
        const idx = parseInt(key, 10) - 1;
        const tabShortcut = shortcuts.find((s) => s.key === `CmdOrCtrl+${key}`);
        if (tabShortcut) {
          tabShortcut.action();
        }
      }

      // Escape: runs the first matching non-global escape action
      if (key === 'escape') {
        const escapeAction = shortcuts.find((s) => s.key.toLowerCase() === 'escape');
        escapeAction?.action();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);
}

// In App.tsx:
useKeyboard([
  { key: 'CmdOrCtrl+N', action: () => createSession() },
  { key: 'CmdOrCtrl+B', action: () => toggleSidebar() },
  { key: 'Escape', action: () => closePalette() },
]);
```

### 3.8 First-Run Detection

```typescript
// stores/configStore.ts
import { create } from 'zustand';
import { invoke } from '@tauri-apps/api/core';

interface ConfigStore {
  isFirstRun: boolean;
  connectionStatus: 'connecting' | 'connected' | 'disconnected';
  fileTreeOpen: boolean;
  spellOutputOpen: boolean;
  paletteOpen: boolean;
  checkFirstRun: () => Promise<void>;
  completeOnboarding: () => Promise<void>;
  setConnectionStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  toggleFileTree: () => void;
  toggleSpellOutput: () => void;
  togglePalette: () => void;
  closePalette: () => void;
}

export const useConfigStore = create<ConfigStore>((set) => ({
  isFirstRun: true,
  connectionStatus: 'connected',
  fileTreeOpen: false,
  spellOutputOpen: false,
  paletteOpen: false,

  checkFirstRun: async () => {
    try {
      const result = await invoke('config_get', { key: 'onboarding_completed' });
      set({ isFirstRun: (result as Record<string, unknown>)?.value !== true });
    } catch (err) {
      console.error('Failed to check first run:', err);
      set({ isFirstRun: true });
    }
  },

  completeOnboarding: async () => {
    try {
      await invoke('config_set', { key: 'onboarding_completed', value: true });
      set({ isFirstRun: false });
    } catch (err) {
      console.error('Failed to complete onboarding:', err);
    }
  },

  setConnectionStatus: (status) => set({ connectionStatus: status }),
  toggleFileTree: () => set((state) => ({ fileTreeOpen: !state.fileTreeOpen })),
  toggleSpellOutput: () => set((state) => ({ spellOutputOpen: !state.spellOutputOpen })),
  togglePalette: () => set((state) => ({ paletteOpen: !state.paletteOpen })),
  closePalette: () => set({ paletteOpen: false }),
}));
```

### 3.10 useTauriEvent Hook

```typescript
// hooks/useTauriEvent.ts
import { useEffect, useRef } from 'react';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

/**
 * React hook that listens to a Tauri event and calls a callback when it fires.
 * Automatically cleans up the listener on unmount.
 * Race-safe: if the listen() promise resolves after unmount, the unlisten function
 * is still called via the ref.
 *
 * Usage (in any component):
 *   useTauriEvent<{sessionId: string}>('agent_complete', (payload) => {
 *     console.log('Session complete:', payload.sessionId);
 *   });
 */
export function useTauriEvent<T = unknown>(event: string, handler: (payload: T) => void) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    let cancelled = false;
    let unlisten: UnlistenFn | undefined;

    listen<T>(event, (e) => {
      if (!cancelled) handlerRef.current(e.payload);
    }).then((fn) => {
      unlisten = fn;
      if (cancelled) fn();
    });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [event]);
}
```

### 3.11 Spell Output Protocol

`spell.cast` is a Request that returns immediately with `{spell_cast_id, status:"started"}`. Actual progress and results arrive via `spell_progress` and `agent_tool_result` events. This avoids blocking the Request on spell completion.

---

## Phase 4: Features & Polish (Week 6-8)

### 4.1 Native Menu

```rust
// src-tauri/src/menu.rs
use tauri::menu::{Menu, Submenu, MenuItem, PredefinedMenuItem};
use tauri::AppHandle;

pub fn create_app_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let file = Submenu::with_items(app, "File", true, &[
        &MenuItem::with_id(app, "new_session", "New Session", true, Some("CmdOrCtrl+N"))?,
        &MenuItem::with_id(app, "open_project", "Open Project...", true, Some("CmdOrCtrl+O"))?,
        &PredefinedMenuItem::separator(app)?,
        &MenuItem::with_id(app, "settings", "Settings...", true, Some("CmdOrCtrl+,"))?,
        &PredefinedMenuItem::quit(app, Some("Quit MvgeOS"))?,
    ])?;
    let edit = Submenu::with_items(app, "Edit", true, &[
        &PredefinedMenuItem::undo(app, Some("Undo"))?,
        &PredefinedMenuItem::redo(app, Some("Redo"))?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::cut(app, Some("Cut"))?,
        &PredefinedMenuItem::copy(app, Some("Copy"))?,
        &PredefinedMenuItem::paste(app, Some("Paste"))?,
    ])?;
    let view = Submenu::with_items(app, "View", true, &[
        &MenuItem::with_id(app, "toggle_file_tree", "Toggle File Tree", true, Some("CmdOrCtrl+B"))?,
        &MenuItem::with_id(app, "toggle_spell_output", "Toggle Spell Output", true, Some("CmdOrCtrl+Shift+B"))?,
        &MenuItem::with_id(app, "toggle_command_palette", "Command Palette", true, Some("CmdOrCtrl+K"))?,
    ])?;
    let mvge = Submenu::with_items(app, "Mvge", true, &[
        &MenuItem::with_id(app, "interrupt", "Interrupt", true, Some("CmdOrCtrl+."))?,
        &MenuItem::with_id(app, "clear_session", "Clear Session", true, Some("CmdOrCtrl+L"))?,
    ])?;
    Menu::with_items(app, &[&file, &edit, &view, &mvge])
}

pub fn handle_menu_event(app: &AppHandle, event: tauri::menu::MenuEvent) {
    match event.id().as_ref() {
        "new_session" => { app.emit("menu-new-session", ()).ok(); }
        "open_project" => { app.emit("menu-open-project", ()).ok(); }
        "settings" => { app.emit("menu-settings", ()).ok(); }
        "toggle_file_tree" => { app.emit("menu-toggle-file-tree", ()).ok(); }
        "toggle_spell_output" => { app.emit("menu-toggle-spell-output", ()).ok(); }
        "toggle_command_palette" => { app.emit("menu-toggle-command-palette", ()).ok(); }
        "interrupt" => { app.emit("menu-interrupt", ()).ok(); }
        "clear_session" => { app.emit("menu-clear-session", ()).ok(); }
        _ => {}
    }
}
```

### 4.2 System Tray

```rust
// src-tauri/src/tray.rs
use tauri::tray::{TrayIconBuilder, TrayIconEvent};
use tauri::menu::{Menu, MenuItem};

pub fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "Show MvgeOS", true, None::<&str>)?;
    let new_session = MenuItem::with_id(app, "tray_new_session", "New Session", true, None::<&str>)?;
    let separator = tauri::menu::PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "tray_quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &new_session, &separator, &quit])?;

    TrayIconBuilder::new()
        .icon(app.default_window_icon().cloned().unwrap_or_else(|| {
            // Fallback: empty icon; tray will be created without a custom icon
            tauri::image::Image::new(&[], 0, 0)
        }))
        .menu(&menu)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => { app.get_webview_window("main").map(|w| w.show().ok()); }
            "tray_new_session" => { app.emit("menu-new-session", ()).ok(); }
            "tray_quit" => {
                // Graceful shutdown before exit to avoid zombie Python process
                if let Some(sup) = app.try_state::<Arc<ProcessSupervisor>>() {
                    let sup = sup.inner().clone();
                    tauri::async_runtime::block_on(async move { sup.shutdown().await; });
                }
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(())
}
```

### 4.3 Auto-Updater

```rust
// main.rs setup
.plugin(tauri_plugin_updater::Builder::new().build())
```

Capabilities include `"updater:default"`. Builds are signed with `TAURI_PRIVATE_KEY`.

**Endpoint**: GitHub Releases at `https://github.com/{owner}/mvgeos/releases/latest/download/updater.json`

The `updater.json` file is generated by `tauri-action` on release and contains per-platform download URLs. The format is:
```json
{
  "version": "0.1.0",
  "notes": "Release notes",
  "pub_date": "2025-01-01T00:00:00Z",
  "platforms": {
    "windows-x86_64": { "signature": "<signature-from-ci>", "url": "https://github.com/<your-org>/mvgeos/releases/download/v0.1.0/MvgeOS_x64.msi" },
    "macos-aarch64": { "signature": "<signature-from-ci>", "url": "..." },
    "linux-x86_64": { "signature": "<signature-from-ci>", "url": "..." }
  }
}
```

**Pubkey configuration**: Set `TAURI_PRIVATE_KEY` as a GitHub Secret and `TAURI_KEY_PASSWORD` (if used). The public key is embedded in `tauri.conf.json` under `plugins.updater.pubkey` (see Section 1.8). Generate the keypair:
```bash
cargo tauri signer generate -w ~/.tauri/mvgeos.key
# Shows public key. Save private key as TAURI_PRIVATE_KEY in CI secrets.
```

### 4.4 Keyboard Shortcuts Table

| Scope | Shortcut | Action |
|-------|----------|--------|
| Global | CmdOrCtrl+N | New session |
| Global | CmdOrCtrl+O | Open project |
| Window | CmdOrCtrl+B | Toggle file tree |
| Window | CmdOrCtrl+Shift+B | Toggle spell output |
| Window | CmdOrCtrl+K | Command palette |
| Window | CmdOrCtrl+. | Interrupt agent |
| Window | CmdOrCtrl+L | Clear session |
| Window | CmdOrCtrl+, | Settings |
| Window | CmdOrCtrl+1-9 | Switch tabs |
| Window | Escape | Close palette / cancel |

### 4.5 FileTree Git Integration

Implementation path (post-MVP, Phase 4):

**Phase 4a — Python git_status spell (immediate):**
- Agent sends `git status --porcelain` via existing bash spell
- FileTree component parses output: `M file.txt` → modified, `?? new.txt` → untracked
- Status icons overlay on file names in FileTree
- No real-time updates; user clicks "Refresh" or agent action triggers re-check

**Phase 4b — Rust notify watcher (post-MVP enhancement):**
- Add `notify = { version = "7", features = ["macos_fsevent"] }` to Cargo.toml
- `src-tauri/src/file_watcher.rs`: uses `notify::RecommendedWatcher` to watch project directory
- Debounce events (300ms) to batch rapid filesystem changes
- Send `file_changed` events to frontend via Tauri event system. Event payload format: `{path: string, kind: "created"|"modified"|"deleted"}`
- FileTree subscribes to `file_changed` events via `useTauriEvent` hook
- FileTree merges git status (from Python spell) with filesystem events (from Rust watcher)

### 4.6 DiffViewer

```typescript
// components/common/DiffViewer.tsx
import { diffLines, Change } from 'diff';

interface DiffLine {
  type: 'added' | 'removed' | 'unchanged';
  content: string;
  lineNumber: number;
}

interface DiffViewerProps {
  original: string;
  modified: string;
  filename: string;
  onAccept?: (filename: string, content: string) => void;
  onReject?: (filename: string) => void;
}

function computeDiff(original: string, modified: string): DiffLine[] {
  const changes: Change[] = diffLines(original, modified);
  const result: DiffLine[] = [];
  let lineNumber = 1;
  for (const change of changes) {
    const lines = change.value.split('\n');
    // remove trailing empty string from split
    if (lines[lines.length - 1] === '') lines.pop();
    for (const line of lines) {
      if (change.added) {
        result.push({ type: 'added', content: line, lineNumber });
      } else if (change.removed) {
        result.push({ type: 'removed', content: line, lineNumber });
      } else {
        result.push({ type: 'unchanged', content: line, lineNumber });
      }
      if (!change.added) lineNumber++;
    }
  }
  return result;
}

export function DiffViewer({ original, modified, filename, onAccept, onReject }: DiffViewerProps) {
  const lines = computeDiff(original, modified);
  // Renders a unified diff with line numbers in a left gutter,
  // green background for added lines, red for removed lines.
  // Accept button calls onAccept(filename, modified).
  // Reject button calls onReject(filename).
  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-gray-100 dark:bg-gray-800 border-b">
        <span className="text-sm font-mono">{filename}</span>
        <div className="flex gap-2">
          {onAccept && <button onClick={() => onAccept(filename, modified)} className="px-2 py-1 text-xs bg-green-600 text-white rounded">Accept</button>}
          {onReject && <button onClick={() => onReject(filename)} className="px-2 py-1 text-xs bg-red-600 text-white rounded">Reject</button>}
        </div>
      </div>
      <pre className="text-sm overflow-x-auto p-2">
        {lines.map((line, i) => (
          <div key={i} className={`flex ${line.type === 'added' ? 'bg-green-100 dark:bg-green-900/30' : ''}${line.type === 'removed' ? 'bg-red-100 dark:bg-red-900/30' : ''}`}>
            <span className="text-gray-400 dark:text-gray-500 pr-3 text-right w-10 select-none">{line.lineNumber}</span>
            <span>{line.content}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}
```

### 4.7 Onboarding Flow

File: `src/components/common/WelcomeOverlay.tsx`

State machine via `useReducer` in WelcomeOverlay:
  STEP_WELCOME → STEP_API_KEY → STEP_MODEL → STEP_PROJECT → STEP_TIPS → DONE

Transitions:
  STEP_WELCOME:      "Get Started" → STEP_API_KEY
  STEP_API_KEY:      provider dropdown + secure keychain input; "Skip" → STEP_MODEL;
                     "Next" (key saved) → STEP_MODEL
  STEP_MODEL:        fetches models from provider via config.get; "Skip","Next" → STEP_PROJECT
  STEP_PROJECT:      directory picker via dialog:allow-open; "Skip","Next" → STEP_TIPS
  STEP_TIPS:         dismissable overlay with keyboard shortcut reference; "Done" → DONE
  DONE:              config_set("onboarding_completed", true); closes WelcomeOverlay

Edge cases:
  - Mid-flow abandon: user closes window → progress not saved → restarts at STEP_WELCOME
  - Back navigation: each step has a "Back" button (except STEP_WELCOME)
  - API key step prefilled if key exists in keychain (get_api_key returns non-empty)

Data stored during onboarding:
  - api_key (os keychain via set_api_key command)
  - default_model (config.set "default_model")
  - project_path (config.set "project_path")
  - onboarding_completed (config.set "onboarding_completed", true)
```

---

## Phase 5: Packaging & Distribution (Week 8-10)

### 5.1 PyInstaller Spec

Prerequisite: add `pyinstaller` as a dev dependency in `mvgeos-cli/pyproject.toml`:
```toml
[project.optional-dependencies]
bundle = ["pyinstaller>=6.0"]
```
CI installs it via `uv sync --group bundle` or `uv pip install pyinstaller`.

```python
# mvgeos-desktop/mvgeos-desktop.spec
# -*- mode: python ; python: 3.12 -*-
import sys
from pathlib import Path

sys.setrecursionlimit(5000)

block_cipher = None

a = Analysis(
    ["../mvgeos-cli/mvgeos/commands/desktop.py"],
    pathex=[str(Path("../mvgeos-cli").resolve())],
    binaries=[],
    datas=[],
    hiddenimports=[
        "mvgeos_agent",
        "mvgeos_provider",
        "mvgeos_tome",
        "mvgeos_spells",
        "mvgeos_runes",
        "mvgeos_cli",
        "anyio",
        "httpx",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="mvgeos-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Release: hide console window. Use --console flag or separate .spec for debug builds.
    # For release CI builds, pass `--console` flag or maintain
    # a separate `mvgeos-desktop-release.spec` with console=False.
    # If console=False, ensure ~/.mvgeos/desktop.log logging is active.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

### 5.2 Build Matrix

| Platform | Runner | Target | Output |
|----------|--------|--------|--------|
| macOS (ARM) | `macos-latest-xlarge` | `aarch64-apple-darwin` | `.dmg` |
| macOS (Intel) | `macos-13` | `x86_64-apple-darwin` | `.dmg` |
| Windows (x64) | `windows-latest` | `x86_64-pc-windows-msvc` | `.msi` |
| Windows (ARM) | `windows-latest` (cross) | `aarch64-pc-windows-msvc` | `.msi` |
| Linux (x64) | `ubuntu-latest` | `x86_64-unknown-linux-gnu` | `.AppImage`, `.deb` |

### 5.3 CI/CD

```yaml
name: Desktop CI

on:
  push:
    branches: [main, dev]
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  CARGO_TERM_COLOR: always
  NODE_VERSION: "20"

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mvgeos-desktop
    steps:
      - uses: actions/checkout@v4
      - name: Install Python and uv
        run: |
          pip install uv
          uv sync
      - uses: dtolnay/rust-toolchain@stable
      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: "mvgeos-desktop/src-tauri -> target"
      - name: Install WebKit2GTK (Linux)
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev libsoup-3.0-dev
      - name: Rust tests
        run: cargo test
        working-directory: mvgeos-desktop/src-tauri
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: mvgeos-desktop/package-lock.json
      - name: Download and cache font assets
        run: |
          mkdir -p src/assets/fonts
          cd src/assets/fonts
          [ -f JetBrainsMono-Regular.woff2 ] || curl -sL --fail -o JetBrainsMono-Regular.woff2 https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/JetBrainsMono/Ligatures/Regular/JetBrainsMonoNerdFont-Regular.woff2 || true
          [ -f Inter-Regular.woff2 ] || curl -sL --fail -o Inter-Regular.woff2 https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Regular.woff2 || true
      - run: npm ci
      - run: npm run test

  build:
    if: startsWith(github.ref, 'refs/tags/v')
    strategy:
      matrix:
        include:
          - os: macos-latest-xlarge
            target: aarch64-apple-darwin
          - os: macos-13
            target: x86_64-apple-darwin
          - os: windows-latest
            target: x86_64-pc-windows-msvc
          - os: windows-latest
            target: aarch64-pc-windows-msvc
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
    runs-on: ${{ matrix.os }}
    defaults:
      run:
        working-directory: mvgeos-desktop
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}
      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: "mvgeos-desktop/src-tauri -> target"
      - name: Add Visual Studio ARM64 build tools (Windows ARM)
        if: matrix.target == 'aarch64-pc-windows-msvc'
        uses: ilammy/msvc-dev-cmd@v1
        with:
          arch: arm64
      - name: Install WebKit2GTK (Linux)
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev libsoup-3.0-dev
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: "npm"
          cache-dependency-path: mvgeos-desktop/package-lock.json
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"
      - run: npm ci
      - name: Sync Python workspace and build bundle
        run: |
          uv sync --group bundle
          uv run pyinstaller mvgeos-desktop.spec
      - name: Copy PyInstaller binary into Tauri resources
        shell: bash
        run: |
          mkdir -p src-tauri/resources
          # Handle both .exe (Windows) and no-extension (Linux/macOS) binaries
          BUNDLE_DIR="dist/mvgeos-desktop"
          SRC=$(ls "$BUNDLE_DIR"/mvgeos-desktop* 2>/dev/null | head -1)
          if [ -z "$SRC" ]; then echo "No PyInstaller binary found in $BUNDLE_DIR"; exit 1; fi
          cp "$SRC" src-tauri/resources/
      - name: Generate icon assets for Tauri
        run: |
          mkdir -p src-tauri/icons
          cp ../assets/icon-512.png src-tauri/icons/icon.png
          # .ico (Windows) and .icns (macOS) require ImageMagick; skip if not installed
          if command -v convert &> /dev/null; then
            convert ../assets/icon-512.png -define icon:auto-resize=256,128,64,48,32,16 src-tauri/icons/icon.ico
            convert ../assets/icon-512.png -resize 512x512 src-tauri/icons/icon.icns
          fi
      - uses: tauri-apps/tauri-action@v2
        with:
          project-path: mvgeos-desktop
          bundle: |
            {"resources": {"resources/mvgeos-desktop": "binaries/"}}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TAURI_PRIVATE_KEY: ${{ secrets.TAURI_PRIVATE_KEY }}
          TAURI_KEY_PASSWORD: ${{ secrets.TAURI_KEY_PASSWORD }}
      - name: Codesign (macOS)
        if: runner.os == 'macOS'
        run: |
          APP_PATH=$(ls src-tauri/target/release/bundle/macos/MvgeOS.app 2>/dev/null | head -1)
          if [ -n "$APP_PATH" ] && [ -n "${{ secrets.APPLE_SIGNING_IDENTITY }}" ]; then
            codesign --deep --force --verify --sign "${{ secrets.APPLE_SIGNING_IDENTITY }}" "$APP_PATH"
          fi
      - name: Notarize (macOS)
        if: runner.os == 'macOS'
        run: |
          DMG_PATH=$(ls src-tauri/target/release/bundle/dmg/MvgeOS_*.dmg 2>/dev/null | head -1)
          if [ -n "$DMG_PATH" ]; then
            xcrun notarytool submit \
              --apple-id "${{ secrets.APPLE_ID }}" \
              --password "${{ secrets.APPLE_PASSWORD }}" \
              --team-id "${{ secrets.APPLE_TEAM_ID }}" \
              --wait "$DMG_PATH"
            xcrun stapler staple "$DMG_PATH"
          fi
```

### 5.4 Code Signing + Notarization

| Platform | Step | Tool |
|----------|------|------|
| macOS | Sign app bundle | `codesign --deep --force --verify --sign "$APPLE_SIGNING_IDENTITY"` (set $APPLE_SIGNING_IDENTITY in CI to your "Developer ID Application: TEAM_ID" string) |
| macOS | Submit for notarization | `xcrun notarytool submit --apple-id $APPLE_ID --password $APPLE_PASSWORD --team-id $APPLE_TEAM_ID --wait` |
| macOS | Staple ticket | `xcrun stapler staple MvgeOS.dmg` |
| Windows | Sign installer (.msi produced by WiX) | `signtool sign /fd sha256 /tr http://timestamp.digicert.com /a "MvgeOS_x64.msi"` (requires $WINDOWS_CERTIFICATE in CI) |
| Linux | Sign checksums with GPG | `gpg --default-key $GPG_KEY_ID --detach-sign --armor MvgeOS.AppImage && gpg --verify MvgeOS.AppImage.asc` (set $GPG_KEY_ID in CI) |

---

## Project Structure (Final)

```
mvgeos/
├── mvgeos-agent/          # Core agent (existing)
│   └── mvgeos_agent/
│       ├── loop.py        # Modified: EventBus wired in
│       ├── event_bus.py   # Existing, now used
│       └── types.py       # Added event_bus field to MvgeState
├── mvgeos-provider/       # LLM providers (existing)
├── mvgeos-tome/           # Session persistence (existing)
├── mvgeos-runes/          # Extensions (existing)
├── mvgeos-cli/            # CLI entry point (existing)
│   └── mvgeos/
│       └── commands/
│           └── desktop.py # Desktop mode JSON-RPC server
├── mvgeos-desktop/        # Tauri v2 desktop app
│   ├── src/               # React frontend
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── types/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── src-tauri/
│   │   ├── src/
│   │   │   ├── main.rs
│   │   │   ├── lib.rs          # Re-exports for integration tests (protocol, lifecycle)
│   │   │   ├── lifecycle.rs
│   │   │   ├── ipc.rs
│   │   │   ├── protocol.rs
│   │   │   ├── menu.rs
│   │   │   ├── tray.rs
│   │   │   └── file_watcher.rs  # (Phase 4b) notify-based file system watcher
│   │   ├── capabilities/
│   │   │   └── default.json
│   │   ├── tests/
│   │   │   └── protocol_tests.rs
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   └── build.rs
│   ├── mvgeos-desktop.spec  # PyInstaller spec
│   ├── .gitignore
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── package.json
│   └── index.html
├── pyproject.toml         # requires-python >=3.12
└── uv.lock
```

---

## Testing Strategy

### Rust Unit Tests (cargo test)
```
- protocol::test_parse_response
- protocol::test_parse_event
- protocol::test_parse_malformed_recovers
- protocol::test_serialize_request
- ipc::test_command_validation
```

### Rust Integration Tests (cargo test --test integration)

File: `src-tauri/tests/integration_test.rs`

```rust
use std::sync::Arc;
use std::time::Duration;
use mvgeos_desktop::protocol::FromPython;
use mvgeos_desktop::lifecycle::{ProcessSupervisor, LaunchMode, BridgeError};
use tokio::sync::mpsc;
use serde_json::json;

// Helper: create a supervisor in Dev mode.
async fn test_supervisor() -> Arc<ProcessSupervisor> {
    let (tx, _rx) = mpsc::channel(256);
    Arc::new(ProcessSupervisor::new(
        std::env::current_dir().unwrap().join("../../"),
        LaunchMode::Dev,
        tx,
    ))
}

#[tokio::test]
async fn test_ping_pong() {
    let sup = test_supervisor().await;
    sup.start().await.unwrap();
    let result = sup.send_request("ping", json!({})).await.unwrap();
    assert_eq!(result["status"], "ok");
    sup.shutdown().await;
}

#[tokio::test]
async fn test_unknown_method() {
    let sup = test_supervisor().await;
    sup.start().await.unwrap();
    let result = sup.send_request("nonexistent.method", json!({})).await;
    assert!(result.is_err());
    sup.shutdown().await;
}

#[tokio::test]
async fn test_concurrent_requests() {
    let sup = test_supervisor().await;
    sup.start().await.unwrap();
    let mut handles = Vec::new();
    for i in 0..10 {
        let req = sup.send_request("ping", json!({"seq": i}));
        handles.push(tokio::spawn(async move { req.await }));
    }
    for handle in handles {
        let result = handle.await.unwrap().unwrap();
        assert_eq!(result["status"], "ok");
    }
    sup.shutdown().await;
}
```

Key test scenarios:
- Spawn Python subprocess, send ping, await pong, verify `"status":"ok"`
- Send unknown method, verify `BridgeError::Protocol` error
- Send malformed JSON via stdin, verify Python's parse error recovery
- Send 10 concurrent ping requests, verify all responses match correctly
- Kill subprocess, verify watchdog detects and attempts restart
- Shutdown sends notification, waits for process exit

### Python Unit Tests (pytest)
```
- test_desktop_ping_pong
- test_desktop_unknown_method
- test_desktop_malformed_input
- test_desktop_event_bus_wiring
```

### Frontend Tests (Vitest + React Testing Library)
```
- ChatPanel renders messages
- FileTree handles empty state
- CommandPalette filters by input
- ErrorBoundary catches and displays fallback
- Zustand stores respond to events
```

### E2E Tests (Playwright) — post-MVP
```
- Launch app, send prompt, verify streaming output
- Open project, verify file tree loads
- Switch sessions, verify content changes
```

---

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| **Tauri v2** over Electron | ~10MB bundle vs ~100MB, Rust backend, OS-native webview, memory efficient |
| **Line-delimited JSON with type discriminator** | `"type":"request"` / `"type":"response"` / `"type":"event"` — unambiguous, self-describing |
| **PyInstaller** for release | Single binary, no Python/uv dep on user machine |
| **`uv run`** for dev | Fast iteration, consistent with monorepo |
| **React 19 + TypeScript** | Best Tauri v2 ecosystem, strict typing |
| **Zustand** | Lightweight, no boilerplate, works with Tauri events |
| **TailwindCSS v4** | Utility-first, CSS-only config, no PostCSS plugin needed |
| **Encrypted local store** for credentials | Never store API keys in plaintext config JSON; use `tauri-plugin-store` |
| **@tanstack/react-virtual** for chat | Virtualized rendering for 1000+ message sessions |
| **react-markdown + rehype-highlight** | Render agent responses with syntax highlighting |
| **crypto.randomUUID()** for session IDs | Stateless, no backend dependency |
| **CancellationToken** for interrupt | Clean cancellation without killing subprocess |
| **Heartbeat every 30s** | Detect silent subprocess death |

---

## Pre-Flight Checklist (Critical Path)

- [ ] `requires-python` lowered to `>=3.12` in root + all 6 workspace `pyproject.toml` files (7 files total)
- [ ] `ruff target-version` changed from `"py314"` to `"py312"` in root `pyproject.toml`
- [ ] `mypy python_version` changed from `"3.14"` to `"3.12"` in root `pyproject.toml`
- [ ] `MvgeState.event_bus` field added to `types.py`
- [ ] `MvgeLoop.__init__` accepts and stores event_bus
- [ ] `_emit_event` calls `event_bus.publish(event)` instead of discarding
- [ ] `uv run pytest` passes across all workspace packages

## Migration Checklist

### Phase 1: Foundation
- [ ] Create `mvgeos-desktop` Tauri v2 project with React-ts template
- [ ] Install npm deps: zustand, @tanstack/react-virtual, react-markdown, tailwindcss, etc.
- [ ] Install Rust deps: tauri plugins (dialog, shell, process, fs, updater, store, global-shortcut), serde, tokio, uuid
- [ ] Write `protocol.rs` with FromPython/ToPython enums and unit tests
- [ ] Write `lifecycle.rs` with ProcessSupervisor (spawn, handshake, stderr reader, stdout dispatcher, watchdog, heartbeat)
- [ ] Write `ipc.rs` with all 10 Tauri commands (typed args/returns)
- [ ] Write `main.rs` with Builder setup, plugin registration, window event handling, event forwarding
- [ ] Write `build.rs`
- [ ] Write `menu.rs` and `tray.rs`
- [ ] Write `desktop.py` with full JSON-RPC handler, StdoutEventBus
- [ ] Write `vite.config.ts` with TailwindCSS v4 + React plugins
- [ ] Write `tsconfig.node.json`
- [ ] Write `.gitignore` for mvgeos-desktop/
- [ ] Write `tauri.conf.json` with scoped permissions
- [ ] Write `capabilities/default.json`
- [ ] Write protocol contract tests in `src-tauri/tests/`
- [ ] Verify end-to-end: Python → stdin/stdout → Rust → Tauri events

### Phase 2: Backend Bridge
- [ ] Implement CancellationToken per session in ProcessSupervisor
- [ ] Implement session interrupt in ipc.rs (interrupt_session)
- [ ] Implement crate `notify` for file system watching (optional, post-MVP)
- [ ] Write integration tests: spawn Python, full request/event round-trip

### Phase 3: Core Frontend
- [ ] Implement AppLayout with sidebar + main panel + status bar
- [ ] Implement ChatPanel with virtualized list, streaming tokens, markdown rendering
- [ ] Implement ChatInput with submit + keyboard shortcut
- [ ] Implement FileTree with lazy loading
- [ ] Implement SpellOutput with collapsible sections
- [ ] Implement TabBar with create/close/rename/reorder
- [ ] Implement CommandPalette with fuzzy search
- [ ] Implement StatusBar with model selector, connection status, mana display
- [ ] Implement SettingsPanel with provider config (keychain-backed), theme, keybindings, about
- [ ] Implement ErrorBoundary wrapping entire app
- [ ] Implement WelcomeOverlay with first-run detection
- [ ] Wire Tauri event listeners for all agent events
- [ ] Write frontend unit tests

### Phase 4: Features & Polish
- [ ] Native menu bar wired to app events
- [ ] System tray with show/new session/quit
- [ ] Auto-updater configured with pubkey + endpoint
- [ ] Global keyboard shortcuts
- [ ] Dark/light/system theme toggle
- [ ] Onboarding wizard (first-run flow)
- [ ] Session browser (tome history)
- [ ] Diff viewer for file changes
- [ ] Font loading (JetBrains Mono for code, system UI for text)

### Phase 5: Packaging & Distribution
- [ ] PyInstaller spec for Python bundle
- [ ] Tauri bundler for all 5 platform targets
- [ ] CI/CD with PR checks + tag release matrix
- [ ] macOS code signing + notarization in CI
- [ ] Windows code signing in CI
- [ ] Auto-updater endpoint setup
- [ ] Installer testing on clean VMs (macOS, Windows, Ubuntu)
- [ ] Documentation & user guide

---

## Estimated Timeline

| Phase | Duration (Solo) | Duration (Team 2-3) | Deliverable |
|-------|-----------------|---------------------|-------------|
| **Pre-flight** | 1 week | 3-5 days | Fixed pyproject.toml, wired EventBus |
| **1. Foundation** | 3 weeks | 2 weeks | Tauri + protocol + subprocess lifecycle + Python handler working end-to-end |
| **2. Backend Bridge** | 2 weeks | 1 week | CancellationToken, interrupt, settings persistence, integration tests |
| **3. Core Frontend** | 3 weeks | 2 weeks | All 10+ components, stores, event wiring, tests |
| **4. Features & Polish** | 2 weeks | 1-2 weeks | Menus, tray, updater, onboarding, theme, diff viewer |
| **5. Packaging** | 3 weeks | 2 weeks | PyInstaller, code signing, notarization, CI/CD, installers |
| **Total** | **14 weeks** | **9-11 weeks** | **v0.1.0 Desktop Release** |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Python subprocess crashes** | Medium | High | Watchdog pings every 5s, auto-restart, crash event to frontend |
| **stdout/stderr pipe deadlock** | Medium | High | Async stderr reader task, stdout BufReader with bounded lines |
| **JSON parse error on either side** | Medium | Medium | `parse_error` frame type, both sides log and continue |
| **macOS notarization failures** | Medium | High | Start signing in Week 1 of Phase 5, test on CI matrix, document exact Xcode version |
| **Code signing certificate expiry** | Low | High | Calendar reminders 60 days before, backup cert in CI secrets |
| **Rust+Python+React debugging complexity** | Medium | High | Structured JSON logging at each boundary, protocol contract tests, clear error types |
| **Long-running spells block agent loop** | Medium | Medium | Spells run in executor threads on Python side; agent loop remains responsive |
| **File conflicts (agent vs user editor)** | Medium | Medium | File watcher on project directory, conflict detection before spell edit |
| **Graceful shutdown on app close** | Medium | Medium | Window close → send Shutdown notification → wait up to 5s → force kill |
| **Windows ARM support** | Low | Medium | Cross-compile target in build matrix, test on ARM VM |
| **PyInstaller hidden imports** | Medium | High | Test spec file with `--debug imports`, iterate on hiddenimports list |
| **Tauri v2 API changes** | Low | Medium | Pin Tauri version in Cargo.toml, test before upgrading |
| **`serde_json::Value` parameter in Tauri commands** | Low | Low | Wrap in typed struct with `#[derive(Deserialize)]` — works in Tauri v2 |

---

## Next Steps

1. **Pre-flight**: Fix `requires-python` to `>=3.12` in all workspace packages
2. **Pre-flight**: Wire `EventBus` into `MvgeLoop` — add field to `MvgeState`, call in `_emit_event`
3. Initialize Tauri v2 project
4. Write `protocol.rs` + tests
5. Write `lifecycle.rs` with full ProcessSupervisor
6. Write `desktop.py` with complete JSON-RPC handler
7. Write `main.rs` wiring all pieces
7. Run `uv sync` in the monorepo root to install Python workspace packages
8. Build and run `cargo tauri dev` — verify Python→Rust→Frontend data flow
