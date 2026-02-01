# Airlock UI — Design Brief

## Vibe

**Linear meets Vault.** Clean, dark, professional. This is a security tool for managing credentials and code execution — it should feel trustworthy and precise, not playful. Every pixel communicates competence.

## Tech

- **Svelte + Vite** — components, reactivity, tiny bundle
- Source in `ui/src/`, build output to `ui/dist/`
- `npm run dev` for development, `npm run build` for production
- No CSS framework — write clean CSS, component-scoped styles
- Google Fonts: Inter (UI) + JetBrains Mono (code/technical)

## Design Principles

1. **Status-first** — everything communicates state at a glance. Locked/unlocked, value exists/missing, active/revoked, completed/error. Use color-coded pills, not text.
2. **Minimal** — lots of whitespace, clear hierarchy, nothing decorative. If it doesn't serve a purpose, remove it.
3. **Monospace where it matters** — `ark_` IDs, credential names, code blocks, execution output, error messages.
4. **Dark mode only** — no light mode toggle. Go properly dark, not grey-dark.

## Color Palette

```
Background layers (darkest to lightest):
  --bg-base:    #0a0a0f     (page background)
  --bg-surface: #111118     (cards, sidebar)
  --bg-raised:  #1a1a24     (inputs, hover states, nested cards)
  --bg-overlay: #22222e     (dropdowns, modals)

Borders:
  --border:       rgba(255, 255, 255, 0.06)
  --border-hover: rgba(255, 255, 255, 0.12)

Text:
  --text-primary:   #e8e8ed
  --text-secondary: #8b8b9e
  --text-muted:     #55556a

Accent:
  --accent:         #6366f1  (indigo — primary actions, active states)
  --accent-hover:   #7577f5
  --accent-subtle:  rgba(99, 102, 241, 0.12)  (backgrounds behind accent elements)

Status:
  --status-success: #22c55e  (locked, value exists, completed)
  --status-warning: #f59e0b  (unlocked, value missing, pending)
  --status-error:   #ef4444  (revoked, expired, error, timeout)
  --status-info:    #6366f1  (running, awaiting)
```

## Typography

```
UI text:        Inter, system-fallback sans-serif
  Headings:     600 weight
  Body:         400 weight
  Labels:       500 weight, text-secondary, slightly smaller

Technical:      JetBrains Mono, monospace fallback
  Used for:     ark_ IDs, credential names, code, stdout, error messages
  Size:         0.875rem typically (slightly smaller than body)
```

## Layout

### Sidebar (fixed left)
- Width: 200px, collapsible to icon-only (56px)
- Airlock wordmark at top (text, not logo)
- Nav items: icon + label, highlight active with accent-subtle background
- Sections: Overview, Credentials, Profiles, Executions, Settings
- User/logout at bottom
- Subtle border-right separator

### Top area
- Section title (h1) + optional action button (top-right)
- Breadcrumbs only if needed (e.g., Profile → Profile Detail)

### Content
- Max-width: 960px, centered with generous padding
- Card-based grouping with --bg-surface background
- 1rem gap between cards

## Components

### Status Pills
Small rounded badges that communicate state instantly:

```
[🔒 Locked]      green bg-subtle + green text
[🔓 Unlocked]    amber bg-subtle + amber text
[✅ Value Set]    green bg-subtle + green text
[⚠️ Missing]     amber bg-subtle + amber text
[Active]          green
[Expired]         red
[Revoked]         red
[Completed]       green
[Error]           red
[Timeout]         red
[Pending]         amber
[Running]         indigo
```

### Cards
```
Background: --bg-surface
Border: 1px solid --border
Border-radius: 8px
Padding: 1.25rem
Hover (if clickable): border-color → --border-hover
```

### Buttons
```
Primary:    --accent bg, white text, 8px radius, 500 weight
Secondary:  transparent bg, --border border, --text-secondary, hover → --text-primary
Danger:     --status-error bg (for revoke, delete actions)
Ghost:      no bg, no border, --text-secondary, hover → --text-primary
```

### Inputs
```
Background: --bg-raised
Border: 1px solid --border
Border-radius: 6px
Focus: border-color → --accent
Padding: 0.625rem 0.875rem
Font: Inter for labels, JetBrains Mono for credential/code inputs
```

### Tables / Lists
- No heavy table borders — use subtle row separators (border-bottom on rows)
- Hover highlight: --bg-raised
- Clickable rows: cursor pointer, subtle hover transition
- Keep columns minimal — 3-4 max per table

## Pages

### Setup (first visit)
- Centered card on --bg-base, narrow width (400px)
- "Airlock" wordmark + "Set your admin password" subtitle
- Password + confirm fields
- Single CTA button: "Create Account"
- Feels like opening a vault for the first time

### Login
- Same layout as setup
- Password field + "Sign In" button
- Error state inline below the field

### Overview (dashboard)
- 3 stat cards in a row: Credentials, Profiles, Executions
- Each card: big number (accent color) + label
- Below: Recent Executions list (last 5, or "No executions yet")

### Credentials
- Header: "Credentials" + "Add Credential" button (top-right)
- List/cards: each credential shows name (monospace), description, status pill (✅ Value Set / ⚠️ No Value)
- Click → inline edit or slide-out detail
- Add form: name, description, value (password field), save button
- Empty state: "No credentials yet. Add one to get started."

### Profiles
- Header: "Profiles" + "Create Profile" button
- List: each profile shows ark_ ID (monospace, truncated), description, lock status pill, credential count
- Click → Profile Detail page
- **Profile Detail:**
  - Lock status prominent at top (big pill or banner)
  - Description (editable if unlocked)
  - Credential list: name + value_exists pill per row
  - If unlocked: "Add Credential" and "Remove" buttons, "Lock Profile" CTA at bottom (amber → green transition metaphor)
  - If locked: read-only view, "Copy ark_ ID" button, revoke button (danger)
  - Expiration date if set

### Executions
- Header: "Executions"
- Table: execution ID (mono, truncated), profile, status pill, duration, timestamp
- Click row → expandable detail: full script (code block), stdout, stderr, result (JSON), error
- Filter by: profile, status
- Empty state: "No executions yet."

### Settings
- Export / Import section (future — show placeholder)
- "About Airlock" footer with version

## Interactions

- **Transitions**: 150ms ease for hover/focus states. No fancy animations.
- **Copy to clipboard**: click ark_ ID or credential name → brief "Copied!" tooltip
- **Confirm dialogs**: for destructive actions only (revoke profile, delete credential)
- **Toast notifications**: bottom-right, auto-dismiss after 3s. Success (green), error (red).
- **Loading**: simple spinner or "Loading..." text. No skeleton screens.

## What NOT to Do

- No glassmorphism or blur effects
- No gradient backgrounds
- No oversized hero sections
- No sidebar icons that look like a SaaS marketing page
- No light mode
- No loading skeletons
- No dark theme that's actually grey — go properly dark (#0a0a0f, not #1a1a2e)
- No decorative elements — every element serves a function
