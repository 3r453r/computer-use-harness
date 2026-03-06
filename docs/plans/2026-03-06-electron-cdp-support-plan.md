# Electron CDP Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable the sidecar to transparently automate Electron apps via CDP, behind the same `/ui/*` API the agent already uses.

**Architecture:** Extract existing UI Automation code behind an `IUIBackend` interface. Add a CDP backend that connects to Electron apps' DevTools Protocol. A `UIBackendRouter` detects Electron processes, manages relaunch + CDP connection, caches backends per window, and delegates `/ui/*` calls to the right backend.

**Tech Stack:** C# / .NET 8, System.Windows.Automation (existing), System.Net.WebSockets (CDP transport), System.Text.Json (CDP messages), System.Diagnostics.Process (Electron detection + relaunch)

---

### Task 1: Extract IUIBackend interface

**Files:**
- Create: `dotnet-sidecar/LocalWindowsSidecar/IUIBackend.cs`

**Step 1: Create the interface file**

```csharp
using LocalWindowsSidecar.Models;

namespace LocalWindowsSidecar;

/// <summary>
/// Abstraction over UI automation backends (Windows UI Automation, CDP, etc.)
/// </summary>
public interface IUIBackend : IDisposable
{
    UIElementInfo? InspectActiveWindow(int maxDepth);
    List<UIElementInfo> FindElements(string? name, string? automationId, string? controlType);
    (bool Success, string Message) ClickElement(string? name, string? automationId, int index);
    (bool Success, string Message) SetText(string? name, string? automationId, string text, int index);
    (bool Success, string Message) InvokeElement(string? name, string? automationId, int index);
}
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/IUIBackend.cs
git commit -m "feat: add IUIBackend interface for pluggable UI backends"
```

---

### Task 2: Extract WindowsUIBackend from UIAutomationHelper

**Files:**
- Create: `dotnet-sidecar/LocalWindowsSidecar/WindowsUIBackend.cs`
- Modify: `dotnet-sidecar/LocalWindowsSidecar/UIAutomationHelper.cs` (keep as static helpers, referenced by WindowsUIBackend)

**Step 1: Create WindowsUIBackend that delegates to existing UIAutomationHelper**

```csharp
using LocalWindowsSidecar.Models;

namespace LocalWindowsSidecar;

/// <summary>
/// UI backend using Windows UI Automation (System.Windows.Automation).
/// Wraps existing UIAutomationHelper static methods behind the IUIBackend interface.
/// </summary>
public class WindowsUIBackend : IUIBackend
{
    public UIElementInfo? InspectActiveWindow(int maxDepth)
    {
        var root = UIAutomationHelper.GetActiveWindowElement();
        if (root == null) return null;
        return UIAutomationHelper.BuildTree(root, maxDepth);
    }

    public List<UIElementInfo> FindElements(string? name, string? automationId, string? controlType)
    {
        var elements = UIAutomationHelper.FindElements(name, automationId, controlType);
        return elements.Select(UIAutomationHelper.ToElementInfo).ToList();
    }

    public (bool Success, string Message) ClickElement(string? name, string? automationId, int index)
    {
        var elements = UIAutomationHelper.FindElements(name, automationId, controlType: null);
        if (elements.Count == 0) return (false, "No matching elements found");
        if (index < 0 || index >= elements.Count)
            return (false, $"Index {index} out of range. Found {elements.Count} element(s).");
        return UIAutomationHelper.ClickElement(elements[index]);
    }

    public (bool Success, string Message) SetText(string? name, string? automationId, string text, int index)
    {
        var elements = UIAutomationHelper.FindElements(name, automationId, controlType: null);
        if (elements.Count == 0) return (false, "No matching elements found");
        if (index < 0 || index >= elements.Count)
            return (false, $"Index {index} out of range. Found {elements.Count} element(s).");
        return UIAutomationHelper.SetText(elements[index], text);
    }

    public (bool Success, string Message) InvokeElement(string? name, string? automationId, int index)
    {
        var elements = UIAutomationHelper.FindElements(name, automationId, controlType: null);
        if (elements.Count == 0) return (false, "No matching elements found");
        if (index < 0 || index >= elements.Count)
            return (false, $"Index {index} out of range. Found {elements.Count} element(s).");
        return UIAutomationHelper.InvokeElement(elements[index]);
    }

    public void Dispose() { }
}
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/WindowsUIBackend.cs
git commit -m "feat: extract WindowsUIBackend implementing IUIBackend"
```

