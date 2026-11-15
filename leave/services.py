"""
Business rules for leave. Views and management commands call these functions
so the rules live in one place and are easy to test.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from people.models import Employee
from people.permissions import can_approve
from people.utils import add_months, working_days_between

from .models import LeaveLedgerEntry, LeaveRequest, LeaveType

TWO_DP = Decimal("0.01")


# ---------------------------------------------------------------- balances

def ledger_balance(employee: Employee, leave_type: LeaveType, as_of: date | None = None) -> Decimal:
    return LeaveLedgerEntry.balance(employee, leave_type, as_of)


def pending_days(employee: Employee, leave_type: LeaveType, exclude_pk=None) -> Decimal:
    qs = LeaveRequest.objects.filter(
        employee=employee, leave_type=leave_type, status=LeaveRequest.Status.PENDING
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.aggregate(t=Sum("days"))["t"] or Decimal("0")


def available_balance(employee: Employee, leave_type: LeaveType) -> Decimal:
    """Balance minus days already requested and awaiting approval."""
    return ledger_balance(employee, leave_type) - pending_days(employee, leave_type)


def balance_summary(employee: Employee):
    rows = []
    for lt in LeaveType.objects.filter(active=True):
        if not lt.tracks_balance:
            continue
        rows.append({
            "leave_type": lt,
            "balance": ledger_balance(employee, lt),
            "pending": pending_days(employee, lt),
            "available": available_balance(employee, lt),
        })
    return rows


# ---------------------------------------------------------------- requests

def _check_overlap(employee, start, end, exclude_pk=None):
    clash = LeaveRequest.objects.filter(
        employee=employee,
        status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
        start_date__lte=end,
        end_date__gte=start,
    )
    if exclude_pk:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise ValidationError("This overlaps with another pending or approved leave request.")


@transaction.atomic
def submit_request(employee: Employee, *, leave_type, start_date, end_date,
                   start_half_day=False, end_half_day=False, reason="", attachment=None) -> LeaveRequest:
    req = LeaveRequest(
        employee=employee, leave_type=leave_type, start_date=start_date, end_date=end_date,
        start_half_day=start_half_day, end_half_day=end_half_day, reason=reason,
    )
    if attachment:
        req.attachment = attachment
    req.full_clean(exclude=["days"])

    if not leave_type.active:
        raise ValidationError("This leave type is no longer available.")
    if start_date < employee.start_date:
        raise ValidationError("Leave cannot start before your employment start date.")

    req.days = working_days_between(start_date, end_date, start_half_day, end_half_day)
    if req.days <= 0:
        raise ValidationError("The selected period contains no working days.")

    if leave_type.requires_attachment and not attachment and req.days > 2:
        # SA practice: a medical certificate is needed for sick leave of more than two consecutive days.
        raise ValidationError(f"{leave_type.name} longer than two days requires a supporting document.")

    _check_overlap(employee, start_date, end_date)

    if leave_type.tracks_balance and not leave_type.allow_negative:
        available = available_balance(employee, leave_type)
        if req.days > available:
            raise ValidationError(
                f"Insufficient {leave_type.name} balance: requested {req.days}, available {available}."
            )

    req.save()
    return req


def can_decide(approver: Employee, req: LeaveRequest, user=None) -> bool:
    return can_approve(approver, req.employee, user, perm="leave.change_leaverequest")


@transaction.atomic
def approve_request(req: LeaveRequest, approver: Employee, comment="", user=None) -> LeaveRequest:
    req = LeaveRequest.objects.select_for_update().get(pk=req.pk)
    if not can_decide(approver, req, user):
        raise PermissionDenied("You may not approve this request.")
    if req.status != LeaveRequest.Status.PENDING:
        raise ValidationError("Only pending requests can be approved.")

    lt = req.leave_type
    if lt.tracks_balance and not lt.allow_negative:
        if req.days > ledger_balance(req.employee, lt):
            raise ValidationError("Balance is no longer sufficient to approve this request.")

    req.status = LeaveRequest.Status.APPROVED
    req.decided_by = approver
    req.decided_at = timezone.now()
    req.decision_comment = comment
    req.save()

    if lt.tracks_balance:
        LeaveLedgerEntry.objects.create(
            employee=req.employee, leave_type=lt, kind=LeaveLedgerEntry.Kind.TAKEN,
            days=-req.days, effective_date=req.start_date, request=req,
            note=f"Leave {req.start_date} to {req.end_date}",
            created_by=getattr(approver, "user", None),
        )
    return req


@transaction.atomic
def reject_request(req: LeaveRequest, approver: Employee, comment="", user=None) -> LeaveRequest:
    req = LeaveRequest.objects.select_for_update().get(pk=req.pk)
    if not can_decide(approver, req, user):
        raise PermissionDenied("You may not reject this request.")
    if req.status != LeaveRequest.Status.PENDING:
        raise ValidationError("Only pending requests can be rejected.")
    if not comment:
        raise ValidationError("Please give a reason when rejecting leave.")
    req.status = LeaveRequest.Status.REJECTED
    req.decided_by = approver
    req.decided_at = timezone.now()
    req.decision_comment = comment
    req.save()
    return req


@transaction.atomic
def cancel_request(req: LeaveRequest, by: Employee, user=None) -> LeaveRequest:
    req = LeaveRequest.objects.select_for_update().get(pk=req.pk)
    is_owner = by and by.pk == req.employee_id
    if not (is_owner or can_decide(by, req, user)):
        raise PermissionDenied("You may not cancel this request.")
    if req.status not in (LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED):
        raise ValidationError("This request can no longer be cancelled.")
    if is_owner and req.status == LeaveRequest.Status.APPROVED and req.start_date <= timezone.localdate():
        raise ValidationError("Leave that has already started must be cancelled by your manager or HR.")

    if req.status == LeaveRequest.Status.APPROVED and req.leave_type.tracks_balance:
        LeaveLedgerEntry.objects.create(
            employee=req.employee, leave_type=req.leave_type, kind=LeaveLedgerEntry.Kind.REVERSAL,
            days=req.days, effective_date=req.start_date, request=req,
            note="Cancellation of approved leave", created_by=getattr(by, "user", None),
        )
    req.status = LeaveRequest.Status.CANCELLED
    req.save()
    return req


# ---------------------------------------------------------------- accruals and cycles

def cycle_start_for(employee: Employee, leave_type: LeaveType, as_of: date) -> date:
    """Cycles run from the employee's start date in blocks of cycle_months."""
    start = employee.start_date
    n = 0
    while add_months(start, (n + 1) * leave_type.cycle_months) <= as_of:
        n += 1
    return add_months(start, n * leave_type.cycle_months)


