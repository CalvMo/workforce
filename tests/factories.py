from datetime import date

from django.contrib.auth import get_user_model

from leave.models import LeaveType
from people.models import Employee


def employee(username, manager=None, start=date(2025, 1, 1)):
    user = get_user_model().objects.create_user(username, password="pw12345!", first_name=username.title())
    return Employee.objects.create(user=user, employee_number=username.upper(), manager=manager, start_date=start)


def annual_leave(**kw):
    defaults = dict(code="ANN", name="Annual leave", annual_entitlement=15, accrual="monthly",
                    cycle_months=12, max_carry_over=5)
    defaults.update(kw)
    return LeaveType.objects.create(**defaults)


def sick_leave(**kw):
    defaults = dict(code="SICK", name="Sick leave", annual_entitlement=30, accrual="upfront",
                    cycle_months=36, max_carry_over=0, requires_attachment=True)
    defaults.update(kw)
    return LeaveType.objects.create(**defaults)
