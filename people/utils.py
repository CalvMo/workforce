import calendar
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache

import holidays
from django.conf import settings


def add_months(d: date, months: int) -> date:
    """Add calendar months, clamping to the last day of the month (31 Jan + 1 = 28/29 Feb)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@lru_cache(maxsize=32)
def _holidays_for(country: str, year: int):
    # python-holidays already applies the SA rule that a Sunday holiday moves to Monday.
    return holidays.country_holidays(country, years=year)


def is_public_holiday(d: date, country: str | None = None) -> bool:
    country = country or settings.HOLIDAY_COUNTRY
    return d in _holidays_for(country, d.year)


def holiday_name(d: date, country: str | None = None) -> str | None:
    country = country or settings.HOLIDAY_COUNTRY
    return _holidays_for(country, d.year).get(d)


def is_working_day(d: date, country: str | None = None) -> bool:
    return d.weekday() < 5 and not is_public_holiday(d, country)


def working_days_between(
    start: date,
    end: date,
    start_half_day: bool = False,
    end_half_day: bool = False,
    country: str | None = None,
) -> Decimal:
    """
    Count working days in [start, end], excluding weekends and public holidays.
    Half-day flags take 0.5 off the first or last day when that day is a working day.
    """
    if end < start:
        return Decimal("0")
    total = Decimal("0")
    d = start
    while d <= end:
        if is_working_day(d, country):
            total += 1
        d += timedelta(days=1)
    if start_half_day and is_working_day(start, country):
        total -= Decimal("0.5")
    if end_half_day and is_working_day(end, country) and end != start:
        total -= Decimal("0.5")
    return max(total, Decimal("0"))


def week_start_for(d: date) -> date:
    return d - timedelta(days=d.weekday())
