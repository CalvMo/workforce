import calendar
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from leave.services import run_cycle_rollover, run_monthly_accrual


class Command(BaseCommand):
    help = (
        "Run leave accruals and cycle rollovers. Safe to run daily: both jobs are idempotent. "
        "Accrual is credited for the most recently completed month."
    )

    def add_arguments(self, parser):
        parser.add_argument("--as-of", help="Run as if today were this date (YYYY-MM-DD).")

    def handle(self, *args, **opts):
        today = date.fromisoformat(opts["as_of"]) if opts["as_of"] else timezone.localdate()
        last_day = calendar.monthrange(today.year, today.month)[1]
        if today.day == last_day:
            month_end = today
        else:
            prev_year, prev_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
            month_end = date(prev_year, prev_month, calendar.monthrange(prev_year, prev_month)[1])
        accrued = run_monthly_accrual(month_end)
        rolled = run_cycle_rollover(today)
        self.stdout.write(self.style.SUCCESS(
            f"Accrual for {month_end:%Y-%m}: {accrued} entries. Cycle rollover actions: {rolled}."
        ))
