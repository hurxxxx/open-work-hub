# UI Design Principles

- Dense enterprise UI; no marketing/admin-dashboard chrome for work surfaces.
- Settings pages start with forms/lists/tables, not metric cards.
- Prefer edge-to-edge sections, typography, subtle dividers; avoid heavy card wrappers and shadows.
- Tables are flat rows, not bordered cards.
- Toolbars are single-row and compact.
- Mobile global hamburger opens the global app launcher; workspace selection stays inside the current workspace app menu.
- Mobile current-app title opens current app menu when internal nav exists.
- Mobile dense workflows collapse to one primary flow with drawers/full-width detail.
- Route changes close transient mobile chrome.
- Typography is compact; descriptions use semantic muted token near the controlled element.
- Cards only when a real framed item/modal is needed; keep them subtle.
- Inputs are low-profile; primary buttons solid; secondary ghost/outline; no gradient buttons.
- Upload progress uses lower-right floating manager scoped to current SPA tab.
- No refresh/tab/browser restart recovery, resumable upload, offline queue, or chunk-session restore unless explicitly reopened.
