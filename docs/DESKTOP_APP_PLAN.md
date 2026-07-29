# MvgeOS Desktop App Implementation Plan

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                        MvgeOS Desktop                           │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (Tauri WebView - WebView2/GTK WebKit/Cocoa WebKit)   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  React + TypeScript + TailwindCSS (SolidJS or React)    │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────────┐  │   │
│  │  │ Chat    │ │ File    │ │ Spell   │ │ Settings/     │  │   │
│  │  │ Panel   │ │ Tree    │ │ Output  │ │ Config        │  │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └───────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  IPC Layer (Tauri Commands + Events)                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  invoke('agent:run')  →  Rust → Python subprocess       │   │
│  │  invoke('spell:cast')   →  Rust → Python subprocess     │   │
│  │  invoke('tome:read')    →  Rust → Python subprocess     │   │
│  │  listen('agent:event')  ←  Python stdout/stderr events  │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  Backend Bridge (Rust)                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  - Manages Python subprocess (uv run mvgeos ...)        │   │
│  │  - JSON-RPC over stdin/stdout                           │   │
│  │  - Event streaming (Server-Sent Events style)           │   │
│  │  - Lifecycle: start, restart, graceful shutdown         │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  Python Core (Existing MvgeOS Packages)                         │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐ ┌──────────┐  │
│  │  cli    │ │  agent   │ │ provider│ │ tome  │ │ spells  │  │
│  └─────────┘ └──────────┘ └─────────┘ └───────┘ └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Foundation (Week 1-2)

### 1.1 Tauri Project Setup

```bash
# Create Tauri project in mvgeos-desktop/
cd mvgeos
npm create tauri-app@latest mvgeos-desktop -- --template react-ts
```

**Structure:**

```text
mvgeos-desktop/
├── src/                    # React frontend
│   ├── components/
│   ├── hooks/
│   ├── stores/             # Zustand/Redux for state
│   ├── types/
│   └── App.tsx
├── src-tauri/              # Rust backend
│   ├── src/
│   │   ├── main.rs
│   │   ├── python_bridge.rs
│   │   ├── ipc.rs
│   │   ├── lifecycle.rs
│   │   └── config.rs
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── build.rs
├── package.json
└── tsconfig.json
```

### 1.2 Rust → Python Bridge Design

### Communication Protocol

JSON-RPC 2.0 over stdin/stdout

```rust
// python_bridge.rs
pub struct PythonBridge {
    child: Child,
    tx: mpsc::Sender<Value>,     // Outgoing to Python
    rx: mpsc::Receiver<Value>,   // Incoming from Python
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "method")]
enum PythonRequest {
    AgentRun { session_id: String, prompt: String, model: ModelConfig },
    SpellCast { spell: String, args: Value },
    TomeRead { path: String },
    TomeWrite { path: String, content: String },
    ConfigGet { key: String },
    ConfigSet { key: String, value: Value },
    Shutdown,
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "event")]
enum PythonEvent {
    AgentToken { session_id: String, token: String },
    AgentToolCall { session_id: String, tool: String, args: Value },
    AgentToolResult { session_id: String, tool: String, result: Value },
    AgentComplete { session_id: String, result: Value },
    AgentError { session_id: String, error: String },
    SpellProgress { spell: String, progress: f32 },
    Log { level: String, message: String },
}
```

### 1.3 Python Entry Point for Desktop

Create `mvgeos-desktop` command in `mvgeos-cli`:

```python
# mvgeos_cli/commands/desktop.py
import json
import sys
from typing import Any
from mvgeos_agent.loop import MvgeLoop
from mvgeos_agent.types import MvgeState


async def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    try:
        if method == "agent.run":
            result = await run_agent(params)
        elif method == "spell.cast":
            result = await cast_spell(params)
        # ... other methods
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -1, "message": str(e)},
        }


async def main():
    # Read JSON-RPC from stdin, write responses to stdout
    for line in sys.stdin:
        request = json.loads(line)
        response = await handle_request(request)
        print(json.dumps(response), flush=True)
```

### 1.4 Tauri Configuration

