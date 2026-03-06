using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace LocalWindowsSidecar;

/// <summary>
/// Low-level Chrome DevTools Protocol client over WebSocket.
/// Sends JSON-RPC commands and waits for responses.
/// </summary>
public class CdpClient : IDisposable
{
    private readonly ClientWebSocket _ws = new();
    private readonly ConcurrentDictionary<int, TaskCompletionSource<JsonNode?>> _pending = new();
    private int _nextId;
    private CancellationTokenSource _cts = new();
    private Task? _receiveLoop;

    public bool IsConnected => _ws.State == WebSocketState.Open;

    /// <summary>
    /// Connect to a CDP websocket endpoint (e.g. ws://127.0.0.1:9222/devtools/page/xxx).
    /// </summary>
    public async Task ConnectAsync(string wsUrl, CancellationToken ct = default)
    {
        await _ws.ConnectAsync(new Uri(wsUrl), ct);
        _receiveLoop = Task.Run(() => ReceiveLoopAsync(_cts.Token));
    }

    /// <summary>
    /// Send a CDP command and wait for the result.
    /// </summary>
    public async Task<JsonNode?> SendAsync(string method, JsonNode? parameters = null, int timeoutMs = 5000)
    {
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
        while (!ct.IsCancellationRequested && _ws.State == WebSocketState.Open)
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

    public void Dispose()
    {
        _cts.Cancel();
        try { _ws.Dispose(); } catch { }
        _cts.Dispose();
    }
}
