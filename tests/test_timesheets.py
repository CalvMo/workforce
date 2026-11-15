from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from leave import services as leave_services
from leave.models import LeaveLedgerEntry
from timesheets import services
from timesheets.models import Project, Timesheet

from .factories import annual_leave, employee


class TimesheetTests(TestCase):
    def setUp(self):
        self.mgr = employee("mgr")
        self.emp = employee("emp", manager=self.mgr)
        self.project = Project.objects.create(code="P1", name="Project one")
        self.ts = services.get_or_create_week(self.emp, date(2026, 11, 4))

    def test_week_starts_on_monday(self):
        self.assertEqual(self.ts.week_start, date(2026, 11, 2))

    def test_entry_validation(self):
        with self.assertRaises(ValidationError):
            services.save_entry(self.ts, project=self.project, entry_date=date(2026, 11, 10), hours=8)
        with self.assertRaises(ValidationError):
            services.save_entry(self.ts, project=self.project, entry_date=date(2026, 11, 2), hours=20)

    def test_daily_cap_across_projects(self):
        p2 = Project.objects.create(code="P2", name="Two")
        services.save_entry(self.ts, project=self.project, entry_date=date(2026, 11, 2), hours=10)
        with self.assertRaises(ValidationError):
            services.save_entry(self.ts, project=p2, entry_date=date(2026, 11, 2), hours=7)

    def test_submit_approve_and_lock(self):
        services.save_entry(self.ts, project=self.project, entry_date=date(2026, 11, 2), hours=8)
        services.submit_timesheet(self.ts, self.emp)
        self.ts.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.save_entry(self.ts, project=self.project, entry_date=date(2026, 11, 3), hours=8)
        with self.assertRaises(PermissionDenied):
            services.decide_timesheet(self.ts, self.emp, True)
        ts = services.decide_timesheet(self.ts, self.mgr, True)
        self.assertEqual(ts.status, Timesheet.Status.APPROVED)

    def test_rejected_timesheet_is_editable_again(self):
        services.save_entry(self.ts, project=self.project, entry_date=date(2026, 11, 2), hours=8)
        services.submit_timesheet(self.ts, self.emp)
        ts = services.decide_timesheet(self.ts, self.mgr, False, "Missing Friday")
        self.assertTrue(ts.is_editable)

    def test_expected_hours_exclude_holidays_and_leave(self):
        ts = services.get_or_create_week(self.emp, date(2026, 12, 21))  # Christmas Friday
        self.assertEqual(services.expected_hours(ts), Decimal("32"))
        ann = annual_leave()
        LeaveLedgerEntry.objects.create(employee=self.emp, leave_type=ann, kind="adjust", days=5,
                                        effective_date=date(2025, 1, 1))
        req = leave_services.submit_request(self.emp, leave_type=ann, start_date=date(2026, 12, 21),
                                            end_date=date(2026, 12, 21), end_half_day=False, start_half_day=True)
        leave_services.approve_request(req, self.mgr)
        self.assertEqual(services.expected_hours(ts), Decimal("28"))


class ViewSmokeTests(TestCase):
    def setUp(self):
        self.mgr = employee("mgr")
        self.emp = employee("emp", manager=self.mgr)
        self.project = Project.objects.create(code="P1", name="Project one")
        annual_leave()
        self.client.login(username="emp", password="pw12345!")

    def test_pages_render(self):
        for name in ["dashboard", "leave:mine", "leave:team", "leave:approvals",
                     "timesheets:week", "timesheets:history", "timesheets:approvals"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_timesheet_post_saves_and_submits(self):
        url = reverse("timesheets:week") + "?week=2026-11-02"
        resp = self.client.post(url, {f"h_{self.project.pk}_2026-11-02": "7.5", "submit": "1"})
        self.assertEqual(resp.status_code, 302)
        ts = Timesheet.objects.get(employee=self.emp)
        self.assertEqual(ts.status, "submitted")
        self.assertEqual(ts.total_hours, Decimal("7.5"))

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
