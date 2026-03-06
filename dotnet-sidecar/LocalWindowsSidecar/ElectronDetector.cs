using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

namespace LocalWindowsSidecar;

/// <summary>
/// Detects whether a given process is an Electron/CEF application
/// by inspecting the process directory for Chromium markers.
/// </summary>
public static class ElectronDetector
{
    private static readonly string[] ChromiumMarkers = new[]
    {
        "libcef.dll",
        "chrome_elf.dll",
        "electron.exe",
        "vk_swiftshader.dll",
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

            var exeName = Path.GetFileName(exePath);
            if (exeName.Equals("electron.exe", StringComparison.OrdinalIgnoreCase))
                return true;

            foreach (var marker in ChromiumMarkers)
            {
                if (File.Exists(Path.Combine(dir, marker)))
                    return true;
            }

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
    /// Gets the executable path for a process by PID.
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
