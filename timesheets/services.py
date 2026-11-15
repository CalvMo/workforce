from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from leave.models import LeaveRequest
from people.models import Employee
from people.utils import is_working_day, week_start_for

from .models import Timesheet, TimesheetEntry


def get_or_create_week(employee: Employee, any_day: date) -> Timesheet:
    ts, _ = Timesheet.objects.get_or_create(employee=employee, week_start=week_start_for(any_day))
    return ts


def expected_hours(ts: Timesheet) -> Decimal:
    """Standard hours for working days in the week, less approved leave days."""
    per_day = ts.employee.standard_hours_per_day
    total = Decimal("0")
    approved_leave = LeaveRequest.objects.filter(
        employee=ts.employee, status=LeaveRequest.Status.APPROVED,
        start_date__lte=ts.week_end, end_date__gte=ts.week_start,
    )
    for d in ts.days():
        if not is_working_day(d):
            continue
        day_factor = Decimal("1")
        for lr in approved_leave:
            if lr.start_date <= d <= lr.end_date:
                half = (d == lr.start_date and lr.start_half_day) or (d == lr.end_date and lr.end_half_day)
                day_factor = Decimal("0.5") if half else Decimal("0")
        total += per_day * day_factor
    return total


@transaction.atomic
def save_entry(ts: Timesheet, *, project, entry_date, hours, notes="") -> TimesheetEntry:
    if not ts.is_editable:
        raise ValidationError("This timesheet is locked.")
    entry, _ = TimesheetEntry.objects.get_or_create(
        timesheet=ts, project=project, date=entry_date, defaults={"hours": hours, "notes": notes}
    )
    entry.hours = hours
    entry.notes = notes
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def submit_timesheet(ts: Timesheet, by: Employee) -> Timesheet:
    ts = Timesheet.objects.select_for_update().get(pk=ts.pk)
    if by.pk != ts.employee_id:
        raise PermissionDenied("You can only submit your own timesheet.")
    if not ts.is_editable:
        raise ValidationError("This timesheet has already been submitted.")
    if not ts.entries.exists():
        raise ValidationError("Add at least one entry before submitting.")
    ts.status = Timesheet.Status.SUBMITTED
    ts.submitted_at = timezone.now()
    ts.decision_comment = ""
    ts.save()
    return ts


def _can_decide(approver: Employee, ts: Timesheet, user=None) -> bool:
    if approver and approver.pk == ts.employee_id:
        return False
    if approver and approver.manages(ts.employee):
        return True
    return bool(user and user.has_perm("timesheets.change_timesheet"))


@transaction.atomic
def decide_timesheet(ts: Timesheet, approver: Employee, approve: bool, comment="", user=None) -> Timesheet:
    ts = Timesheet.objects.select_for_update().get(pk=ts.pk)
    if not _can_decide(approver, ts, user):
        raise PermissionDenied("You may not approve this timesheet.")
    if ts.status != Timesheet.Status.SUBMITTED:
        raise ValidationError("Only submitted timesheets can be approved or rejected.")
    if not approve and not comment:
        raise ValidationError("Please give a reason when rejecting a timesheet.")
    ts.status = Timesheet.Status.APPROVED if approve else Timesheet.Status.REJECTED
    ts.decided_by = approver
    ts.decided_at = timezone.now()
    ts.decision_comment = comment
    ts.save()
    return ts
