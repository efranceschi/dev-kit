# Visual review checklist (visual-reviewer)

Compare the **rendered** interface with `.dev/design/ui-spec.md`. Findings use `category: visual` or `consistency`. Every finding cites the screen id, viewport and screenshot file.

## Capture protocol
- Viewports: 1280×800 (desktop), 768×1024 (tablet, if in scope), 375×812 (mobile). Themes: light, plus dark when the brief requires it.
- States per screen: default, loading, empty, error, filled/long content, focus (Tab to the first control), hover on primary action when possible.
- Use the project's existing Playwright setup or `npx playwright screenshot`; never install packages. If the app cannot run, say so and audit from markup/CSS and any screenshots provided.
- Read every screenshot; do not infer visuals from code alone.

## What to check
1. **Layout integrity**: no overflow, clipped or overlapping text/controls, no horizontal scroll at 375 px, consistent page margins and max widths, sensible wrapping of long words/names.
2. **Spacing and alignment**: spacing values come from the scale; elements align on a grid; consistent gaps between repeated items; baseline alignment of label/value pairs.
3. **Typography**: type scale and weights as in spec; line length 45–90 characters for body text; no more than two families; headings visibly ranked; numbers aligned in tables.
4. **Colour and contrast**: tokens used, not hard-coded hex; semantic colours used for their meaning only; contrast visible in the actual render (spot-check with computed values); disabled vs enabled distinguishable.
5. **Hierarchy**: one dominant primary action per screen; secondary actions visually subordinate; important information not buried; consistent iconography and icon sizes.
6. **Components**: variants and states render as specified (focus ring visible, loading indicator, error styling, disabled); consistent radius, borders, shadows; tables, cards and forms follow the inventory.
7. **Responsive behaviour**: reflow matches the spec per breakpoint; touch targets large enough; navigation adapts; images scale without distortion.
8. **Polish**: empty states are designed (not blank); skeletons/spinners avoid layout shift; truncation has a tooltip or expand; transitions are subtle and respect reduced motion; favicon/title set.
9. **Dark mode** (if required): no unreadable elements, images/icons adapt, shadows/borders still visible.

## Severity guide
Broken layout or unreadable content on a main screen → `high`. Spec deviation visible to users → `medium`. Pixel nits → `low`. Missing state implementation required by spec → `high`.
