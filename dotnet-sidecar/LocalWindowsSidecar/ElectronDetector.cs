using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

namespace LocalWindowsSidecar;

/// <summary>
/// Detects whether a given process is an Electron/CEF/Chromium application
/// that supports Chrome DevTools Protocol.
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

    /// <summary>
    /// Executable names that are known Chromium-based browsers supporting CDP.
    /// These host PWAs and web apps that are opaque to Windows UI Automation.
    /// </summary>
    private static readonly string[] ChromiumBrowserExes = new[]
    {
        "chrome.exe",
        "msedge.exe",
        "brave.exe",
        "vivaldi.exe",
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
    /// Returns true if the given PID is an Electron/CEF/Chromium app that supports CDP.
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

            // Direct Electron executable
            if (exeName.Equals("electron.exe", StringComparison.OrdinalIgnoreCase))
                return true;

            // Known Chromium-based browsers (host PWAs like StemForge)
            foreach (var browserExe in ChromiumBrowserExes)
            {
                if (exeName.Equals(browserExe, StringComparison.OrdinalIgnoreCase))
                    return true;
            }

            // Check marker files in exe directory
            foreach (var marker in ChromiumMarkers)
            {
                if (File.Exists(Path.Combine(dir, marker)))
                    return true;
            }

            // Check version subdirectories (Chrome stores chrome_elf.dll there)
            try
            {
                foreach (var subDir in Directory.GetDirectories(dir))
                {
                    foreach (var marker in ChromiumMarkers)
                    {
                        if (File.Exists(Path.Combine(subDir, marker)))
                            return true;
                    }
                }
            }
            catch { }

            // Electron-specific: resources/electron.asar
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
