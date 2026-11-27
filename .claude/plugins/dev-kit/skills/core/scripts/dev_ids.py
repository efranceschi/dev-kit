"""The one definition of every dev-kit id (conventions.md §3): patterns, canonical forms, order and numbering.

Every script reads ids through this module; the lint refuses an id pattern written anywhere else, and the board
gets the same patterns from the server (`board_patterns()`), so an id valid in state is valid everywhere.

Rules: ids are global and continuous in the project, never restarted per release, never reused (not even one
retired from the plan) and never renumbered once they have history (a QA folder, a branch, events). Gaps are fine.
Standard library only.
"""
from __future__ import annotations

import re

SEQ = r"\d{1,6}"  # what a reader accepts; the kit writes at least 3 digits (T-001)
MILESTONE = r"M\d{1,4}(?:\.\d{1,3})?"  # M5, or M5.1 for the fixes milestone of a rejected release
RELEASE = r"R\d{1,4}"
TASK = rf"T-{SEQ}"
ISSUE = rf"I-{SEQ}"
QUESTION = rf"Q-{SEQ}"
FACT = rf"K-{SEQ}"
FINDING = rf"F-{SEQ}"
DEFERRED = rf"D-{SEQ}"
ADR = rf"ADR-{SEQ}"
REQUEST = rf"P-{SEQ}"
AC = r"AC-\d{1,4}"
SCREEN = r"S-\d{1,4}"
STORY = r"US-\d{1,4}"
JOURNEY = r"J-\d{1,4}"

KINDS = {
    "milestone": MILESTONE, "release": RELEASE, "task": TASK, "issue": ISSUE, "question": QUESTION,
    "fact": FACT, "finding": FINDING, "deferred": DEFERRED, "adr": ADR, "request": REQUEST, "ac": AC,
    "screen": SCREEN, "story": STORY, "journey": JOURNEY,
}
PREFIX = {"task": "T-", "issue": "I-", "question": "Q-", "fact": "K-", "finding": "F-", "deferred": "D-",
          "adr": "ADR-", "request": "P-"}
_FULL = {k: re.compile(rf"^{v}$") for k, v in KINDS.items()}
# a finding cited outside its report carries its scope: M4/F-003, release/F-002
SCOPED_FINDING = rf"(?:{MILESTONE}|release)/{FINDING}"
# almost a milestone or release heading: "## M01", "## m1", "## Milestone 1", "## Release 2", "## M1: title"
NEAR_HEADING = re.compile(r"^##\s+(?:(?P<mword>milestone)\s*|(?P<m>m)|(?P<rword>release)\s*|(?P<r>r))0*(?P<n>\d{1,4})"
                          r"(?P<sub>\.\d{1,3})?\b\s*(?P<sep>[:.)]?)", re.I)


def pattern(kind: str) -> str:
    return KINDS[kind]


def is_id(kind: str, s: object) -> bool:
    return bool(_FULL[kind].match(str(s or "")))


def fmt(kind: str, n: int) -> str:
    """The canonical id number n of a kind: M7, R2, T-007, ADR-012."""
    if kind == "milestone":
        return f"M{int(n)}"
    if kind == "release":
        return f"R{int(n)}"
    return f"{PREFIX[kind]}{int(n):03d}"


def number(s: str) -> int:
    """The integer part of an id (M5.1 → 5, T-012 → 12); -1 when it has none."""
    m = re.search(r"(\d+)", str(s or ""))
    return int(m.group(1)) if m else -1


def mkey(m: str) -> tuple[int, int]:
    """Order of a milestone id: M5 < M5.1 < M5.2 < M6 (a release's fixes milestone follows its last milestone)."""
    mm = re.fullmatch(r"M(\d+)(?:\.(\d+))?", str(m))
    return (int(mm.group(1)), int(mm.group(2) or 0)) if mm else (10 ** 6, 0)


def mmajor(m: str) -> int:
    return mkey(m)[0]


def canonical(kind: str, s: str) -> str | None:
    """The canonical form of an id written another way (M01, m1, 'Milestone 1', T-1, t-0012), or None."""
    raw = str(s or "").strip()
    if kind in ("milestone", "release"):
        letter = "M" if kind == "milestone" else "R"
        word = "milestone" if kind == "milestone" else "release"
        mm = re.fullmatch(rf"(?i)(?:{word}\s*|{letter})0*(\d{{1,4}})(?:\.0*(\d{{1,3}}))?", raw)
        if not mm:
            return None
        sub = f".{int(mm.group(2))}" if mm.group(2) and kind == "milestone" else ""
        if mm.group(2) and kind == "release":
            return None
        return f"{letter}{int(mm.group(1))}{sub}"
    pre = PREFIX[kind]
    mm = re.fullmatch(rf"(?i){re.escape(pre)}\s*(\d{{1,6}})", raw)
    return fmt(kind, int(mm.group(1))) if mm else None


def is_canonical(kind: str, s: str) -> bool:
    return is_id(kind, s) and canonical(kind, s) == s


def next_milestone(used: list[str] | set[str], retired: list[str] | tuple = (), first: int = 1) -> str:
    """The next free milestone number: one above every used or retired milestone, never below `first`."""
    nums = [mmajor(x) for x in list(used) + list(retired) if is_id("milestone", x)]
    return f"M{max(nums + [int(first) - 1]) + 1}"


def next_release(used: list[str] | set[str], retired: list[str] | tuple = ()) -> str:
    nums = [number(x) for x in list(used) + list(retired) if is_id("release", x)]
    return f"R{max(nums + [0]) + 1}"


def next_seq(kind: str, counter: int, used, retired=()) -> tuple[str, int]:
    """The next id of a counted kind from its counter, skipping every used or retired number.
    Returns (id, the new counter value)."""
    taken = {number(x) for x in list(used) + list(retired) if is_id(kind, x)}
    n = max(int(counter or 1), 1)
    while n in taken:
        n += 1
    return fmt(kind, n), n + 1


def board_patterns() -> dict:
    """The patterns the board's page uses to recognise and link ids (no anchors, no groups)."""
    return {k: v for k, v in KINDS.items()}