---

### Task 3: Create ElectronDetector

**Files:**
- Create: `dotnet-sidecar/LocalWindowsSidecar/ElectronDetector.cs`

This class detects whether a process is an Electron app by checking for Chromium markers.

**Step 1: Create the detector**

```csharp
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace LocalWindowsSidecar;

/// <summary>
/// Detects whether a given process is an Electron/CEF application
/// by inspecting loaded modules and process directory for Chromium markers.
/// </summary>
public static class ElectronDetector
{
    private static readonly string[] ChromiumMarkers = new[]
    {
        "libcef.dll",
        "chrome_elf.dll",
        "electron.exe",
        "vk_swiftshader.dll",  // Common in Electron apps
    };

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    /// <summary>
    /// Returns true if the process owning the given window handle is an Electron/CEF app.
    /// </summary>
    public static bool IsElectron(IntPtr hWnd)
    {
        GetWindowThreadProcessId(hWnd, out var pid);
        if (pid == 0) return false;
        return IsElectronProcess((int)pid);
    }

    /// <summary>
    /// Returns true if the given PID is an Electron/CEF app.
    /// Checks process executable directory for Chromium marker files.
    /// </summary>
    public static bool IsElectronProcess(int pid)
    {
        try
        {
            var proc = Process.GetProcessById(pid);
            var exePath = proc.MainModule?.FileName;
            if (string.IsNullOrEmpty(exePath)) return false;

            var dir = Path.GetDirectoryName(exePath);
            if (string.IsNullOrEmpty(dir)) return false;

            // Check if the exe itself is electron.exe
            var exeName = Path.GetFileName(exePath);
            if (exeName.Equals("electron.exe", StringComparison.OrdinalIgnoreCase))
                return true;

            // Check for Chromium marker files in the same directory
            foreach (var marker in ChromiumMarkers)
            {
                if (File.Exists(Path.Combine(dir, marker)))
                    return true;
            }

            // Check resources/electron.asar (definitive Electron marker)
            var resourcesDir = Path.Combine(dir, "resources");
            if (Directory.Exists(resourcesDir) &&
                File.Exists(Path.Combine(resourcesDir, "electron.asar")))
                return true;

            return false;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Gets the executable path for the process owning the given window.
    /// </summary>
    public static string? GetProcessExePath(int pid)
    {
        try
        {
            return Process.GetProcessById(pid).MainModule?.FileName;
        }
        catch
        {
            return null;
        }
    }
}
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/ElectronDetector.cs
git commit -m "feat: add ElectronDetector for identifying Electron/CEF processes"
```

---

### Task 4: Create CdpClient (low-level CDP websocket transport)

**Files:**
- Create: `dotnet-sidecar/LocalWindowsSidecar/CdpClient.cs`

This is the low-level CDP transport — sends JSON-RPC commands over websocket and returns results.

**Step 1: Create CdpClient**

