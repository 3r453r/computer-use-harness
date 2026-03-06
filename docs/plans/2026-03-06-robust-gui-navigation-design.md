# Robust GUI Navigation Design

## Problem

The agent loop has three recurring failure modes when navigating GUI apps:

1. **Wrong click type** — uses double-click when single-click is needed (or vice versa), wastes steps
2. **Stuck loops** — repeats the same action 5+ times (same coordinates, same scroll direction) without trying alternatives
3. **No action feedback** — takes screenshots immediately after clicking, before the UI updates; can't tell if its action worked

These cost $0.38-$0.69 per failed run and burn through max_steps without completing the task.

## Scope

General robustness improvements enforced at the harness level. No Electron/CDP-specific work. No new external dependencies.

## Design

### 1. Stuck Detection

**Location:** `AgentHarness.run_task()` loop

Track recent actions in a sliding window. When 3+ consecutive actions are "similar", inject a synthetic message into history forcing the model to change approach.

**Similarity rules:**
- Same tool name AND:
  - Mouse tools: coordinates within 50px euclidean distance
  - Scroll: same direction (both positive or both negative delta)
  - Keyboard: same keys/text
  - Other tools: same arguments

**Injected message:**
```
You have repeated a similar action 3 times without progress. Try a fundamentally different approach: different coordinates, different click type, keyboard navigation, or a completely different tool.
```

**Reset condition:** model calls a different tool, or screenshot diff detects UI change.

### 2. Auto-delay After GUI Actions

**Location:** `AgentHarness._execute()`, after tool returns

After any mouse or keyboard tool execution, the harness waits before continuing the loop.

- Default: 1.5 seconds
- Configurable: `GUI_ACTION_DELAY_S` env var in Settings
- Applies to tools: `mouse.*`, `keyboard.*`
- Does NOT apply to: `fs.*`, `terminal.exec`, `process.*`, `sidecar.call`, `screen.capture`, `browser.*`

Invisible to the model — just ensures UI has time to respond before the next screenshot.

### 3. Screenshot Diff Feedback

**Location:** `AgentHarness.run_task()`, in screenshot extraction logic

Compare each new screenshot to the previous one and report whether the UI changed.

**Implementation:**
- Store previous screenshot bytes in harness (not in history)
- On new screenshot: load both as PIL images, compute mean absolute pixel difference normalized to 0-1
- Threshold: diff < 0.01 → `ui_changed: false`, else `ui_changed: true`
- Add to screenshot result output: `{"ui_changed": true/false, "change_magnitude": 0.037}`

**Dependencies:** PIL (already used by ScreenCaptureTool). No new deps.

### 4. Click Escalation Prompt

**Location:** System prompt in `openai_client.py`

Add explicit escalation strategy:

1. Single click first
2. If `ui_changed` is false → double click same element
3. If still no change → click 20-30px offset
4. If still no change → keyboard navigation (Tab, Enter)
5. If still no change → completely different approach (sidecar, terminal, different UI path)

Rule: never repeat the exact same action more than twice.

## Files to Modify

| File | Change |
|------|--------|
| `config/settings.py` | Add `gui_action_delay_s: float = 1.5` |
| `agent/harness.py` | Stuck detector, auto-delay, screenshot diff logic |
| `agent/openai_client.py` | Click escalation in system prompt |
| `tools/local_tools.py` | Return raw image bytes from ScreenCaptureTool for diff |

## Success Criteria

- Stuck loops broken: model never repeats the same action 4+ times
- Model receives `ui_changed` feedback on every screenshot
- GUI actions have automatic delay before next step
- Prompt guides click escalation with concrete steps
