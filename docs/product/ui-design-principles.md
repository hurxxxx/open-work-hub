# UI Design Principles: Clean Enterprise Standard

The application follows a clean, professional, and dense enterprise design system inspired by top-tier work management tools like ClickUp and Jira. 

## Core Philosophy: "No AI Dashboards"
The administrative and settings interfaces must strictly avoid looking like an "AI Dashboard" or a generic admin dashboard template.
- **No unnecessary metric cards:** Settings pages are for configuring systems, not primarily for viewing dashboard metrics. We do not use top-heavy `StatCards` (e.g., total users, active events) unless specifically on a dedicated Analytics page.
- **Immediate action:** The user should immediately see the configuration forms, lists, or tables without having to scroll past large summary boxes.

## Layout & Structure
- **Edge-to-edge content:** Remove heavy container borders. Sections should blend seamlessly into the background (`bg-app-bg`), using typography and subtle dividers to create hierarchy rather than boxed cards or deep shadows.
- **Flat Tables:** Tables must not be wrapped in large bordered cards. They should run fully flat, relying on clean `<tr className="border-b">` lines. 
- **Subtle Toolbars:** Search bars and action buttons (`Invite`, `Create`) should sit organically above the lists/tables on a single row, taking up minimal vertical space.

## Mobile App Shell
- **Separate global and local navigation:** The mobile hamburger opens only the global app/workspace switcher. It must not also render the current app's submenu.
- **Current app menu from title:** When an app has internal navigation, the compact mobile app title opens a dedicated current-app menu drawer. Screens without internal navigation render the title as static text.
- **No three-pane mobile workflows:** Dense desktop layouts may use app bar + sub-sidebar + content, but mobile task workflows should collapse into a single primary flow with explicit drawers or full-width detail panels.
- **Route changes close transient chrome:** Mobile app switcher and current-app menu drawers should close on pathname/search changes so stale navigation chrome does not follow the user into a new view.

## Typography and Spacing
- Use compact, high-density typography for standard rows.
- Use distinct sizing and font-weight for main headers to immediately orient the user, without adding excessive paddings below them.
- Secondary descriptions should use the shared semantic muted-ink token (for example, `text-app-ink-muted`) and be situated closely to the primary header or element they describe.

## UI Primitives
- **Cards:** If a card must be used, it should be visually subtle—a simple light border with `rounded-xl` and no dramatic box-shadow. Do not use cards for purely textual lists.
- **Inputs:** Form fields should have a low-profile default state, highlighting (e.g., `focus:border-app-accent`) only upon interaction.
- **Buttons:** Primary actions use a solid distinct color. Secondary actions are mostly borderless ghost buttons or thinly outlined, relying on hover states to show interactivity. No gradient buttons.

## File Upload Status
- File uploads should use a lower-right floating upload manager so users can keep seeing progress while navigating inside the SPA.
- The upload manager state is intentionally scoped to the current browser tab's SPA lifetime.
- Refresh recovery, tab-close recovery, browser-restart recovery, resumable uploads, offline queues, and chunk-session restore are explicit non-goals for this requirement. Do not re-plan them unless the requirement is explicitly reopened.