```csharp
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace LocalWindowsSidecar;

/// <summary>
/// Low-level Chrome DevTools Protocol client over WebSocket.
/// Sends JSON-RPC commands and waits for responses.
/// </summary>
public class CdpClient : IDisposable
{
    private readonly ClientWebSocket _ws = new();
    private readonly ConcurrentDictionary<int, TaskCompletionSource<JsonNode?>> _pending = new();
    private int _nextId;
    private CancellationTokenSource _cts = new();
    private Task? _receiveLoop;

    public bool IsConnected => _ws.State == WebSocketState.Open;

    /// <summary>
    /// Connect to a CDP websocket endpoint (e.g. ws://127.0.0.1:9222/devtools/page/xxx).
    /// </summary>
    public async Task ConnectAsync(string wsUrl, CancellationToken ct = default)
    {
        await _ws.ConnectAsync(new Uri(wsUrl), ct);
        _receiveLoop = Task.Run(() => ReceiveLoopAsync(_cts.Token));
    }

    /// <summary>
    /// Send a CDP command and wait for the result.
    /// </summary>
    public async Task<JsonNode?> SendAsync(string method, JsonNode? parameters = null, int timeoutMs = 5000)
    {
        var id = Interlocked.Increment(ref _nextId);
        var tcs = new TaskCompletionSource<JsonNode?>();
        _pending[id] = tcs;

        var msg = new JsonObject
        {
            ["id"] = id,
            ["method"] = method
        };
        if (parameters != null)
            msg["params"] = parameters;

        var bytes = Encoding.UTF8.GetBytes(msg.ToJsonString());
        await _ws.SendAsync(bytes, WebSocketMessageType.Text, true, _cts.Token);

        using var timeoutCts = new CancellationTokenSource(timeoutMs);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token, timeoutCts.Token);
        try
        {
            linked.Token.Register(() => tcs.TrySetCanceled());
            return await tcs.Task;
        }
        catch (TaskCanceledException)
        {
            _pending.TryRemove(id, out _);
            throw new TimeoutException($"CDP command '{method}' timed out after {timeoutMs}ms");
        }
    }

    private async Task ReceiveLoopAsync(CancellationToken ct)
    {
        var buffer = new byte[64 * 1024];
        var sb = new StringBuilder();
        while (!ct.IsCancellationRequested && _ws.State == WebSocketState.Open)
        {
            try
            {
                var result = await _ws.ReceiveAsync(buffer, ct);
                if (result.MessageType == WebSocketMessageType.Close) break;

                sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                if (!result.EndOfMessage) continue;

                var json = sb.ToString();
                sb.Clear();

                var node = JsonNode.Parse(json);
                if (node == null) continue;

                var id = node["id"]?.GetValue<int>();
                if (id.HasValue && _pending.TryRemove(id.Value, out var tcs))
                {
                    if (node["error"] != null)
                        tcs.TrySetException(new Exception($"CDP error: {node["error"]}"));
                    else
                        tcs.TrySetResult(node["result"]);
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch
            {
                // Log and continue
            }
        }
    }

    public void Dispose()
    {
        _cts.Cancel();
        try { _ws.Dispose(); } catch { }
        _cts.Dispose();
    }
}
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/CdpClient.cs
git commit -m "feat: add CdpClient low-level CDP websocket transport"
```

---

### Task 5: Create ElectronLauncher (relaunch with CDP enabled)

**Files:**
- Create: `dotnet-sidecar/LocalWindowsSidecar/ElectronLauncher.cs`

Handles killing the existing Electron process and relaunching with `--remote-debugging-port`.

**Step 1: Create ElectronLauncher**

