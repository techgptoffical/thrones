# Thrones interface design specification

## Identity

Thrones should feel like a well-made instrument: calm, exact, a little warm. The identity is carried by **typography and one accent**, not by decoration.

- **Mark:** three pillars on a base. The centre pillar is antique gold: a seat, a crown, a signal. Used at 22 px in the sidebar, 38 px on the welcome screen and as the favicon. No glow, no gradient.
- **Voice in type:** the brand name and the welcome line are set in *Instrument Serif*; everything you work with is in *Geist*; code and paths in *Geist Mono*. The serif appears in only three places (brand, welcome greeting, settings title), so it stays special.
- **Accent:** antique gold (`#B08A3A` solid; `#86661C` light-mode text; `#D6B56E` dark-mode text). It marks only things that carry meaning: the active mode icon, citation chips, the "selected/in memory" model tags, a running indicator, focus rings. Never backgrounds, never large areas.
- **Neutrals:** warm graphite and bone, not blue-grey. Light `#F6F6F3` page, `#FFFFFF` surfaces, `#17181A` text; dark `#141516` page, `#1A1B1D` surfaces, `#ECEBE7` text.

Explicitly avoided: neon or purple gradients, glass panels, glowing orbs, decorative charts, oversized icons, card grids for features, animated backgrounds, marketing copy inside the product.

## Tokens (`frontend/src/styles/tokens.css`)

| Group | Tokens |
|---|---|
| Type scale | 12 / 13 / 14 / 15.5 (body) / 18 px, multiplied by the *Text size* setting (0.92 / 1 / 1.1) |
| Line height | 1.6 UI, 1.68 for answers |
| Radii | 6, 8, 12, 16, 22 (composer) |
| Layout | sidebar 272 px; reading column 760 px; row height 34 px (30 compact) |
| Motion | 120 ms (hover/press), 200 ms (sidebar, dialogs), `cubic-bezier(0.2,0,0,1)`; all motion off under `prefers-reduced-motion` |
| Shadows | three levels only (sm for composer, md for menus/popovers, lg for dialogs/toasts) |
| Status colours | ok green, warn amber, danger red — used in text and small dots, never as fills except error banners |

Both themes define every token; components never hard-code colours. Code highlighting uses theme tokens too, so code blocks match the page.

## Layout

```
┌──────────────┬──────────────────────────────────────────────┐
│ ▮ Thrones  ⇤ │  Conversation title           [docs] [⤓]     │
│ ✎ New chat   │                                              │
│ ⌕ Search     │        ┌ 760 px reading column ┐              │
│              │        │  user bubble (right)  │              │
│ Projects  +  │        │  activity  ▸ steps    │              │
│ Research     │        │  answer (markdown)    │              │
│ Today        │        │  sources grid         │              │
│ Yesterday    │        │  ⧉ ↻  model · mode · tok/s · time │   │
│ …            │        └───────────────────────┘              │
│──────────────│   ┌──────────── composer ─────────────┐       │
│ ● Qwen3.5 9B │   │ Ask anything                      │       │
│ ⚙ Settings   │   │ 📎 [Fast|Think|Deep Research]  model ▾ ⬆│  │
└──────────────┴───┴───────────────────────────────────┴───────┘
```

- **Sidebar:** New chat, Search, Projects (collapsible, rename/delete, "new chat in project"), Research history (Deep Research conversations), chats grouped Today / Yesterday / Previous 7 days / 30 days / Older. Per-item menu: rename, export (MD/JSON), move to project, delete (confirmation dialog). Footer: live engine status (dot + model + state) and Settings. Collapses with Ctrl+B; below 900 px it becomes an overlay drawer.
- **Welcome:** mark, serif greeting with the accent clause in italic gold, one line naming the model that is running and the privacy promise, six starter prompts as a quiet two-column list (each pre-selects its mode). When no model is installed this becomes a single setup card instead.
- **Answer:** an *Activity* panel lists the real steps (planning text, each tool call with its input and result, verification verdict, each research stage) — open while running, collapsed afterwards to "Worked through N steps · 56 s". Model reasoning is a separate, collapsed disclosure. The answer follows, then sources, then actions.
- **Composer:** auto-growing textarea (Enter sends, Shift+Enter newline, IME-safe), attach (button, drag-and-drop, paste), segmented mode control, model picker, send ↔ stop. A one-line hint under the composer states what the current mode will do, or why it cannot run (no model, offline, research disabled).

## Components and states

| Component | States |
|---|---|
| Buttons | default, hover (`--hover`), pressed (`--pressed`), disabled (40–50 % opacity, `not-allowed`), focus ring (2 px gold, 2 px offset) |
| Mode control | selected segment raised on surface with gold icon; disabled while generating |
| Send | disabled (28 % opacity) when empty / uploading / no model; becomes Stop while streaming; Esc also stops |
| Steps | running (gold spinner), done (green check), error (red ×), skipped/stopped (grey −) |
| Citations | inline gold chip `[n]` → hover/focus card with site, date, title, snippet; click opens the real URL |
| Sources | grid of cards (number, site, date or "undated", title); sources read but not cited are dimmed |
| Metrics | the meta line under each answer opens a popover with measured speed, first-token latency, total time, tokens, model/tool calls, peak VRAM and engine RAM, context size, load time |
| Errors | inline red banner in the answer with the engine's actual message; toasts for transient errors |
| Empty / loading | conversation load spinner; "Thinking…" with notice text while waiting for the first token |

## Settings

Modal with side navigation (horizontal on narrow screens), sections: General (theme, density, text size, style, custom instructions, reasoning visibility) · Models & hardware (live hardware readout, engine status with apply/load/unload, profile cards, context/GPU layers/idle unload, model list with download progress, compatibility and licences) · Generation (sampling, Think budgets) · Research (web access, provider, depth) · Tools (what exists, what is off, what is not available) · Memory (list, add, edit, toggle, delete, clear, export) · Privacy & data (offline mode, every outbound request listed, export, delete all, storage paths) · About (what Thrones is and is not, base model and runtime attribution, honest limits).

Number fields commit on blur/Enter only; destructive actions use inline confirmation; anything not available in 1.0 is labelled "Not available" rather than hidden behind a dead control.

## Accessibility

- Keyboard: Ctrl+Shift+O new chat, Ctrl+K search, Ctrl+B sidebar, Ctrl+, settings, Ctrl+/ focus composer, Esc stop/close. Dialogs trap focus and restore it on close; menus close on Escape and outside click.
- Semantics: `nav`, `main`, `header`; radio groups for mode and choices; switches use `role="switch"` + `aria-checked`; live answer region is `aria-live="polite"` and `aria-busy`; every icon-only button has an `aria-label`.
- Contrast: body text ≥ 12:1 in both themes; muted text (`--text-3`) is used only for secondary information and was chosen to stay legible at 12–13 px.
- No automatic remote requests from rendered answers: Markdown images become links; links open in a new tab with `noopener`.

## Not yet done (tracked in PROGRESS.md)

Formal screen-reader audit; right-to-left layout; per-message edit; a native desktop window (Tauri).
