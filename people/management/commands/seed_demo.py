from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from leave.models import LeaveType
from leave.services import run_cycle_rollover, run_monthly_accrual
from people.models import Department, Employee
from people.utils import add_months
from timesheets.models import Project

DEMO_PASSWORD = "demo12345"


class Command(BaseCommand):
    help = "Create demo leave types, projects and users (admin, manager, two staff)."

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()

        # South African defaults (BCEA minimums for a five-day week). Adjust to company policy.
        leave_types = [
            dict(code="ANN", name="Annual leave", annual_entitlement=15, accrual="monthly",
                 cycle_months=12, max_carry_over=5),
            dict(code="SICK", name="Sick leave", annual_entitlement=30, accrual="upfront",
                 cycle_months=36, max_carry_over=0, requires_attachment=True),
            dict(code="FRL", name="Family responsibility leave", annual_entitlement=3, accrual="upfront",
                 cycle_months=12, max_carry_over=0),
            dict(code="STUDY", name="Study leave", annual_entitlement=5, accrual="upfront",
                 cycle_months=12, max_carry_over=0),
            dict(code="UNPAID", name="Unpaid leave", annual_entitlement=0, accrual="none",
                 cycle_months=12, allow_negative=True),
        ]
        for lt in leave_types:
            LeaveType.objects.update_or_create(code=lt["code"], defaults=lt)

        for code, name, client in [
            ("INT-ADMIN", "Internal admin", ""), ("INT-TRAIN", "Training", ""),
            ("CUST-001", "Customer implementation", "Acme Ltd"), ("CUST-002", "Managed services", "Globex"),
        ]:
            Project.objects.update_or_create(code=code, defaults={"name": name, "client": client,
                                                                   "billable": code.startswith("CUST")})

        ops, _ = Department.objects.get_or_create(name="Operations")
        start = add_months(timezone.localdate().replace(day=1), -14)

        def make(username, first, last, number, manager=None, staff=False, superuser=False):
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first, "last_name": last,
                                             "email": f"{username}@example.com",
                                             "is_staff": staff, "is_superuser": superuser})
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            emp, _ = Employee.objects.get_or_create(
                user=user, defaults={"employee_number": number, "department": ops,
                                     "manager": manager, "start_date": start})
            return emp

        boss = make("admin", "Admin", "User", "E000", staff=True, superuser=True)
        mgr = make("manager", "Thandi", "Mokoena", "E001", manager=boss)
        make("staff1", "Sipho", "Dlamini", "E002", manager=mgr)
        make("staff2", "Anika", "van der Merwe", "E003", manager=mgr)

        # Back-fill accruals and cycle grants so balances are realistic.
        d = start
        while d <= timezone.localdate():
            run_cycle_rollover(d)
            nxt = add_months(d, 1)
            month_end = nxt - timedelta(days=1)
            if month_end < timezone.localdate():
                run_monthly_accrual(month_end)
            d = nxt

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Users: admin, manager, staff1, staff2. Password: {DEMO_PASSWORD}"
        ))