```csharp
using System.Diagnostics;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace LocalWindowsSidecar;

/// <summary>
/// Manages relaunching Electron apps with --remote-debugging-port enabled,
/// and discovering the CDP websocket URL.
/// </summary>
public static class ElectronLauncher
{
    private static int _nextPort = 9222;
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(2) };

    /// <summary>
    /// Relaunch an Electron app with CDP enabled.
    /// Returns (websocketDebuggerUrl, newPid) or throws on failure.
    /// </summary>
    public static async Task<(string WsUrl, int Pid)> RelaunchWithCdpAsync(int originalPid, int timeoutMs = 8000)
    {
        var proc = Process.GetProcessById(originalPid);
        var exePath = proc.MainModule?.FileName
            ?? throw new Exception($"Cannot get exe path for PID {originalPid}");

        // Pick a port
        var port = Interlocked.Increment(ref _nextPort);
        if (port > 9300) Interlocked.Exchange(ref _nextPort, 9222);

        // Kill the original process
        try { proc.Kill(entireProcessTree: true); } catch { }
        try { proc.WaitForExit(3000); } catch { }

        // Relaunch with CDP flag
        var psi = new ProcessStartInfo
        {
            FileName = exePath,
            Arguments = $"--remote-debugging-port={port}",
            UseShellExecute = false,
        };
        var newProc = Process.Start(psi)
            ?? throw new Exception($"Failed to start {exePath}");

        // Poll /json until CDP is ready
        var wsUrl = await PollForCdpAsync(port, timeoutMs);
        return (wsUrl, newProc.Id);
    }

    /// <summary>
    /// Poll http://127.0.0.1:{port}/json to discover the CDP websocket URL.
    /// Returns the websocket debugger URL of the first page target.
    /// </summary>
    private static async Task<string> PollForCdpAsync(int port, int timeoutMs)
    {
        var deadline = Environment.TickCount64 + timeoutMs;
        while (Environment.TickCount64 < deadline)
        {
            try
            {
                var json = await Http.GetStringAsync($"http://127.0.0.1:{port}/json");
                var targets = JsonNode.Parse(json)?.AsArray();
                if (targets != null)
                {
                    foreach (var target in targets)
                    {
                        var type = target?["type"]?.GetValue<string>();
                        var wsUrl = target?["webSocketDebuggerUrl"]?.GetValue<string>();
                        if (type == "page" && !string.IsNullOrEmpty(wsUrl))
                            return wsUrl;
                    }
                }
            }
            catch
            {
                // Not ready yet
            }
            await Task.Delay(300);
        }
        throw new TimeoutException($"CDP endpoint at port {port} did not become ready within {timeoutMs}ms");
    }
}
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/ElectronLauncher.cs
git commit -m "feat: add ElectronLauncher for restarting Electron apps with CDP"
```

---

### Task 6: Create CdpUIBackend (CDP implementation of IUIBackend)

**Files:**
- Create: `dotnet-sidecar/LocalWindowsSidecar/CdpUIBackend.cs`

This is the main piece — maps `/ui/*` operations to CDP commands via JavaScript evaluation.

**Step 1: Create CdpUIBackend**