```json
// tauri.conf.json
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
    "windows": [
      {
        "title": "MvgeOS",
        "width": 1400,
        "height": 900,
        "minWidth": 1000,
        "minHeight": 700,
        "center": true,
        "resizable": true,
        "fullscreen": false,
        "decorations": true,
        "transparent": false
      }
    ],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' ipc: http://localhost:5173"
    }
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "icon": ["icons/icon.png", "icons/icon.icns", "icons/icon.ico"],
    "windows": {
      "nsis": { "installerIcon": "icons/icon.ico" }
    },
    "macOS": {
      "entitlements": "entitlements.plist"
    }
  },
  "plugins": {
    "shell": { "open": true },
    "dialog": { "open": true, "save": true },
    "fs": { "all": true },
    "process": { "launch": true, "exit": true }
  }
}
```

---

## Phase 2: Core Frontend (Week 2-3)

### 2.1 State Management (Zustand)

```typescript
// src/stores/agentStore.ts
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

interface AgentState {
  sessions: Map<string, AgentSession>;
  activeSessionId: string | null;
  createSession: (config: SessionConfig) => string;
  sendMessage: (sessionId: string, prompt: string) => Promise<void>;
  onEvent: (event: AgentEvent) => void;
}

interface AgentSession {
  id: string;
  messages: Message[];
  status: 'idle' | 'running' | 'error';
  model: ModelConfig;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
}
```

### 2.2 Core UI Components

| Component | Description | Key Features |
| ----------- | ----------- | ----------- |
| ChatPanel | Main conversation view | Streaming, markdown, code, copy |
| FileTree | Project explorer | Lazy load, git status, context menu |
| SpellOutput | Tool execution panel | Collapsible, live logs, progress |
| TabBar | Multi-session tabs | New tab, close, rename, reorder |
| StatusBar | Bottom bar | Model selector, mana, connection |
| CommandPalette | Cmd+K / Ctrl+K | Fuzzy search commands, files, settings |

### 2.3 Tauri IPC Commands

```rust
// src-tauri/src/ipc.rs
#[tauri::command]
async fn agent_run(
  session_id: String,
  prompt: String,
  model: ModelConfig,
) -> Result<(), String> {
    PYTHON_BRIDGE.send(PythonRequest::AgentRun { session_id, prompt, model }).await
}

#[tauri::command]
async fn spell_cast(spell: String, args: Value) -> Result<Value, String> {
    PYTHON_BRIDGE.send(PythonRequest::SpellCast { spell, args }).await
}

#[tauri::command]
async fn tome_read(path: String) -> Result<String, String> {
    PYTHON_BRIDGE.send(PythonRequest::TomeRead { path }).await
}

#[tauri::command]
async fn config_get(key: String) -> Result<Value, String> {
    PYTHON_BRIDGE.send(PythonRequest::ConfigGet { key }).await
}

// Event listeners
#[tauri::command]
fn listen_agent_events(window: tauri::Window) {
    // Forward Python events to frontend
}
```

---

## Phase 3: Python Backend Integration (Week 3-4)

### 3.1 Desktop CLI Command

Add to `mvgeos-cli/mvgeos/commands/desktop.py`:

```python
# New command: mvgeos desktop
@app.command()
def desktop(
    project_path: str = typer.Argument(".", help="Project directory"),
    port: int = typer.Option(0, help="Port for WebSocket (0 = stdio)"),
):
    """Run MvgeOS in desktop mode (JSON-RPC over stdio)."""
    asyncio.run(run_desktop_mode(project_path, port))
```

### 3.2 Python Process Manager (Rust)

```rust
// src-tauri/src/lifecycle.rs
pub struct PythonProcess {
    child: Child,
    stdin: tokio::process::ChildStdin,
    stdout: tokio::sync::mpsc::Sender<String>,
}

impl PythonProcess {
    pub async fn spawn(project_path: &Path) -> Result<Self, Error> {
        let mut cmd = Command::new("uv");
        cmd.args(["run", "mvgeos", "desktop"])
           .current_dir(project_path)
           .stdin(Stdio::piped())
           .stdout(Stdio::piped())
           .stderr(Stdio::piped())
           .spawn()?;
        
        // Start stdout/stderr readers
        // Start JSON-RPC dispatcher
    }
    
    pub async fn send(&self, request: PythonRequest) -> Result<Value, Error> {
        // Send request, wait for response with matching ID
    }
    
    pub async fn shutdown(&mut self) {
        self.send(PythonRequest::Shutdown).await.ok();
        self.child.kill().await.ok();
    }
}
```

