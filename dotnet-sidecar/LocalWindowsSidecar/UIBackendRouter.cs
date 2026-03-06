using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using LocalWindowsSidecar.Models;

namespace LocalWindowsSidecar;

/// <summary>
/// Routes /ui/* calls to the appropriate backend (Windows UI Automation or CDP)
/// based on whether the active window is an Electron app.
/// Caches backends per PID.
/// </summary>
public class UIBackendRouter : IUIBackend
{
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    private readonly ConcurrentDictionary<int, IUIBackend> _cache = new();
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