```csharp
using System.Text.Json;
using System.Text.Json.Nodes;
using LocalWindowsSidecar.Models;

namespace LocalWindowsSidecar;

/// <summary>
/// UI backend using Chrome DevTools Protocol for Electron apps.
/// Maps the IUIBackend interface to CDP Runtime.evaluate calls.
/// </summary>
public class CdpUIBackend : IUIBackend
{
    private readonly CdpClient _cdp;

    public CdpUIBackend(CdpClient cdp)
    {
        _cdp = cdp;
    }

    public UIElementInfo? InspectActiveWindow(int maxDepth)
    {
        var js = $$"""
        (function() {
            function walk(el, depth, maxD) {
                var rect = el.getBoundingClientRect();
                var node = {
                    name: el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText?.substring(0, 80) || '',
                    automationId: el.id || '',
                    controlType: el.getAttribute('role') || el.tagName.toLowerCase(),
                    boundingRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                    children: []
                };
                if (depth < maxD) {
                    for (var i = 0; i < el.children.length && i < 50; i++) {
                        node.children.push(walk(el.children[i], depth + 1, maxD));
                    }
                }
                if (node.children.length === 0) delete node.children;
                return node;
            }
            return JSON.stringify(walk(document.body, 0, {{maxDepth}}));
        })()
        """;
        var result = EvalSync(js);
        if (result == null) return null;

        try
        {
            return JsonSerializer.Deserialize<UIElementInfo>(result,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }
        catch
        {
            return null;
        }
    }

    public List<UIElementInfo> FindElements(string? name, string? automationId, string? controlType)
    {
        // Build a CSS/attribute selector from the search criteria
        var js = $$"""
        (function() {
            var results = [];
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var elName = el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText?.substring(0, 80) || '';
                var elId = el.id || '';
                var elRole = el.getAttribute('role') || el.tagName.toLowerCase();

                var nameMatch = !('{{name ?? ""}}') || elName.indexOf('{{EscapeJs(name)}}') !== -1;
                var idMatch = !('{{automationId ?? ""}}') || elId === '{{EscapeJs(automationId)}}';
                var typeMatch = !('{{controlType ?? ""}}') || elRole === '{{EscapeJs(controlType)}}';

                if (nameMatch && idMatch && typeMatch) {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            name: elName.substring(0, 80),
                            automationId: elId,
                            controlType: elRole,
                            boundingRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                            _index: i
                        });
                    }
                }
                if (results.length >= 50) break;
            }
            return JSON.stringify(results);
        })()
        """;
        var result = EvalSync(js);
        if (result == null) return new List<UIElementInfo>();

        try
        {
            return JsonSerializer.Deserialize<List<UIElementInfo>>(result,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? new List<UIElementInfo>();
        }
        catch
        {
            return new List<UIElementInfo>();
        }
    }

    public (bool Success, string Message) ClickElement(string? name, string? automationId, int index)
    {
        var elements = FindElements(name, automationId, null);
        if (elements.Count == 0) return (false, "No matching elements found");
        if (index < 0 || index >= elements.Count)
            return (false, $"Index {index} out of range. Found {elements.Count} element(s).");

        var el = elements[index];
        // Click via JS using the element's center coordinates
        var js = $$"""
        (function() {
            var all = document.querySelectorAll('*');
            var matches = [];
            for (var i = 0; i < all.length; i++) {
                var e = all[i];
                var eName = e.getAttribute('aria-label') || e.getAttribute('title') || e.innerText?.substring(0, 80) || '';
                var eId = e.id || '';
                var nameMatch = !('{{EscapeJs(name)}}') || eName.indexOf('{{EscapeJs(name)}}') !== -1;
                var idMatch = !('{{EscapeJs(automationId)}}') || eId === '{{EscapeJs(automationId)}}';
                if (nameMatch && idMatch) {
                    var rect = e.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) matches.push(e);
                }
                if (matches.length > {{index}}) break;
            }
            if (matches.length <= {{index}}) return JSON.stringify({ok: false, msg: 'Element not found at index'});
            var target = matches[{{index}}];
            target.scrollIntoViewIfNeeded?.();
            target.click();
            return JSON.stringify({ok: true, msg: 'Clicked via JS .click()'});
        })()
        """;
        var result = EvalSync(js);
        if (result == null) return (false, "CDP eval returned null");
        try
        {
            var obj = JsonNode.Parse(result);
            return (obj?["ok"]?.GetValue<bool>() ?? false, obj?["msg"]?.GetValue<string>() ?? "unknown");
        }
        catch
        {
            return (false, "Failed to parse click result");
        }
    }

    public (bool Success, string Message) SetText(string? name, string? automationId, string text, int index)
    {
        var js = $$"""
        (function() {
            var all = document.querySelectorAll('*');
            var matches = [];
            for (var i = 0; i < all.length; i++) {
                var e = all[i];
                var eName = e.getAttribute('aria-label') || e.getAttribute('title') || e.innerText?.substring(0, 80) || '';
                var eId = e.id || '';
                var nameMatch = !('{{EscapeJs(name)}}') || eName.indexOf('{{EscapeJs(name)}}') !== -1;
                var idMatch = !('{{EscapeJs(automationId)}}') || eId === '{{EscapeJs(automationId)}}';
                if (nameMatch && idMatch) {
                    var rect = e.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) matches.push(e);
                }
                if (matches.length > {{index}}) break;
            }
            if (matches.length <= {{index}}) return JSON.stringify({ok: false, msg: 'Element not found at index'});
            var target = matches[{{index}}];
            target.focus();
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value')?.set
                || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
            if (nativeInputValueSetter) {
                nativeInputValueSetter.call(target, '{{EscapeJs(text)}}');
            } else {
                target.value = '{{EscapeJs(text)}}';
            }
            target.dispatchEvent(new Event('input', { bubbles: true }));
            target.dispatchEvent(new Event('change', { bubbles: true }));
            return JSON.stringify({ok: true, msg: 'Text set via JS'});
        })()
        """;
        var result = EvalSync(js);
        if (result == null) return (false, "CDP eval returned null");
        try
        {
            var obj = JsonNode.Parse(result);
            return (obj?["ok"]?.GetValue<bool>() ?? false, obj?["msg"]?.GetValue<string>() ?? "unknown");
        }
        catch
        {
            return (false, "Failed to parse set_text result");
        }
    }

    public (bool Success, string Message) InvokeElement(string? name, string? automationId, int index)
    {
        // Invoke is the same as click for web elements
        return ClickElement(name, automationId, index);
    }

    /// <summary>
    /// Synchronously evaluate JS via CDP Runtime.evaluate.
    /// Returns the string value of the expression result, or null.
    /// </summary>
    private string? EvalSync(string expression)
    {
        try
        {
            var parameters = new JsonObject
            {
                ["expression"] = expression,
                ["returnByValue"] = true
            };
            var result = _cdp.SendAsync("Runtime.evaluate", parameters, timeoutMs: 5000)
                .GetAwaiter().GetResult();
            return result?["result"]?["value"]?.GetValue<string>();
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Escape a string for safe embedding in JS string literals.
    /// </summary>
    private static string EscapeJs(string? s)
    {
        if (string.IsNullOrEmpty(s)) return "";
        return s.Replace("\\", "\\\\").Replace("'", "\\'").Replace("\n", "\\n").Replace("\r", "\\r");
    }

    public void Dispose()
    {
        _cdp.Dispose();
    }
}
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/CdpUIBackend.cs
git commit -m "feat: add CdpUIBackend implementing IUIBackend via CDP"
```

