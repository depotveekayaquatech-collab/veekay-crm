"""Consecutive-zero logic, pure (no database), so every edge case can be tested directly.

A day is one of:
  ZERO      an entry exists and it says 0
  NONZERO   an entry exists and it says more than 0
  UNMARKED  nobody entered anything for the store that day
  SKIP      a day nobody is expected to enter (a company holiday, or today before anyone has had the chance): neutral, never breaks or adds to a streak

How an UNMARKED day is treated inside a streak is the caller's choice:
  "break"   it ends the run (default: a silent store is not a proven zero)
  "ignore"  it is stepped over: the run carries on across it, but the day itself is not counted
  "count"   it counts as a zero day

A NONZERO day always ends a run. The report never reads the streak back from anything stored: it is recomputed from the days it is given.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

ZERO, NONZERO, UNMARKED, SKIP = "zero", "nonzero", "unmarked", "skip"
MODES = ("break", "ignore", "count")


def analyse(days: Iterable[tuple[date, str]], mode: str = "break") -> dict:
    """`days` = (date, kind) for every calendar day of the range, oldest first. Returns the longest run and the counts.

    longest: {"length", "start", "end", "ongoing", "dates"} or None. `length` is the number of days counted into the run (in "ignore" mode the unmarked days
    stepped over are not counted); `ongoing` means the run is still open at the end of the range (nothing after it ended it); `dates` are the counted days.
    When two runs are equally long the later one is reported."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    runs: list[list[date]] = []
    current: list[date] = []
    total_zero = unmarked = 0
    last_nonzero: date | None = None
    for d, kind in days:
        if kind == SKIP:
            continue
        if kind == UNMARKED:
            unmarked += 1
        if kind == ZERO:
            total_zero += 1
        counts_as_zero = kind == ZERO or (kind == UNMARKED and mode == "count")
        if counts_as_zero:
            current.append(d)
            continue
        if kind == UNMARKED and mode == "ignore":
            continue
        if kind == NONZERO:
            last_nonzero = d
        if current:                                  # a non-zero day, or an unmarked day in "break" mode, ends the run
            runs.append(current)
            current = []
    ongoing_run = current
    if current:
        runs.append(current)
    longest = None
    if runs:
        best = max(runs, key=lambda r: (len(r), r[-1]))
        longest = {"length": len(best), "start": best[0], "end": best[-1], "ongoing": best is ongoing_run and bool(ongoing_run), "dates": best}
    return {"longest": longest, "total_zero": total_zero, "unmarked": unmarked, "last_nonzero": last_nonzero}


def severity(length: int) -> str:
    """How loud a streak should look."""
    return "critical" if length >= 7 else "high" if length >= 5 else "medium" if length >= 3 else "low" if length >= 2 else "none"
