namespace LocalWindowsSidecar.Models;

public record WindowInfo(long Handle, string Title, int ProcessId);

public record WindowFocusRequest(string? Title, string? TitlePattern);
