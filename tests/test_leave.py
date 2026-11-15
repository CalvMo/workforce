from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from leave import services
from leave.models import LeaveLedgerEntry, LeaveRequest
from people.utils import add_months

from .factories import annual_leave, employee, sick_leave


class LeaveFlowTests(TestCase):
    def setUp(self):
        self.mgr = employee("mgr")
        self.emp = employee("emp", manager=self.mgr)
        self.other = employee("other")
        self.ann = annual_leave()
        LeaveLedgerEntry.objects.create(employee=self.emp, leave_type=self.ann, kind="adjust",
                                        days=10, effective_date=date(2025, 1, 1))

    def request(self, start=date(2026, 11, 9), end=date(2026, 11, 13), **kw):
        return services.submit_request(self.emp, leave_type=self.ann, start_date=start, end_date=end, **kw)

    def test_submit_calculates_days_and_reserves_balance(self):
        req = self.request()
        self.assertEqual(req.days, 5)
        self.assertEqual(services.available_balance(self.emp, self.ann), Decimal("5"))
        self.assertEqual(services.ledger_balance(self.emp, self.ann), Decimal("10"))

    def test_insufficient_balance_rejected(self):
        with self.assertRaises(ValidationError):
            self.request(end=date(2026, 11, 27))  # 15 days

    def test_overlap_rejected(self):
        self.request()
        with self.assertRaises(ValidationError):
            self.request(start=date(2026, 11, 12), end=date(2026, 11, 12))

    def test_manager_approval_deducts_balance(self):
        req = services.approve_request(self.request(), self.mgr)
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)
        self.assertEqual(services.ledger_balance(self.emp, self.ann), Decimal("5"))

    def test_only_manager_can_approve(self):
        req = self.request()
        with self.assertRaises(PermissionDenied):
            services.approve_request(req, self.other)
        with self.assertRaises(PermissionDenied):
            services.approve_request(req, self.emp)  # cannot approve own leave

    def test_reject_needs_comment(self):
        req = self.request()
        with self.assertRaises(ValidationError):
            services.reject_request(req, self.mgr, "")
        req = services.reject_request(req, self.mgr, "Year-end freeze")
        self.assertEqual(services.available_balance(self.emp, self.ann), Decimal("10"))

    @mock.patch("leave.services.timezone.localdate", return_value=date(2026, 10, 1))
    def test_cancel_approved_leave_restores_balance(self, _):
        req = services.approve_request(self.request(), self.mgr)
        services.cancel_request(req, self.emp)
        self.assertEqual(services.ledger_balance(self.emp, self.ann), Decimal("10"))
        kinds = list(LeaveLedgerEntry.objects.filter(request=req).values_list("kind", flat=True))
        self.assertCountEqual(kinds, ["taken", "reversal"])

    def test_sick_leave_over_two_days_needs_attachment(self):
        sick = sick_leave()
        services.run_cycle_rollover(date(2025, 1, 1))
        with self.assertRaises(ValidationError):
            services.submit_request(self.emp, leave_type=sick, start_date=date(2026, 11, 9), end_date=date(2026, 11, 11))
        req = services.submit_request(self.emp, leave_type=sick, start_date=date(2026, 11, 9), end_date=date(2026, 11, 10))
        self.assertEqual(req.days, 2)


class AccrualTests(TestCase):
    def setUp(self):
        self.emp = employee("emp", start=date(2025, 1, 1))
        self.ann = annual_leave()
        self.sick = sick_leave()

    def test_monthly_accrual_is_idempotent(self):
        services.run_monthly_accrual(date(2025, 1, 31))
        services.run_monthly_accrual(date(2025, 1, 31))
        self.assertEqual(services.ledger_balance(self.emp, self.ann), Decimal("1.25"))

    def test_upfront_grant_and_forfeit_on_new_cycle(self):
        services.run_cycle_rollover(date(2025, 1, 1))
        self.assertEqual(services.ledger_balance(self.emp, self.sick), Decimal("30"))
        services.run_cycle_rollover(date(2025, 6, 1))  # same cycle, nothing happens
        self.assertEqual(services.ledger_balance(self.emp, self.sick), Decimal("30"))
        services.run_cycle_rollover(date(2028, 1, 1))  # new 36-month cycle
        self.assertEqual(services.ledger_balance(self.emp, self.sick), Decimal("30"))
        self.assertTrue(LeaveLedgerEntry.objects.filter(kind="forfeit", days=-30).exists())

    def test_annual_carry_over_capped(self):
        for m in range(1, 13):
            month_end = add_months(date(2025, m, 1), 1) - timedelta(days=1)
            services.run_monthly_accrual(month_end)
        self.assertEqual(services.ledger_balance(self.emp, self.ann), Decimal("15"))
        services.run_cycle_rollover(date(2026, 1, 1))
        self.assertEqual(services.ledger_balance(self.emp, self.ann), Decimal("5"))
        services.run_cycle_rollover(date(2026, 1, 1))
        self.assertEqual(services.ledger_balance(self.emp, self.ann), Decimal("5"))

    def test_employee_not_yet_started_gets_nothing(self):
        late = employee("late", start=date(2025, 3, 1))
        services.run_monthly_accrual(date(2025, 1, 31))
        self.assertEqual(services.ledger_balance(late, self.ann), 0)