### 3.3 Event Streaming

Python emits SSE-style events to stdout:

```python
# In Python desktop handler
async def emit_event(event: PythonEvent):
    print(
        json.dumps({"jsonrpc": "2.0", "method": "event", "params": event.dict()}),
        flush=True,
    )

# Rust reads line by line and emits Tauri events
```

---

## Phase 4: Features & Polish (Week 4-6)

### 4.1 Native Menu Bar (macOS/Windows/Linux)

```rust
// src-tauri/src/menu.rs
fn create_menu() -> Menu {
    Menu::new()
        .add_submenu(Submenu::new("File", Menu::new()
            .add_item(MenuItem::new("New Session", "cmd+n"))
            .add_item(MenuItem::new("Open Project...", "cmd+o"))
            .add_separator()
            .add_item(MenuItem::new("Quit", "cmd+q"))
        ))
        .add_submenu(Submenu::new("Edit", Menu::new()
            .add_item(MenuItem::new("Copy", "cmd+c"))
            .add_item(MenuItem::new("Paste", "cmd+v"))
        ))
        .add_submenu(Submenu::new("View", Menu::new()
            .add_item(MenuItem::new("Toggle File Tree", "cmd+b"))
            .add_item(MenuItem::new("Toggle Spell Output", "cmd+shift+b"))
        ))
        .add_submenu(Submenu::new("Mvge", Menu::new()
            .add_item(MenuItem::new("Interrupt", "cmd+c"))
            .add_item(MenuItem::new("Clear Session", "cmd+k"))
        ))
}
```

### 4.2 System Tray (Background Mode)

```rust
// src-tauri/src/tray.rs
fn create_tray(app: &tauri::AppHandle) -> Result<TrayIcon> {
    TrayIconBuilder::new()
        .icon(app.default_window_icon().unwrap())
        .menu(&Menu::new()
            .add_item(MenuItem::new("Show", "show"))
            .add_item(MenuItem::new("New Session", "new"))
            .add_separator()
            .add_item(MenuItem::new("Quit", "quit"))
        )
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => app.get_window("main").unwrap().show().unwrap(),
            "new" => create_new_session(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .build(app)
}
```

### 4.3 Auto-Updater

```rust
// Cargo.toml
[dependencies]
tauri-plugin-updater = "2"

# tauri.conf.json
"plugins": {
  "updater": {
    "pubkey": "dW50cnVzdGVkIGNvbW1lbnQ...",
    "endpoints": [
      "https://releases.mvgeos.dev/{{target}}/{{current_version}}"
    ],
    "dialog": true
  }
}
```

### 4.4 Keyboard Shortcuts

| Shortcut | Action |
| ---------- | -------- |
| Cmd+N / Ctrl+N | New session |
| Cmd+O / Ctrl+O | Open project |
| Cmd+B / Ctrl+B | Toggle file tree |
| Cmd+Shift+B / Ctrl+Shift+B | Toggle spell output |
| Cmd+K / Ctrl+K | Command palette |
| Cmd+Shift+P / Ctrl+Shift+P | Command palette (full) |
| Cmd+. / Ctrl+. | Interrupt agent |
| Cmd+L / Ctrl+L | Clear session |
| Cmd+1-9 / Ctrl+1-9 | Switch tabs |

---

## Phase 5: Packaging & Distribution (Week 6-7)

### 5.1 Build Targets

| Platform | Target | Output |
| ---------- | -------- | -------- |
| macOS (ARM) | aarch64-apple-darwin | .dmg, .app |
| macOS (Intel) | x86_64-apple-darwin | .dmg, .app |
| Windows | x86_64-pc-windows-msvc | .msi, .exe |
| Linux | x86_64-unknown-linux-gnu | .AppImage, .deb, .rpm |

### 5.2 GitHub Actions Workflow

```yaml
# .github/workflows/desktop-release.yml
name: Desktop Release

on:
  push:
    tags: ['v*']

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: macos-latest
            target: aarch64-apple-darwin
          - os: macos-latest
            target: x86_64-apple-darwin
          - os: windows-latest
            target: x86_64-pc-windows-msvc
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}
      - uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TAURI_PRIVATE_KEY: ${{ secrets.TAURI_PRIVATE_KEY }}
          TAURI_KEY_PASSWORD: ${{ secrets.TAURI_KEY_PASSWORD }}
```

