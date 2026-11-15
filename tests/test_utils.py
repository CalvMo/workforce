from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from people.utils import add_months, is_public_holiday, working_days_between


class WorkingDayTests(SimpleTestCase):
    def test_full_week_without_holidays(self):
        # Mon 9 Nov to Fri 13 Nov 2026
        self.assertEqual(working_days_between(date(2026, 11, 9), date(2026, 11, 13)), 5)

    def test_election_day_excluded(self):
        # 4 Nov 2026 is the Local Government Elections public holiday
        self.assertEqual(working_days_between(date(2026, 11, 2), date(2026, 11, 6)), 4)

    def test_weekend_excluded(self):
        self.assertEqual(working_days_between(date(2026, 11, 6), date(2026, 11, 9)), 2)

    def test_sa_public_holidays_excluded(self):
        # Week of Christmas 2026: Fri 25 Dec is Christmas, Sat 26 Dec Day of Goodwill (weekend anyway)
        self.assertTrue(is_public_holiday(date(2026, 12, 25)))
        self.assertEqual(working_days_between(date(2026, 12, 21), date(2026, 12, 25)), 4)

    def test_sunday_holiday_observed_on_monday(self):
        # Freedom Day 27 April 2025 fell on a Sunday, so Monday 28 April was a public holiday
        self.assertTrue(is_public_holiday(date(2025, 4, 28)))

    def test_half_days(self):
        self.assertEqual(working_days_between(date(2026, 11, 9), date(2026, 11, 13), True, True), Decimal("4"))
        self.assertEqual(working_days_between(date(2026, 11, 9), date(2026, 11, 9), True, False), Decimal("0.5"))

    def test_add_months_clamps(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 15), 3), date(2027, 2, 15))
