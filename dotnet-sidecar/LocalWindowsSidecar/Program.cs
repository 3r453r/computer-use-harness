using LocalWindowsSidecar.Models;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddEndpointsApiExplorer();

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
    var active = WindowInterop.GetActiveWindow();
    return Results.Ok(new
    {
        note = "MVP inspection returns active window metadata. Extend with UIAutomation tree traversal.",
        active
    });
});

app.MapPost("/ui/find_element", (Dictionary<string, object> req) =>
    Results.Ok(new { ok = false, note = "Not yet implemented in MVP", request = req }));
app.MapPost("/ui/invoke", (Dictionary<string, object> req) =>
    Results.Ok(new { ok = false, note = "Not yet implemented in MVP", request = req }));
app.MapPost("/ui/set_text", (Dictionary<string, object> req) =>
    Results.Ok(new { ok = false, note = "Not yet implemented in MVP", request = req }));
app.MapPost("/ui/click_element", (Dictionary<string, object> req) =>
    Results.Ok(new { ok = false, note = "Not yet implemented in MVP", request = req }));

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
        return SetForegroundWindow(new IntPtr(found.Handle));
    }

    private static string GetTitle(IntPtr hWnd)
    {
        var buff = new System.Text.StringBuilder(512);
        _ = GetWindowText(hWnd, buff, buff.Capacity);
        return buff.ToString();
    }
}
