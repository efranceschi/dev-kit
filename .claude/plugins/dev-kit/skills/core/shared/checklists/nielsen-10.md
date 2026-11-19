# Nielsen's 10 usability heuristics — audit checklist

For each heuristic, inspect the flows/screens in scope and record violations as findings (`category: usability`). Severity: 0 none · 1 cosmetic (low) · 2 minor (medium) · 3 major (high) · 4 catastrophic (critical).

1. **Visibility of system status** — loading indicators, progress, saved/unsaved state, success confirmations, current location in navigation.
2. **Match between system and real world** — domain vocabulary of the personas, natural ordering, familiar icons, locale-correct formats.
3. **User control and freedom** — undo/redo, cancel, back without losing input, escape from modals, no dead ends.
4. **Consistency and standards** — same action same label/placement everywhere; platform conventions; consistent with `ui-spec.md`.
5. **Error prevention** — constraints and defaults that avoid errors, confirmation only for destructive/irreversible actions, inline validation before submit.
6. **Recognition rather than recall** — visible options, recently used items, contextual help, labels not placeholders alone.
7. **Flexibility and efficiency of use** — shortcuts, bulk actions, sensible defaults, remembered preferences, keyboard navigation.
8. **Aesthetic and minimalist design** — one primary action per screen, no competing emphasis, progressive disclosure.
9. **Help users recognise, diagnose, recover from errors** — plain-language error messages that say what happened and what to do; errors next to the field; preserve input.
10. **Help and documentation** — onboarding, empty states that teach, tooltips, searchable help where the product is complex.

Also check (not Nielsen but expected):
- Empty, loading, error, offline states exist for every list/detail screen.
- Destructive actions are reversible or doubly confirmed.
- Forms: tab order, autofocus, enter submits, autocomplete attributes.
- Copy matches the tone in the brief and the application language.
