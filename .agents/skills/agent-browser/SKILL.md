---
name: agent-browser
description: Automate rendered browser or Electron interactions. Use when the task requires navigation, clicks, forms, authenticated UI state, screenshots, rendered-page extraction, or browser-based app testing. Do not use for a plain HTTP/document read that needs no browser state, or automatically for every bug, QA, or code-review task.
allowed-tools: Bash(agent-browser:*), Bash(npx agent-browser:*)
---

# agent-browser

Use installed CLI docs; this stub must not duplicate versioned command guidance.

Start by checking the installed version and supported commands:

```bash
agent-browser --version
agent-browser --help
```

If the CLI provides `skills`, read its native guides below. Otherwise, use the installed command help.

```bash
agent-browser skills get core
agent-browser skills get core --full
```

Specialized docs:

```bash
agent-browser skills get electron
agent-browser skills get slack
agent-browser skills get dogfood
agent-browser skills get vercel-sandbox
agent-browser skills get agentcore
agent-browser skills list
```

Dashboard: port `4848`, dashboard origin only; session ports stay internal/proxied.
