"""The consecutive-zero logic: pure, so every edge is checked directly."""
from datetime import date, timedelta

import pytest

from app.services.zero_streak import NONZERO, SKIP, UNMARKED, ZERO, analyse, severity

Z, N, U, S = ZERO, NONZERO, UNMARKED, SKIP


def days(pattern: str, start: date = date(2026, 10, 1)):
    """'ZZNU' -> [(Oct 1, zero), (Oct 2, zero), (Oct 3, nonzero), (Oct 4, unmarked)]"""
    kinds = {"Z": Z, "N": N, "U": U, "S": S}
    return [(start + timedelta(days=i), kinds[c]) for i, c in enumerate(pattern)]


def longest(pattern, mode="break", start=date(2026, 10, 1)):
    return analyse(days(pattern, start), mode)["longest"]


def test_no_zeros_means_no_streak():
    r = analyse(days("NNNNN"))
    assert r["longest"] is None and r["total_zero"] == 0 and r["unmarked"] == 0 and r["last_nonzero"] == date(2026, 10, 5)


def test_all_zeros_is_one_ongoing_streak_the_whole_range():
    s = longest("ZZZZZZZ")
    assert (s["length"], s["start"], s["end"], s["ongoing"]) == (7, date(2026, 10, 1), date(2026, 10, 7), True)


def test_a_streak_at_the_start_of_the_range_is_not_ongoing():
    s = longest("ZZZNN")
    assert (s["length"], s["start"], s["end"], s["ongoing"]) == (3, date(2026, 10, 1), date(2026, 10, 3), False)


def test_a_streak_at_the_end_of_the_range_is_ongoing():
    s = longest("NNZZZZ")
    assert (s["length"], s["start"], s["end"], s["ongoing"]) == (4, date(2026, 10, 3), date(2026, 10, 6), True)


def test_a_non_zero_day_breaks_a_streak_and_the_longest_wins():
    s = longest("ZZNZZZNZ")
    assert (s["length"], s["start"], s["end"], s["ongoing"]) == (3, date(2026, 10, 4), date(2026, 10, 6), False)


def test_equal_streaks_report_the_latest_one():
    s = longest("ZZNZZN")
    assert s["start"] == date(2026, 10, 4) and s["length"] == 2


def test_a_single_zero_day_is_a_streak_of_one():
    assert longest("NZN")["length"] == 1


def test_unmarked_day_breaks_the_streak_by_default():
    s = longest("ZZUZZZ")
    assert (s["length"], s["start"], s["ongoing"]) == (3, date(2026, 10, 4), True)
    assert analyse(days("ZZUZZZ"))["unmarked"] == 1


def test_unmarked_days_are_stepped_over_in_ignore_mode_but_not_counted():
    s = longest("ZZUZZ", "ignore")
    assert (s["length"], s["start"], s["end"]) == (4, date(2026, 10, 1), date(2026, 10, 5))
    assert len(s["dates"]) == 4 and date(2026, 10, 3) not in s["dates"]


def test_unmarked_days_count_as_zero_in_count_mode():
    s = longest("ZUUZ", "count")
    assert (s["length"], s["start"], s["end"]) == (4, date(2026, 10, 1), date(2026, 10, 4))


def test_a_non_zero_day_ends_a_run_in_every_mode():
    for mode in ("break", "ignore", "count"):
        assert longest("ZZNZZ", mode)["length"] == 2, mode


def test_unmarked_days_are_counted_separately_whatever_the_mode():
    for mode in ("break", "ignore", "count"):
        assert analyse(days("UUZNU"), mode)["unmarked"] == 3, mode


def test_a_run_followed_only_by_ignored_unmarked_days_is_still_ongoing():
    assert longest("NZZU", "ignore")["ongoing"] is True
    assert longest("NZZU", "break")["ongoing"] is False


def test_skipped_days_neither_break_nor_add():
    s = longest("ZZSZZ")
    assert s["length"] == 4 and s["ongoing"] is True
    assert analyse(days("ZSSN"))["unmarked"] == 0                         # a holiday is not an unmarked day


def test_last_non_zero_date_is_the_latest_one():
    assert analyse(days("NZNZZ"))["last_nonzero"] == date(2026, 10, 3)


def test_a_streak_crosses_a_month_boundary():
    s = longest("ZZZZ", start=date(2026, 10, 29))
    assert (s["start"], s["end"]) == (date(2026, 10, 29), date(2026, 11, 1)) and s["length"] == 4


def test_a_streak_crosses_the_end_of_a_leap_february():
    s = longest("ZZZ", start=date(2028, 2, 28))                              # 2028 is a leap year
    assert [d.isoformat() for d in s["dates"]] == ["2028-02-28", "2028-02-29", "2028-03-01"]
    s = longest("ZZ", start=date(2027, 2, 28))                               # 2027 is not
    assert [d.isoformat() for d in s["dates"]] == ["2027-02-28", "2027-03-01"]


def test_an_empty_range_and_a_bad_mode():
    assert analyse([])["longest"] is None
    with pytest.raises(ValueError):
        analyse(days("Z"), "sometimes")


@pytest.mark.parametrize("n,label", [(0, "none"), (1, "none"), (2, "low"), (3, "medium"), (4, "medium"), (5, "high"), (6, "high"), (7, "critical"), (30, "critical")])
def test_severity_levels(n, label):
    assert severity(n) == label
