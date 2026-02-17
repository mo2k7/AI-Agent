# File Documentation: hot_reload.py

## File Metadata
| Field | Value |
|---|---|
| File Path | `agent_host/ipc/hot_reload.py` |
| Language | Python |
| Role | library |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Feature: Hot reload system for Python code changes |
| Current Status | Active |
| LOC (approx) | 294 |

---

## Purpose / Summary
Hot reload system that allows the Python backend to automatically detect code changes and reload modules without requiring a full process restart. This is critical for developer productivity and for live model selection to take effect without manual intervention.

---

## Key Features
1. **File System Watching**: Polls `.py` files in `agent_host/` every 2 seconds for mtime changes
2. **SIGHUP Signal Handling**: External processes can trigger reload via `kill -HUP <pid>`
3. **IPC Command Support**: Frontend can request reload via `reload` IPC method
4. **Ordered Module Reloading**: Modules are reloaded in dependency order
5. **Cooldown Protection**: 1-second cooldown prevents rapid successive reloads
6. **Callback System**: Other components can subscribe to reload events

---

## Public Interfaces

### Classes

#### `FileState`
```python
@dataclass
class FileState:
    path: Path
    mtime: float
    
    @classmethod
    def from_path(cls, path: Path) -> "FileState"
    
    def has_changed(self) -> bool
```
Tracks modification timestamps for individual files.

#### `ReloadEvent`
```python
@dataclass
class ReloadEvent:
    timestamp: float
    trigger: str  # 'file_change', 'signal', 'ipc', 'manual'
    changed_files: list[str]
    success: bool
    error: Optional[str]
```
Event emitted when code reload is triggered or completes.

#### `HotReloadManager`
```python
class HotReloadManager:
    RELOAD_MODULES = [
        "agent_host.config",
        "agent_host.gemini_client",
        "agent_host.tool_parser",
        "agent_host.schema_validator",
        "agent_host.ipc.protocol",
        "agent_host.ipc.server",
    ]
    
    def __init__(self, watch_dir: Optional[Path] = None, poll_interval: float = 2.0, auto_watch: bool = True)
    
    @property
    def version(self) -> int
    
    def on_reload(self, callback: Callable[[ReloadEvent], Any]) -> None
    def reload_modules(self, trigger: str = "manual", changed_files: Optional[list[str]] = None) -> ReloadEvent
    async def start(self) -> None
    async def stop(self) -> None
```
Main manager class for hot reloading. Handles file watching, signal handling, and module reloading.

### Module Functions

#### `get_reload_manager()`
```python
def get_reload_manager() -> HotReloadManager
```
Get the global singleton HotReloadManager instance.

#### `init_reload_manager()`
```python
def init_reload_manager(
    watch_dir: Optional[Path] = None,
    poll_interval: float = 2.0,
    auto_watch: bool = True,
) -> HotReloadManager
```
Initialize the global HotReloadManager with custom settings.

---

## Dependencies
- `asyncio`: For async file watching loop
- `importlib`: For `importlib.reload()` function
- `signal`: For SIGHUP handler registration
- `logging`: For debug/info/error logs
- `pathlib.Path`: For file path handling
- `dataclasses`: For FileState and ReloadEvent

---

## How It Works

### File Watching
1. On startup, scans all `.py` files in `agent_host/` and records their mtimes
2. Every 2 seconds, re-scans and compares mtimes
3. If any file's mtime is newer, triggers a reload

### Module Reloading
Uses `importlib.reload()` in a specific order defined by `RELOAD_MODULES`:
1. First reloads `config.py` (base configuration)
2. Then `gemini_client.py` (API client)
3. Then parsers/validators
4. Finally `protocol.py` and `server.py`

The order matters because later modules may import from earlier ones.

### Version Tracking
- `_version` is an integer timestamp updated after each successful reload
- Clients can query version to check if reload occurred
- Used by `SystemMessage.version_info()` IPC response

---

## Integration Points

### main.py Integration
```python
# In main.py
from agent_host.ipc.hot_reload import get_reload_manager

async def handle_reload(request, client):
    event = reload_manager.reload_modules(trigger="ipc")
    # Send SystemMessage.reload_complete()

async def handle_version(request, client):
    # Send SystemMessage.version_info() with reload_manager.version
```

### Signal Integration
External tools can trigger reload:
```bash
kill -HUP $(pgrep -f "python.*agent_host")
```

---

## Known Issues / Risks
| Issue | Severity | Notes |
|---|---|---|
| Polling not real-time | Low | 2-second delay acceptable for development |
| No file system events | Low | macOS FSEvents would be faster but adds complexity |
| Import order dependencies | Medium | If new modules added, RELOAD_MODULES must be updated |

---

## Test Coverage
- No unit tests yet (low priority as this is a development tool)
- Manual testing: Change a .py file, observe reload in logs

---

## Related Files
| File | Relationship |
|---|---|
| `agent_host/main.py` | Integrates HotReloadManager and registers IPC handlers |
| `agent_host/ipc/protocol.py` | Defines SystemMessage for reload status |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Swift side for ReloadRequest/SystemResponse |

---

## Change Log (Last 5 Edits)
| Date | Modified By | WHY | Summary |
|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial implementation | Created hot reload system with file watching, signal handling, IPC support |
