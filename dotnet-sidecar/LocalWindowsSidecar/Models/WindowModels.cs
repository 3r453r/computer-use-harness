namespace LocalWindowsSidecar.Models;

public record WindowInfo(long Handle, string Title, int ProcessId);

public record WindowFocusRequest(string? Title, string? TitlePattern);

// UI Automation request/response models

public class FindElementRequest
{
    public string? Name { get; set; }
    public string? AutomationId { get; set; }
    public string? ControlType { get; set; }
}

public class ClickElementRequest
{
    public string? Name { get; set; }
    public string? AutomationId { get; set; }
    public int Index { get; set; } = 0;
}

public class SetTextRequest
{
    public string? Name { get; set; }
    public string? AutomationId { get; set; }
    public string? Text { get; set; }
    public int Index { get; set; } = 0;
}

public class InvokeRequest
{
    public string? Name { get; set; }
    public string? AutomationId { get; set; }
    public int Index { get; set; } = 0;
}

public class UIElementInfo
{
    public string? Name { get; set; }
    public string? AutomationId { get; set; }
    public string? ControlType { get; set; }
    public BoundingRectInfo? BoundingRect { get; set; }
    public List<UIElementInfo>? Children { get; set; }
}

public class BoundingRectInfo
{
    public double X { get; set; }
    public double Y { get; set; }
    public double Width { get; set; }
    public double Height { get; set; }
}
