# Copy and microcopy review checklist (copy-reviewer)

Review every user-facing string against `brief.md` (block 2 languages/locales, block 7 tone) and the microcopy guide in `ux-flows.md` §7. Findings use `category: copy`.

## Find the strings
Grep the UI code, templates, i18n catalogs, email templates, error responses of the API that reach users, CLI output and help text. Also read screenshots when provided.

## Checks
1. **Language and locale**: all strings in the application language(s); no mixed languages; dates, numbers, currency, plurals and time zones formatted for the locale; no hard-coded strings if the project uses i18n catalogs (missing key → `medium`; untranslated visible string on a main flow → `high`).
2. **Tone**: matches the brief (formal/friendly/playful) consistently; same person and form of address throughout (e.g. tu/você, you/we).
3. **Clarity**: plain words; one idea per sentence; no jargon or internal terms (IDs, codes, stack traces) shown to users; labels describe the outcome ("Save changes", not "Submit").
4. **Buttons and links**: verb-first labels, specific, unique on the page; destructive actions named explicitly ("Delete project"), confirmations say what will be lost.
5. **Errors**: say what happened, why if useful, and what to do next; no blame; no raw exception text; validation messages are field-specific and appear next to the field. Generic "Something went wrong" on a recoverable error → `medium`.
6. **Empty and first-use states**: explain what belongs here and offer the next action.
7. **Success and progress**: confirmation of completed actions; progress copy for long tasks.
8. **Terminology consistency**: one term per concept across screens, emails, docs (glossary of entities from the PRD); spelling and capitalisation rules consistent.
9. **Accessibility of text**: link text meaningful out of context; alt text describes purpose; no text in images; abbreviations explained on first use.
10. **Length and truncation**: strings fit their containers in the longest supported language; no ALL CAPS paragraphs.
11. **Legal and trust**: consent, privacy and terms copy present where the brief requires; no dark patterns (confusing opt-outs, guilt copy).
12. **Spelling and grammar** in the application language.

Report each issue with the string, its location, and a proposed replacement. Severity: wrong language/unreadable on a main flow → `high`; unclear error or inconsistent term → `medium`; polish → `low`.
