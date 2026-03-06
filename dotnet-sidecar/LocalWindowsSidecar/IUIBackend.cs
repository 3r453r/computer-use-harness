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
