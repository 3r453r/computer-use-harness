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