### 5.3 Code Signing

| Platform | Certificate | Method |
| ---------- | ------------- | -------- |
| macOS | Developer ID Application | codesign --deep --force --verify |
| Windows | EV Code Signing Cert | signtool sign /fd sha256 /tr timestamp URL |
| Linux | GPG Key | gpg --detach-sign --armor |

---

## Project Structure (Final)

```text
mvgeos/
├── mvgeos-agent/          # Core agent (existing)
├── mvgeos-provider/       # LLM providers (existing)
├── mvgeos-tome/           # Session persistence (existing)
├── mvgeos-spells/         # Tool implementations (existing)
├── mvgeos-runes/          # Extensions (existing)
├── mvgeos-cli/            # CLI entry point (existing)
│   └── mvgeos/
│       └── commands/
│           └── desktop.py # NEW: Desktop mode entry
├── mvgeos-desktop/        # NEW: Tauri desktop app
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── hooks/         # Custom React hooks
│   │   ├── stores/        # Zustand stores
│   │   ├── types/         # TypeScript types
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── src-tauri/
│   │   ├── src/
│   │   │   ├── main.rs
│   │   │   ├── python_bridge.rs
│   │   │   ├── ipc.rs
│   │   │   ├── lifecycle.rs
│   │   │   ├── menu.rs
│   │   │   ├── tray.rs
│   │   │   └── config.rs
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   └── build.rs
│   ├── package.json
│   └── tsconfig.json
├── pyproject.toml         # Workspace root
└── uv.lock
```

---

## Key Technical Decisions

| Decision | Rationale |
| ---------- | ----------- |
| Tauri over Electron | Smaller bundle, Rust backend, Python stdio |
| JSON-RPC over stdio | Simple, language-agnostic, uv workflow |
| uv for Python management | Consistent with MvgeOS, auto virtualenvs |
| Zustand for state | Lightweight, TypeScript-first, Tauri events |
| React + TypeScript | Familiar, good Tauri integration, ecosystem |
| TailwindCSS | Utility-first, matches aesthetic, small bundle |

---

## Migration Checklist

- [ ] Create `mvgeos-desktop` Tauri project
- [ ] Add `desktop` command to `mvgeos-cli`
- [ ] Implement Python JSON-RPC server in `desktop.py`
- [ ] Build Rust `PythonBridge` with process management
- [ ] Define TypeScript/Rust/Python shared types
- [ ] Implement core UI: ChatPanel, FileTree, SpellOutput
- [ ] Add Tauri commands for agent/spell/tome/config
- [ ] Implement event streaming (Python → Rust → Frontend)
- [ ] Native menus, system tray, keyboard shortcuts
- [ ] Auto-updater with GitHub releases
- [ ] Code signing for all platforms
- [ ] CI/CD pipeline for releases
- [ ] Installer testing on clean VMs
- [ ] Documentation & user guide

---

## Estimated Timeline

| Phase | Duration | Deliverable |
| ------- | ---------- | ------------- |
| 1. Foundation | 2 weeks | Tauri + Rust bridge + Python desktop command |
| 2. Core Frontend | 2 weeks | Chat, FileTree, SpellOutput, TabBar |
| 3. Backend Integration | 2 weeks | Full agent loop, spell casting, tome ops |
| 4. Features & Polish | 2 weeks | Menus, tray, shortcuts, settings, themes |
| 5. Packaging | 2 weeks | Signed builds, updater, CI/CD, release |
| Total | ~10 weeks | v0.1.0 Desktop Release |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
| ------ | ------------- | -------- | ------------ |
| Python subprocess crashes | Medium | High | Supervisor, auto-restart, reports |
| JSON-RPC protocol mismatch | Low | Medium | Shared schemas, tests |
| WebView rendering differences | Medium | Medium | Test all platforms, CSS resets |
| Large bundle size | Low | Low | Tauri is small; audit deps |
| Code signing complexity | Medium | High | Start early, document, CI secrets |

---

## Next Steps

1. Initialize Tauri project: npm create tauri-app@latest mvgeos-desktop
2. Add desktop command to mvgeos-cli
3. Define shared types (TypeScript ↔ Rust ↔ Python)
4. Build PythonBridge in Rust with tests
5. Implement first end-to-end flow: User → Frontend → Rust → Python → Agent → Events → Frontend