---

### Task 7: Create UIBackendRouter (detection + caching + delegation)

**Files:**
- Create: `dotnet-sidecar/LocalWindowsSidecar/UIBackendRouter.cs`

The router detects whether the active window is Electron, manages backends, and delegates calls.

**Step 1: Create UIBackendRouter**

```csharp
using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using LocalWindowsSidecar.Models;

namespace LocalWindowsSidecar;

/// <summary>
/// Routes /ui/* calls to the appropriate backend (Windows UI Automation or CDP)
/// based on whether the active window is an Electron app.
/// Caches backends per window handle.
/// </summary>
public class UIBackendRouter : IUIBackend
{
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    private readonly ConcurrentDictionary<int, IUIBackend> _cache = new(); // keyed by PID
    private readonly WindowsUIBackend _windowsBackend = new();

    /// <summary>
    /// Get or create the appropriate backend for the current foreground window.
    /// </summary>
    public IUIBackend GetBackendForActiveWindow()
    {
        var hWnd = GetForegroundWindow();
        if (hWnd == IntPtr.Zero) return _windowsBackend;

        GetWindowThreadProcessId(hWnd, out var pid);
        if (pid == 0) return _windowsBackend;

        return _cache.GetOrAdd((int)pid, p =>
        {
            if (!ElectronDetector.IsElectronProcess(p))
                return _windowsBackend;

            try
            {
                var (wsUrl, newPid) = ElectronLauncher.RelaunchWithCdpAsync(p)
                    .GetAwaiter().GetResult();

                var cdp = new CdpClient();
                cdp.ConnectAsync(wsUrl).GetAwaiter().GetResult();
                var backend = new CdpUIBackend(cdp);

                // Cache under new PID as well (process was relaunched)
                if (newPid != p)
                    _cache.TryAdd(newPid, backend);

                return backend;
            }
            catch (Exception ex)
            {
                // CDP setup failed — fall back to Windows UI Automation
                Console.Error.WriteLine($"[UIBackendRouter] CDP setup failed for PID {p}: {ex.Message}. Falling back to Windows UI Automation.");
                return _windowsBackend;
            }
        });
    }

    public UIElementInfo? InspectActiveWindow(int maxDepth) => GetBackendForActiveWindow().InspectActiveWindow(maxDepth);
    public List<UIElementInfo> FindElements(string? name, string? automationId, string? controlType) => GetBackendForActiveWindow().FindElements(name, automationId, controlType);
    public (bool Success, string Message) ClickElement(string? name, string? automationId, int index) => GetBackendForActiveWindow().ClickElement(name, automationId, index);
    public (bool Success, string Message) SetText(string? name, string? automationId, string text, int index) => GetBackendForActiveWindow().SetText(name, automationId, text, index);
    public (bool Success, string Message) InvokeElement(string? name, string? automationId, int index) => GetBackendForActiveWindow().InvokeElement(name, automationId, index);

    public void Dispose()
    {
        foreach (var backend in _cache.Values)
        {
            if (backend != _windowsBackend)
                backend.Dispose();
        }
        _cache.Clear();
        _windowsBackend.Dispose();
    }
}
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/UIBackendRouter.cs
git commit -m "feat: add UIBackendRouter with per-window detection and caching"
```

