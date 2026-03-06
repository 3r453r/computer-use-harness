# Demo tasks

## Deterministic terminal-first demo
`restart my Next.js dev server in the current repo`

Expected plan: process.find -> process.kill (approval) -> terminal.exec with working directory.

## Sidecar/visual fallback demo
`focus Notepad and set the first textbox value to Hello from harness`

Expected plan: sidecar.call window.list/window.focus/ui.set_text. If unavailable, fallback to screen.capture + mouse/keyboard actions.
