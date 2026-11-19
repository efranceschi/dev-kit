# WCAG 2.2 level AA — practical checklist

Record violations as findings with `category: accessibility`. Level A/AA failures on main flows are `high`; on secondary flows `medium`.

## Perceivable
- 1.1.1 Non-text content: images have meaningful `alt` (or empty alt if decorative); icons-only buttons have accessible names.
- 1.3.1 Info and relationships: semantic HTML (headings, lists, tables with headers, `label`/`for`, fieldsets), not div soup; ARIA only when native elements cannot express it.
- 1.3.2 Meaningful sequence: DOM order equals visual/reading order.
- 1.3.5 Identify input purpose: `autocomplete` on name/email/address/etc.
- 1.4.1 Use of colour: state never conveyed by colour alone (add icon/text).
- 1.4.3 Contrast: text ≥ 4.5:1 (large text ≥ 3:1); 1.4.11 non-text (icons, borders, focus rings) ≥ 3:1.
- 1.4.4 Resize text to 200% and 1.4.10 reflow at 320 px width without horizontal scroll or loss.
- 1.4.12 Text spacing: layout survives increased line/letter spacing.
- 1.4.13 Content on hover/focus (tooltips) is dismissible, hoverable, persistent.

## Operable
- 2.1.1 Keyboard: everything reachable and operable by keyboard; 2.1.2 no keyboard traps; 2.1.4 single-key shortcuts can be turned off/remapped.
- 2.2.1 Timing adjustable (sessions, toasts) ; 2.2.2 pause/stop moving content.
- 2.3.1 No flashing > 3 times/s; respect `prefers-reduced-motion`.
- 2.4.1 Bypass blocks (skip link / landmarks); 2.4.2 page titles; 2.4.3 focus order; 2.4.4 link purpose in context; 2.4.6 descriptive headings/labels; 2.4.7 focus visible; **2.4.11 focus not obscured (new in 2.2)**.
- 2.5.3 Label in name (visible label is part of accessible name); 2.5.7 **dragging has a single-pointer alternative (2.2)**; 2.5.8 **target size ≥ 24×24 CSS px (2.2)**.

## Understandable
- 3.1.1 Page language set (`lang`); 3.1.2 language of parts when mixed.
- 3.2.1/3.2.2 No unexpected context change on focus/input; 3.2.3 consistent navigation; 3.2.4 consistent identification; **3.2.6 consistent help location (2.2)**.
- 3.3.1 Error identification in text; 3.3.2 labels/instructions; 3.3.3 error suggestion; 3.3.4 error prevention for legal/financial/data actions (review, confirm, undo); **3.3.7 redundant entry avoided (2.2)**; **3.3.8 accessible authentication: no cognitive-function tests, allow paste/password managers (2.2)**.

## Robust
- 4.1.2 Name, role, value for all custom controls; 4.1.3 status messages via `aria-live`/`role=status` without moving focus.

## How to test quickly
- Keyboard-only pass through each main flow (Tab/Shift+Tab/Enter/Space/Esc/arrows).
- Browser zoom 200%, window 320 px wide.
- Automated: axe-core / Lighthouse accessibility if available (`npx @axe-core/cli <url>` or Playwright + axe); treat automated results as a starting point, not the audit.
- Screen-reader smoke test when possible (VoiceOver/NVDA/Orca) on the primary flow.