---

### Task 8: Wire UIBackendRouter into Program.cs endpoints

**Files:**
- Modify: `dotnet-sidecar/LocalWindowsSidecar/Program.cs`

Replace direct `UIAutomationHelper` calls in the `/ui/*` endpoints with calls to `UIBackendRouter`.

**Step 1: Add router singleton and refactor endpoints**

At the top of Program.cs, after `var app = builder.Build();`, add:
```csharp
var uiRouter = new UIBackendRouter();
```

Replace all 5 `/ui/*` endpoint bodies. The new endpoints delegate to the router:

```csharp
app.MapPost("/ui/inspect_active_window", () =>
{
    try
    {
        var tree = uiRouter.InspectActiveWindow(maxDepth: 2);
        if (tree == null)
            return Results.Ok(new { ok = false, error = "No active window found" });
        return Results.Ok(new { ok = true, tree });
    }
    catch (Exception ex)
    {
        return Results.Ok(new { ok = false, error = ex.Message });
    }
});

app.MapPost("/ui/find_element", (FindElementRequest req) =>
{
    try
    {
        if (string.IsNullOrEmpty(req.Name) && string.IsNullOrEmpty(req.AutomationId) && string.IsNullOrEmpty(req.ControlType))
            return Results.Ok(new { ok = false, error = "At least one of name, automationId, or controlType must be specified" });
        var elements = uiRouter.FindElements(req.Name, req.AutomationId, req.ControlType);
        return Results.Ok(new { ok = true, count = elements.Count, elements });
    }
    catch (Exception ex)
    {
        return Results.Ok(new { ok = false, error = ex.Message });
    }
});

app.MapPost("/ui/click_element", (ClickElementRequest req) =>
{
    try
    {
        if (string.IsNullOrEmpty(req.Name) && string.IsNullOrEmpty(req.AutomationId))
            return Results.Ok(new { ok = false, error = "At least one of name or automationId must be specified" });
        var (success, message) = uiRouter.ClickElement(req.Name, req.AutomationId, req.Index);
        return Results.Ok(new { ok = success, message });
    }
    catch (Exception ex)
    {
        return Results.Ok(new { ok = false, error = ex.Message });
    }
});

app.MapPost("/ui/set_text", (SetTextRequest req) =>
{
    try
    {
        if (string.IsNullOrEmpty(req.Name) && string.IsNullOrEmpty(req.AutomationId))
            return Results.Ok(new { ok = false, error = "At least one of name or automationId must be specified" });
        if (req.Text == null)
            return Results.Ok(new { ok = false, error = "text field is required" });
        var (success, message) = uiRouter.SetText(req.Name, req.AutomationId, req.Text, req.Index);
        return Results.Ok(new { ok = success, message });
    }
    catch (Exception ex)
    {
        return Results.Ok(new { ok = false, error = ex.Message });
    }
});

app.MapPost("/ui/invoke", (InvokeRequest req) =>
{
    try
    {
        if (string.IsNullOrEmpty(req.Name) && string.IsNullOrEmpty(req.AutomationId))
            return Results.Ok(new { ok = false, error = "At least one of name or automationId must be specified" });
        var (success, message) = uiRouter.InvokeElement(req.Name, req.AutomationId, req.Index);
        return Results.Ok(new { ok = success, message });
    }
    catch (Exception ex)
    {
        return Results.Ok(new { ok = false, error = ex.Message });
    }
});
```

