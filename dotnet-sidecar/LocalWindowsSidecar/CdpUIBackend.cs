using System.Text.Json;
using System.Text.Json.Nodes;
using LocalWindowsSidecar.Models;

namespace LocalWindowsSidecar;

public class CdpUIBackend : IUIBackend
{
    private readonly CdpClient _cdp;

    public CdpUIBackend(CdpClient cdp)
    {
        _cdp = cdp;
    }

    public UIElementInfo? InspectActiveWindow(int maxDepth)
    {
        var js = @"
        (function() {
            function walk(el, depth, maxD) {
                var rect = el.getBoundingClientRect();
                var node = {
                    name: el.getAttribute('aria-label') || el.getAttribute('title') || (el.innerText || '').substring(0, 80),
                    automationId: el.id || '',
                    controlType: el.getAttribute('role') || el.tagName.toLowerCase(),
                    boundingRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                    children: []
                };
                if (depth < maxD) {
                    for (var i = 0; i < el.children.length && i < 50; i++) {
                        node.children.push(walk(el.children[i], depth + 1, maxD));
                    }
                }
                if (node.children.length === 0) delete node.children;
                return node;
            }
            return JSON.stringify(walk(document.body, 0, " + maxDepth + @"));
        })()";

        var result = EvalSync(js);
        if (result == null) return null;
        try
        {
            return JsonSerializer.Deserialize<UIElementInfo>(result,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }
        catch { return null; }
    }

    public List<UIElementInfo> FindElements(string? name, string? automationId, string? controlType)
    {
        var js = @"
        (function() {
            var results = [];
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var elName = el.getAttribute('aria-label') || el.getAttribute('title') || (el.innerText || '').substring(0, 80);
                var elId = el.id || '';
                var elRole = el.getAttribute('role') || el.tagName.toLowerCase();
                var nameFilter = '" + EscapeJs(name) + @"';
                var idFilter = '" + EscapeJs(automationId) + @"';
                var typeFilter = '" + EscapeJs(controlType) + @"';
                var nameMatch = !nameFilter || elName.indexOf(nameFilter) !== -1;
                var idMatch = !idFilter || elId === idFilter;
                var typeMatch = !typeFilter || elRole === typeFilter;
                if (nameMatch && idMatch && typeMatch) {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            name: elName.substring(0, 80),
                            automationId: elId,
                            controlType: elRole,
                            boundingRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                        });
                    }
                }
                if (results.length >= 50) break;
            }
            return JSON.stringify(results);
        })()";

        var result = EvalSync(js);
        if (result == null) return new List<UIElementInfo>();
        try
        {
            return JsonSerializer.Deserialize<List<UIElementInfo>>(result,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true }) ?? new List<UIElementInfo>();
        }
        catch { return new List<UIElementInfo>(); }
    }

    public (bool Success, string Message) ClickElement(string? name, string? automationId, int index)
    {
        var js = @"
        (function() {
            var all = document.querySelectorAll('*');
            var matches = [];
            for (var i = 0; i < all.length; i++) {
                var e = all[i];
                var eName = e.getAttribute('aria-label') || e.getAttribute('title') || (e.innerText || '').substring(0, 80);
                var eId = e.id || '';
                var nameFilter = '" + EscapeJs(name) + @"';
                var idFilter = '" + EscapeJs(automationId) + @"';
                var nameMatch = !nameFilter || eName.indexOf(nameFilter) !== -1;
                var idMatch = !idFilter || eId === idFilter;
                if (nameMatch && idMatch) {
                    var rect = e.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) matches.push(e);
                }
                if (matches.length > " + index + @") break;
            }
            if (matches.length <= " + index + @") return JSON.stringify({ok: false, msg: 'Element not found at index'});
            var target = matches[" + index + @"];
            if (target.scrollIntoViewIfNeeded) target.scrollIntoViewIfNeeded();
            else target.scrollIntoView({block:'center'});
            target.click();
            return JSON.stringify({ok: true, msg: 'Clicked via JS .click()'});
        })()";

        return ParseActionResult(EvalSync(js));
    }

    public (bool Success, string Message) SetText(string? name, string? automationId, string text, int index)
    {
        var js = @"
        (function() {
            var all = document.querySelectorAll('*');
            var matches = [];
            for (var i = 0; i < all.length; i++) {
                var e = all[i];
                var eName = e.getAttribute('aria-label') || e.getAttribute('title') || (e.innerText || '').substring(0, 80);
                var eId = e.id || '';
                var nameFilter = '" + EscapeJs(name) + @"';
                var idFilter = '" + EscapeJs(automationId) + @"';
                var nameMatch = !nameFilter || eName.indexOf(nameFilter) !== -1;
                var idMatch = !idFilter || eId === idFilter;
                if (nameMatch && idMatch) {
                    var rect = e.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) matches.push(e);
                }
                if (matches.length > " + index + @") break;
            }
            if (matches.length <= " + index + @") return JSON.stringify({ok: false, msg: 'Element not found at index'});
            var target = matches[" + index + @"];
            target.focus();
            var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
            if (!nativeSet) nativeSet = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
            if (nativeSet && nativeSet.set) {
                nativeSet.set.call(target, '" + EscapeJs(text) + @"');
            } else {
                target.value = '" + EscapeJs(text) + @"';
            }
            target.dispatchEvent(new Event('input', { bubbles: true }));
            target.dispatchEvent(new Event('change', { bubbles: true }));
            return JSON.stringify({ok: true, msg: 'Text set via JS'});
        })()";

        return ParseActionResult(EvalSync(js));
    }

    public (bool Success, string Message) InvokeElement(string? name, string? automationId, int index)
    {
        return ClickElement(name, automationId, index);
    }

    private string? EvalSync(string expression)
    {
        // Try eval, and if websocket is dead, reconnect and retry once
        for (int attempt = 0; attempt < 2; attempt++)
        {
            try
            {
                if (!_cdp.IsConnected)
                {
                    if (attempt == 0)
                    {
                        Console.Error.WriteLine("[CdpUIBackend] WebSocket disconnected, attempting reconnect...");
                        var reconnected = _cdp.ReconnectAsync().GetAwaiter().GetResult();
                        if (!reconnected)
                        {
                            Console.Error.WriteLine("[CdpUIBackend] Reconnection failed");
                            return null;
                        }
                        Console.Error.WriteLine("[CdpUIBackend] Reconnected successfully");
                        continue;
                    }
                    Console.Error.WriteLine("[CdpUIBackend] WebSocket still not connected after reconnect");
                    return null;
                }

                var parameters = new JsonObject
                {
                    ["expression"] = expression,
                    ["returnByValue"] = true
                };
                var result = _cdp.SendAsync("Runtime.evaluate", parameters, timeoutMs: 5000)
                    .GetAwaiter().GetResult();

                var value = result?["result"]?["value"]?.GetValue<string>();
                return value;
            }
            catch (Exception ex) when (attempt == 0)
            {
                Console.Error.WriteLine($"[CdpUIBackend] EvalSync failed ({ex.Message}), attempting reconnect...");
                try
                {
                    var reconnected = _cdp.ReconnectAsync().GetAwaiter().GetResult();
                    if (!reconnected) return null;
                }
                catch { return null; }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[CdpUIBackend] EvalSync error: {ex.Message}");
                return null;
            }
        }
        return null;
    }

    private static (bool Success, string Message) ParseActionResult(string? json)
    {
        if (json == null) return (false, "CDP eval returned null");
        try
        {
            var obj = JsonNode.Parse(json);
            return (obj?["ok"]?.GetValue<bool>() ?? false, obj?["msg"]?.GetValue<string>() ?? "unknown");
        }
        catch { return (false, "Failed to parse action result"); }
    }

    private static string EscapeJs(string? s)
    {
        if (string.IsNullOrEmpty(s)) return "";
        return s.Replace("\\", "\\\\").Replace("'", "\\'").Replace("\n", "\\n").Replace("\r", "\\r");
    }

    /// <summary>
    /// Test the CDP connection with a simple eval. Returns the result string or null.
    /// </summary>
    public string? TestEval()
    {
        return EvalSync("JSON.stringify({ok:true, elements: document.querySelectorAll('*').length, connected: true})");
    }

    public void Dispose()
    {
        _cdp.Dispose();
    }
}
