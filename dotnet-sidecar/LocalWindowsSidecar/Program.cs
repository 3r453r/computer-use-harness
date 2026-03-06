using LocalWindowsSidecar;
using LocalWindowsSidecar.Models;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddEndpointsApiExplorer();
builder.Services.Configure<Microsoft.AspNetCore.Http.Json.JsonOptions>(o =>
    o.SerializerOptions.PropertyNameCaseInsensitive = true);

var app = builder.Build();
app.MapGet("/health", () => Results.Ok(new { ok = true }));

app.MapPost("/window/list", () =>
{
    var windows = WindowInterop.ListWindows();
    return Results.Ok(new { windows });
});

app.MapPost("/window/get_active", () =>
{
    var active = WindowInterop.GetActiveWindow();
    return Results.Ok(active);
});

app.MapPost("/window/focus", (WindowFocusRequest req) =>
{
    var result = WindowInterop.FocusWindow(req.TitlePattern ?? req.Title ?? "");
    return Results.Ok(new { ok = result });
});

app.MapPost("/ui/inspect_active_window", () =>
{
    try
    {
        var root = UIAutomationHelper.GetActiveWindowElement();
        if (root == null)
            return Results.Ok(new { ok = false, error = "No active window found" });

        var tree = UIAutomationHelper.BuildTree(root, maxDepth: 2);
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

        var elements = UIAutomationHelper.FindElements(req.Name, req.AutomationId, req.ControlType);
        var results = elements.Select(UIAutomationHelper.ToElementInfo).ToList();
        return Results.Ok(new { ok = true, count = results.Count, elements = results });
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

        var elements = UIAutomationHelper.FindElements(req.Name, req.AutomationId, controlType: null);
        if (elements.Count == 0)
            return Results.Ok(new { ok = false, error = "No matching elements found" });

        if (req.Index < 0 || req.Index >= elements.Count)
            return Results.Ok(new { ok = false, error = $"Index {req.Index} out of range. Found {elements.Count} element(s)." });

        var target = elements[req.Index];
        var (success, message) = UIAutomationHelper.ClickElement(target);
        var info = UIAutomationHelper.ToElementInfo(target);
        return Results.Ok(new { ok = success, message, element = info });
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

        var elements = UIAutomationHelper.FindElements(req.Name, req.AutomationId, controlType: null);
        if (elements.Count == 0)
            return Results.Ok(new { ok = false, error = "No matching elements found" });

        if (req.Index < 0 || req.Index >= elements.Count)
            return Results.Ok(new { ok = false, error = $"Index {req.Index} out of range. Found {elements.Count} element(s)." });

        var target = elements[req.Index];
        var (success, message) = UIAutomationHelper.SetText(target, req.Text);
        var info = UIAutomationHelper.ToElementInfo(target);
        return Results.Ok(new { ok = success, message, element = info });
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

        var elements = UIAutomationHelper.FindElements(req.Name, req.AutomationId, controlType: null);
        if (elements.Count == 0)
            return Results.Ok(new { ok = false, error = "No matching elements found" });

        if (req.Index < 0 || req.Index >= elements.Count)
            return Results.Ok(new { ok = false, error = $"Index {req.Index} out of range. Found {elements.Count} element(s)." });

        var target = elements[req.Index];
        var (success, message) = UIAutomationHelper.InvokeElement(target);
        var info = UIAutomationHelper.ToElementInfo(target);
        return Results.Ok(new { ok = success, message, element = info });
    }
    catch (Exception ex)
    {
        return Results.Ok(new { ok = false, error = ex.Message });
    }
});

app.Run("http://127.0.0.1:47901");

internal static class WindowInterop
{
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

    [DllImport("user32.dll")]
    private static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);

    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    private const int SW_RESTORE = 9;
    private const byte VK_MENU = 0x12;
    private const uint KEYEVENTF_EXTENDEDKEY = 0x0001;
    private const uint KEYEVENTF_KEYUP = 0x0002;

    public static List<WindowInfo> ListWindows()
    {
        var windows = new List<WindowInfo>();
        EnumWindows((hWnd, _) =>
        {
            if (!IsWindowVisible(hWnd)) return true;
            var title = GetTitle(hWnd);
            if (string.IsNullOrWhiteSpace(title)) return true;
            GetWindowThreadProcessId(hWnd, out var pid);
            windows.Add(new WindowInfo(hWnd.ToInt64(), title, (int)pid));
            return true;
        }, IntPtr.Zero);
        return windows;
    }

    public static WindowInfo? GetActiveWindow()
    {
        var hWnd = GetForegroundWindow();
        if (hWnd == IntPtr.Zero) return null;
        GetWindowThreadProcessId(hWnd, out var pid);
        return new WindowInfo(hWnd.ToInt64(), GetTitle(hWnd), (int)pid);
    }

    public static bool FocusWindow(string pattern)
    {
        var regex = new Regex(pattern, RegexOptions.IgnoreCase);
        var found = ListWindows().FirstOrDefault(w => regex.IsMatch(w.Title));
        if (found == null) return false;
        var hWnd = new IntPtr(found.Handle);

        // Restore if minimized
        ShowWindow(hWnd, SW_RESTORE);

        // Attach to the target window's thread to bypass SetForegroundWindow restrictions
        GetWindowThreadProcessId(hWnd, out var targetThreadId);
        var currentThreadId = GetCurrentThreadId();
        var attached = false;
        if (targetThreadId != currentThreadId)
        {
            attached = AttachThreadInput(currentThreadId, targetThreadId, true);
        }

        // Simulate Alt key press — standard workaround for SetForegroundWindow restrictions
        keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY, UIntPtr.Zero);
        keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, UIntPtr.Zero);

        var result = SetForegroundWindow(hWnd);

        if (attached)
        {
            AttachThreadInput(currentThreadId, targetThreadId, false);
        }

        return result;
    }

    private static string GetTitle(IntPtr hWnd)
    {
        var buff = new System.Text.StringBuilder(512);
        _ = GetWindowText(hWnd, buff, buff.Capacity);
        return buff.ToString();
    }
}
