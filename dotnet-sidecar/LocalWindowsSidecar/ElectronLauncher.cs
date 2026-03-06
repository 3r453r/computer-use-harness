using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json.Nodes;

namespace LocalWindowsSidecar;

/// <summary>
/// Manages connecting to Chromium-based apps via CDP.
/// For standalone Electron apps: kill and relaunch with --remote-debugging-port.
/// For Chrome/Edge PWAs: probe existing debug ports, or relaunch the browser.
/// </summary>
public static class ElectronLauncher
{
    private static int _nextPort = 9222;
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(2) };

    /// <summary>
    /// Known Chromium browser executables that may host PWAs.
    /// These should NOT be killed (would close all browser tabs).
    /// </summary>
    private static readonly string[] BrowserExes = { "chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe" };

    /// <summary>
    /// Connect to a Chromium-based app's CDP.
    /// Strategy depends on whether it's a standalone Electron app or a browser PWA.
    /// Returns (websocketDebuggerUrl, pid) or throws on failure.
    /// </summary>
    public static async Task<(string WsUrl, int Pid)> ConnectOrRelaunchAsync(int originalPid, int timeoutMs = 8000)
    {
        var proc = Process.GetProcessById(originalPid);
        var exePath = proc.MainModule?.FileName
            ?? throw new Exception($"Cannot get exe path for PID {originalPid}");
        var exeName = Path.GetFileName(exePath);

        // Check if this is a browser hosting a PWA
        var isBrowser = BrowserExes.Any(b => exeName.Equals(b, StringComparison.OrdinalIgnoreCase));

        if (isBrowser)
        {
            // For browsers: probe common debug ports (don't kill)
            var wsUrl = await ProbeExistingCdpAsync();
            if (wsUrl != null)
                return (wsUrl, originalPid);

            // No existing debug port found — relaunch browser with CDP enabled
            // This will close all browser windows but is the only option
            Console.Error.WriteLine($"[ElectronLauncher] No existing CDP port found for {exeName}. Relaunching with --remote-debugging-port.");
        }

        return await RelaunchWithCdpAsync(proc, exePath, timeoutMs);
    }

    /// <summary>
    /// Probe common CDP ports (9222-9229) for an already-running debuggable browser.
    /// Returns the first page websocket URL found, or null.
    /// </summary>
    private static async Task<string?> ProbeExistingCdpAsync()
    {
        for (int port = 9222; port <= 9229; port++)
        {
            try
            {
                var json = await Http.GetStringAsync($"http://127.0.0.1:{port}/json");
                var targets = JsonNode.Parse(json)?.AsArray();
                if (targets == null) continue;
                foreach (var target in targets)
                {
                    var type = target?["type"]?.GetValue<string>();
                    var wsUrl = target?["webSocketDebuggerUrl"]?.GetValue<string>();
                    if (type == "page" && !string.IsNullOrEmpty(wsUrl))
                        return wsUrl;
                }
            }
            catch
            {
                // Port not open
            }
        }
        return null;
    }

    private static async Task<(string WsUrl, int Pid)> RelaunchWithCdpAsync(Process proc, string exePath, int timeoutMs)
    {
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
    /// Poll http://127.0.0.1:{port}/json until a page target appears.
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