**Step 2: Verify it compiles**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Smoke test — native app still works**

Run the sidecar, open Calculator, call `/ui/inspect_active_window`. Should return the same UI tree as before.

```bash
cd dotnet-sidecar/LocalWindowsSidecar && dotnet run &
# In another terminal:
curl -s -X POST http://127.0.0.1:47901/window/list | python -m json.tool
curl -s -X POST http://127.0.0.1:47901/ui/inspect_active_window | python -m json.tool
```
Expected: Same element tree structure as before (regression check).

**Step 4: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/Program.cs
git commit -m "feat: wire UIBackendRouter into /ui/* endpoints"
```

---

### Task 9: Add /debug/backend_info diagnostic endpoint

**Files:**
- Modify: `dotnet-sidecar/LocalWindowsSidecar/Program.cs`

Add an endpoint that reports which backend is active for the current window, useful for debugging.

**Step 1: Add the endpoint**

```csharp
app.MapPost("/debug/backend_info", () =>
{
    try
    {
        var backend = uiRouter.GetBackendForActiveWindow();
        var backendType = backend.GetType().Name;
        return Results.Ok(new { ok = true, backend = backendType });
    }
    catch (Exception ex)
    {
        return Results.Ok(new { ok = false, error = ex.Message });
    }
});
```

**Step 2: Verify it compiles and responds**

Run: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet build`
Expected: Build succeeded

**Step 3: Commit**

```bash
git add dotnet-sidecar/LocalWindowsSidecar/Program.cs
git commit -m "feat: add /debug/backend_info diagnostic endpoint"
```

---

### Task 10: End-to-end Electron test

**Files:** None (manual test)

**Step 1: Find an Electron app to test**

Any Electron app installed on the system will work. Common ones: VS Code, Discord, Slack, Spotify (desktop), etc. If none installed, use a minimal Electron test app.

Run: `powershell "Get-Process | Where-Object { Test-Path (Join-Path (Split-Path $_.Path -Parent) 'resources/electron.asar') -ErrorAction SilentlyContinue } | Select-Object Id, ProcessName, Path | Format-Table"`

**Step 2: Start the sidecar and test**

```bash
cd dotnet-sidecar/LocalWindowsSidecar && dotnet run
```

In another terminal, focus the Electron app, then:
```bash
curl -s -X POST http://127.0.0.1:47901/debug/backend_info | python -m json.tool
# Expected: { "ok": true, "backend": "CdpUIBackend" }

curl -s -X POST http://127.0.0.1:47901/ui/inspect_active_window | python -m json.tool
# Expected: JSON tree with HTML elements (tag names, aria-labels, ids)
```

**Step 3: Test interaction**

```bash
# Find a clickable element
curl -s -X POST http://127.0.0.1:47901/ui/find_element -H "Content-Type: application/json" -d '{"controlType":"button"}' | python -m json.tool

# Click it
curl -s -X POST http://127.0.0.1:47901/ui/click_element -H "Content-Type: application/json" -d '{"name":"<button name from above>","index":0}' | python -m json.tool
```

**Step 4: Verify native apps still work (regression)**

Focus Calculator or Notepad, call the same endpoints. Should use WindowsUIBackend.

```bash
curl -s -X POST http://127.0.0.1:47901/debug/backend_info | python -m json.tool
# Expected: { "ok": true, "backend": "WindowsUIBackend" }
```

**Step 5: Commit any fixes needed, then final commit**

```bash
git add -A
git commit -m "test: verify Electron CDP and native UI Automation coexistence"
```
