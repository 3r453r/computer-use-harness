using System.Collections.Concurrent;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace LocalWindowsSidecar;

/// <summary>
/// Low-level Chrome DevTools Protocol client over WebSocket.
/// Supports reconnection when the websocket dies.
/// </summary>
public class CdpClient : IDisposable
{
    private ClientWebSocket? _ws;
    private readonly ConcurrentDictionary<int, TaskCompletionSource<JsonNode?>> _pending = new();
    private int _nextId;
    private CancellationTokenSource _cts = new();
    private Task? _receiveLoop;
    private string? _lastWsUrl;

    public bool IsConnected => _ws?.State == WebSocketState.Open;

    /// <summary>
    /// The CDP HTTP port this client is connected to (for target rediscovery).
    /// </summary>
    public int? Port { get; private set; }

    /// <summary>
    /// Connect to a CDP websocket endpoint.
    /// </summary>
    public async Task ConnectAsync(string wsUrl, CancellationToken ct = default)
    {
        // Extract port from wsUrl for reconnection
        if (Uri.TryCreate(wsUrl, UriKind.Absolute, out var uri))
            Port = uri.Port;

        await ConnectInternalAsync(wsUrl, ct);
    }

    private async Task ConnectInternalAsync(string wsUrl, CancellationToken ct = default)
    {
        // Clean up old connection
        CleanupConnection();

        _cts = new CancellationTokenSource();
        _ws = new ClientWebSocket();
        _lastWsUrl = wsUrl;
        await _ws.ConnectAsync(new Uri(wsUrl), ct);
        _receiveLoop = Task.Run(() => ReceiveLoopAsync(_cts.Token));
    }

    /// <summary>
    /// Reconnect by rediscovering the page target on the same CDP port.
    /// Returns true if reconnection succeeded.
    /// </summary>
    public async Task<bool> ReconnectAsync(CancellationToken ct = default)
    {
        if (!Port.HasValue) return false;

        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            var json = await http.GetStringAsync($"http://127.0.0.1:{Port.Value}/json", ct);
            var targets = JsonNode.Parse(json)?.AsArray();
            if (targets == null) return false;

            foreach (var target in targets)
            {
                var type = target?["type"]?.GetValue<string>();
                var wsUrl = target?["webSocketDebuggerUrl"]?.GetValue<string>();
                if (type == "page" && !string.IsNullOrEmpty(wsUrl))
                {
                    await ConnectInternalAsync(wsUrl, ct);
                    Console.Error.WriteLine($"[CdpClient] Reconnected to {wsUrl}");
                    return true;
                }
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[CdpClient] Reconnection failed: {ex.Message}");
        }
        return false;
    }

    /// <summary>
    /// Send a CDP command and wait for the result.
    /// </summary>
    public async Task<JsonNode?> SendAsync(string method, JsonNode? parameters = null, int timeoutMs = 5000)
    {
        if (_ws == null || _ws.State != WebSocketState.Open)
            throw new InvalidOperationException("WebSocket not connected");

        var id = Interlocked.Increment(ref _nextId);
        var tcs = new TaskCompletionSource<JsonNode?>();
        _pending[id] = tcs;

        var msg = new JsonObject
        {
            ["id"] = id,
            ["method"] = method
        };
        if (parameters != null)
            msg["params"] = parameters;

        var bytes = Encoding.UTF8.GetBytes(msg.ToJsonString());
        await _ws.SendAsync(bytes, WebSocketMessageType.Text, true, _cts.Token);

        using var timeoutCts = new CancellationTokenSource(timeoutMs);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token, timeoutCts.Token);
        try
        {
            linked.Token.Register(() => tcs.TrySetCanceled());
            return await tcs.Task;
        }
        catch (TaskCanceledException)
        {
            _pending.TryRemove(id, out _);
            throw new TimeoutException($"CDP command '{method}' timed out after {timeoutMs}ms");
        }
    }

    private async Task ReceiveLoopAsync(CancellationToken ct)
    {
        var buffer = new byte[64 * 1024];
        var sb = new StringBuilder();
        while (!ct.IsCancellationRequested && _ws?.State == WebSocketState.Open)
        {
            try
            {
                var result = await _ws.ReceiveAsync(buffer, ct);
                if (result.MessageType == WebSocketMessageType.Close) break;

                sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                if (!result.EndOfMessage) continue;

                var json = sb.ToString();
                sb.Clear();

                var node = JsonNode.Parse(json);
                if (node == null) continue;

                var id = node["id"]?.GetValue<int>();
                if (id.HasValue && _pending.TryRemove(id.Value, out var tcs))
                {
                    if (node["error"] != null)
                        tcs.TrySetException(new Exception($"CDP error: {node["error"]}"));
                    else
                        tcs.TrySetResult(node["result"]);
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch
            {
                // Continue on transient errors
            }
        }
    }

    private void CleanupConnection()
    {
        try { _cts.Cancel(); } catch { }
        try { _ws?.Dispose(); } catch { }
        try { _cts.Dispose(); } catch { }
        // Cancel all pending requests
        foreach (var kv in _pending)
        {
            kv.Value.TrySetCanceled();
            _pending.TryRemove(kv.Key, out _);
        }
    }

    public void Dispose()
    {
        CleanupConnection();
    }
}
