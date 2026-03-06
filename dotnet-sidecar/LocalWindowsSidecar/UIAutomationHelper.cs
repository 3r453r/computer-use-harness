using System.Runtime.InteropServices;
using System.Windows.Automation;
using LocalWindowsSidecar.Models;

namespace LocalWindowsSidecar;

internal static class UIAutomationHelper
{
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    private static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);

    private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    private const uint MOUSEEVENTF_LEFTUP = 0x0004;

    /// <summary>
    /// Gets the AutomationElement for the current foreground window.
    /// </summary>
    public static AutomationElement? GetActiveWindowElement()
    {
        var hwnd = GetForegroundWindow();
        if (hwnd == IntPtr.Zero) return null;
        try
        {
            return AutomationElement.FromHandle(hwnd);
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Builds a UI element tree from the given root, limited to maxDepth levels.
    /// </summary>
    public static UIElementInfo BuildTree(AutomationElement element, int maxDepth, int currentDepth = 0)
    {
        var info = ToElementInfo(element);

        if (currentDepth < maxDepth)
        {
            try
            {
                var children = element.FindAll(TreeScope.Children, Condition.TrueCondition);
                if (children.Count > 0)
                {
                    info.Children = new List<UIElementInfo>();
                    foreach (AutomationElement child in children)
                    {
                        try
                        {
                            info.Children.Add(BuildTree(child, maxDepth, currentDepth + 1));
                        }
                        catch
                        {
                            // Skip elements that throw during inspection
                        }
                    }
                }
            }
            catch
            {
                // FindAll can fail for some windows
            }
        }

        return info;
    }

    /// <summary>
    /// Finds elements matching the given criteria in the active window.
    /// </summary>
    public static List<AutomationElement> FindElements(string? name, string? automationId, string? controlType)
    {
        var root = GetActiveWindowElement();
        if (root == null) return new List<AutomationElement>();

        var conditions = new List<Condition>();

        if (!string.IsNullOrEmpty(name))
            conditions.Add(new PropertyCondition(AutomationElement.NameProperty, name));

        if (!string.IsNullOrEmpty(automationId))
            conditions.Add(new PropertyCondition(AutomationElement.AutomationIdProperty, automationId));

        if (!string.IsNullOrEmpty(controlType))
        {
            var ct = ParseControlType(controlType);
            if (ct != null)
                conditions.Add(new PropertyCondition(AutomationElement.ControlTypeProperty, ct));
        }

        Condition searchCondition;
        if (conditions.Count == 0)
            searchCondition = Condition.TrueCondition;
        else if (conditions.Count == 1)
            searchCondition = conditions[0];
        else
            searchCondition = new AndCondition(conditions.ToArray());

        try
        {
            var found = root.FindAll(TreeScope.Descendants, searchCondition);
            var results = new List<AutomationElement>();
            foreach (AutomationElement el in found)
                results.Add(el);
            return results;
        }
        catch
        {
            return new List<AutomationElement>();
        }
    }

    /// <summary>
    /// Clicks an element by trying InvokePattern first, then falling back to simulating a mouse click
    /// at the center of the element's bounding rectangle.
    /// </summary>
    public static (bool Success, string Message) ClickElement(AutomationElement element)
    {
        // Try InvokePattern first
        try
        {
            if (element.TryGetCurrentPattern(InvokePattern.Pattern, out var pattern))
            {
                ((InvokePattern)pattern).Invoke();
                return (true, "Clicked via InvokePattern");
            }
        }
        catch (Exception ex)
        {
            // Fall through to mouse simulation
        }

        // Try toggle pattern (for checkboxes etc.)
        try
        {
            if (element.TryGetCurrentPattern(TogglePattern.Pattern, out var pattern))
            {
                ((TogglePattern)pattern).Toggle();
                return (true, "Clicked via TogglePattern");
            }
        }
        catch { }

        // Fall back to simulated mouse click
        try
        {
            var rect = element.Current.BoundingRectangle;
            if (rect.IsEmpty || double.IsInfinity(rect.X) || double.IsInfinity(rect.Y))
                return (false, "Element has no valid bounding rectangle for mouse click");

            int x = (int)(rect.X + rect.Width / 2);
            int y = (int)(rect.Y + rect.Height / 2);

            SetCursorPos(x, y);
            Thread.Sleep(50);
            mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
            mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);

            return (true, $"Clicked via mouse simulation at ({x}, {y})");
        }
        catch (Exception ex)
        {
            return (false, $"Failed to click element: {ex.Message}");
        }
    }

    /// <summary>
    /// Sets text on an element using ValuePattern, or falls back to clearing and using SendKeys.
    /// </summary>
    public static (bool Success, string Message) SetText(AutomationElement element, string text)
    {
        // Try ValuePattern
        try
        {
            if (element.TryGetCurrentPattern(ValuePattern.Pattern, out var pattern))
            {
                ((ValuePattern)pattern).SetValue(text);
                return (true, "Text set via ValuePattern");
            }
        }
        catch (Exception ex)
        {
            // Fall through
        }

        // Fall back to focus + SendKeys
        try
        {
            element.SetFocus();
            Thread.Sleep(100);
            // Select all existing text and replace
            System.Windows.Forms.SendKeys.SendWait("^(a)");
            Thread.Sleep(50);
            // SendKeys requires special escaping for certain chars.
            // Build escaped string char-by-char to avoid replacement ordering issues.
            var sb = new System.Text.StringBuilder();
            foreach (char c in text)
            {
                sb.Append(c switch
                {
                    '{' => "{{}",
                    '}' => "{}}",
                    '+' => "{+}",
                    '^' => "{^}",
                    '%' => "{%}",
                    '~' => "{~}",
                    '(' => "{(}",
                    ')' => "{)}",
                    _ => c.ToString()
                });
            }
            System.Windows.Forms.SendKeys.SendWait(sb.ToString());
            return (true, "Text set via SendKeys");
        }
        catch (Exception ex)
        {
            return (false, $"Failed to set text: {ex.Message}");
        }
    }

    /// <summary>
    /// Invokes an element using InvokePattern.
    /// </summary>
    public static (bool Success, string Message) InvokeElement(AutomationElement element)
    {
        try
        {
            if (element.TryGetCurrentPattern(InvokePattern.Pattern, out var pattern))
            {
                ((InvokePattern)pattern).Invoke();
                return (true, "Invoked via InvokePattern");
            }

            // Try ExpandCollapsePattern as alternative
            if (element.TryGetCurrentPattern(ExpandCollapsePattern.Pattern, out var ecPattern))
            {
                var ecp = (ExpandCollapsePattern)ecPattern;
                if (ecp.Current.ExpandCollapseState == ExpandCollapseState.Collapsed)
                    ecp.Expand();
                else
                    ecp.Collapse();
                return (true, "Invoked via ExpandCollapsePattern");
            }

            return (false, "Element does not support InvokePattern or ExpandCollapsePattern");
        }
        catch (Exception ex)
        {
            return (false, $"Failed to invoke element: {ex.Message}");
        }
    }

    /// <summary>
    /// Converts an AutomationElement to a UIElementInfo.
    /// </summary>
    public static UIElementInfo ToElementInfo(AutomationElement element)
    {
        try
        {
            var current = element.Current;
            var rect = current.BoundingRectangle;
            BoundingRectInfo? boundingRect = null;
            if (!rect.IsEmpty && !double.IsInfinity(rect.X))
            {
                boundingRect = new BoundingRectInfo
                {
                    X = rect.X,
                    Y = rect.Y,
                    Width = rect.Width,
                    Height = rect.Height
                };
            }

            return new UIElementInfo
            {
                Name = current.Name,
                AutomationId = current.AutomationId,
                ControlType = current.ControlType.ProgrammaticName.Replace("ControlType.", ""),
                BoundingRect = boundingRect
            };
        }
        catch
        {
            return new UIElementInfo { Name = "(error reading element)" };
        }
    }

    /// <summary>
    /// Parses a control type string to a ControlType object.
    /// </summary>
    private static ControlType? ParseControlType(string name)
    {
        var field = typeof(ControlType).GetField(name,
            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
        return field?.GetValue(null) as ControlType;
    }
}
