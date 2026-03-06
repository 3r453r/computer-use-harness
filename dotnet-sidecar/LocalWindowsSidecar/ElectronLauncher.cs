using System.Diagnostics;
using System.Net.Http;
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
