# Electron CDP Support Design

**Goal:** Enable the harness to automate any Electron app by transparently routing UI commands through Chrome DevTools Protocol (CDP) instead of Windows UI Automation.

**Architecture:** Unified UI automation layer in the .NET sidecar. The existing `/ui/*` endpoints become a facade over two backends — Windows UI Automation for native apps, CDP for Electron apps. The agent sees no difference.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Any arbitrary Electron app | General-purpose, not app-specific |
| CDP connection | Auto-detect + relaunch | Detect Electron process, kill, relaunch with `--remote-debugging-port`, connect |
| Interaction level | Full DOM interaction | Read DOM tree + click/type/invoke via JS. No network-layer features |
| CDP logic location | In sidecar, same `/ui/*` API shape | Agent doesn't need to know which backend is used |
| Backend selection | Per-window caching | First `/ui/*` call detects and caches; subsequent calls are instant |

## Backend Detection

On first `/ui/*` call for a window:
1. Get the window's process (PID from window handle)
2. Check if process is Electron: look for `electron.exe` in process name, or Chromium DLLs (`libcef.dll`, `chrome_elf.dll`) in the process directory
3. If Electron: kill process, find its executable path, relaunch with `--remote-debugging-port=<dynamic-port>`, poll `http://127.0.0.1:<port>/json` until ready, connect via CDP websocket
4. If native: use existing UI Automation code
5. Cache the backend keyed by window handle

## CDP-to-UI Endpoint Mapping

| Endpoint | CDP Implementation |
|----------|-------------------|
| `ui/inspect_active_window` | `Runtime.evaluate` to walk DOM, return element tree (tag, id, class, text, role, bounding rect via `getBoundingClientRect`) |
| `ui/find_element` | `Runtime.evaluate` with CSS/attribute selectors matching name/automationId/controlType to HTML equivalents (aria-label, id, role) |
| `ui/click_element` | `Runtime.evaluate` to find element + `DOM.getBoxModel` for coords + `Input.dispatchMouseEvent`, or direct `.click()` via JS |
| `ui/set_text` | `Runtime.evaluate` to focus element + set `.value` + dispatch `input`/`change` events |
| `ui/invoke` | `Runtime.evaluate` to `.click()` the element |

## Interface Abstraction

```csharp
interface IUIBackend
{
    UIElementInfo InspectActiveWindow(int maxDepth);
    List<UIElementInfo> FindElements(string? name, string? automationId, string? controlType);
    (bool Success, string Message) ClickElement(string? name, string? automationId, int index);
    (bool Success, string Message) SetText(string? name, string? automationId, string text, int index);
    (bool Success, string Message) InvokeElement(string? name, string? automationId, int index);
}
```

Existing UI Automation code gets extracted into `WindowsUIBackend : IUIBackend`. New CDP code goes into `CdpUIBackend : IUIBackend`. A `UIBackendRouter` holds the per-window cache and delegates.

## Relaunch Strategy

- Find process executable path via `Process.MainModule.FileName`
- Find original command-line args via WMI or `/proc` equivalent
- Kill process, relaunch with original args + `--remote-debugging-port=<port>`
- Port selection: start at 9222, increment if busy
- Poll `http://127.0.0.1:<port>/json` with timeout (5s) to detect readiness
- On failure: fall back to screenshot+mouse (log warning, don't crash)

## What Does NOT Change

- System prompt (tool selection strategy stays the same)
- Tool definitions (sidecar.call operations stay the same)
- Python harness code (SidecarTool just POSTs to sidecar)
- Agent behavior (it just calls sidecar and gets results)