def _active_employees(as_of: date):
    return Employee.objects.filter(start_date__lte=as_of).exclude(end_date__lt=as_of)


@transaction.atomic
def run_monthly_accrual(month_end: date) -> int:
    """
    Credit one month's accrual (entitlement / 12) for MONTHLY leave types.
    Idempotent: a second run for the same month creates nothing.
    An employee is credited for a month once they have worked to its end.
    """
    created = 0
    monthly = (lt for lt in LeaveType.objects.filter(active=True, accrual=LeaveType.Accrual.MONTHLY))
    for lt in monthly:
        amount = (lt.annual_entitlement / 12).quantize(TWO_DP, ROUND_HALF_UP)
        for emp in _active_employees(month_end):
            exists = LeaveLedgerEntry.objects.filter(
                employee=emp, leave_type=lt, kind=LeaveLedgerEntry.Kind.ACCRUAL,
                effective_date=month_end,
            ).exists()
            if exists:
                continue
            LeaveLedgerEntry.objects.create(
                employee=emp, leave_type=lt, kind=LeaveLedgerEntry.Kind.ACCRUAL,
                days=amount, effective_date=month_end,
                note=f"Monthly accrual {month_end:%Y-%m}",
            )
            created += 1
    return created


@transaction.atomic
def run_cycle_rollover(as_of: date) -> int:
    """
    At the start of each employee's cycle:
      - forfeit balance above max_carry_over (if a cap is set), and
      - for UPFRONT types, grant the new cycle's entitlement.
    Idempotent per employee, leave type and cycle start.
    """
    actions = 0
    for lt in LeaveType.objects.filter(active=True).exclude(accrual=LeaveType.Accrual.NONE):
        for emp in _active_employees(as_of):
            cycle_start = cycle_start_for(emp, lt, as_of)
            marker_kind = (
                LeaveLedgerEntry.Kind.GRANT if lt.accrual == LeaveType.Accrual.UPFRONT
                else LeaveLedgerEntry.Kind.FORFEIT
            )
            already = LeaveLedgerEntry.objects.filter(
                employee=emp, leave_type=lt, effective_date=cycle_start,
                kind__in=[LeaveLedgerEntry.Kind.GRANT, LeaveLedgerEntry.Kind.FORFEIT],
            ).exists()
            if already:
                continue

            first_cycle = cycle_start == emp.start_date
            if not first_cycle and lt.max_carry_over is not None:
                # Closing balance of the previous cycle (ignore anything dated on the new cycle's first day).
                prior = ledger_balance(emp, lt, as_of=cycle_start) - _entries_on(emp, lt, cycle_start)
                excess = prior - lt.max_carry_over
                if excess > 0:
                    LeaveLedgerEntry.objects.create(
                        employee=emp, leave_type=lt, kind=LeaveLedgerEntry.Kind.FORFEIT,
                        days=-excess, effective_date=cycle_start,
                        note=f"Carry-over capped at {lt.max_carry_over}",
                    )
                    actions += 1
                elif marker_kind == LeaveLedgerEntry.Kind.FORFEIT:
                    # Record a zero row so the cycle is marked as processed.
                    LeaveLedgerEntry.objects.create(
                        employee=emp, leave_type=lt, kind=LeaveLedgerEntry.Kind.FORFEIT,
                        days=0, effective_date=cycle_start, note="Cycle rollover (nothing forfeited)",
                    )

            if lt.accrual == LeaveType.Accrual.UPFRONT:
                LeaveLedgerEntry.objects.create(
                    employee=emp, leave_type=lt, kind=LeaveLedgerEntry.Kind.GRANT,
                    days=lt.annual_entitlement, effective_date=cycle_start,
                    note=f"Cycle grant from {cycle_start}",
                )
                actions += 1
    return actions


def _entries_on(emp, lt, d) -> Decimal:
    """Ledger movement dated exactly on d (excluded when measuring the closing balance of the previous cycle)."""
    return (
        LeaveLedgerEntry.objects.filter(employee=emp, leave_type=lt, effective_date=d)
        .aggregate(t=Sum("days"))["t"] or Decimal("0")
    )
