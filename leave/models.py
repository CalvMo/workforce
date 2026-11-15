from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from people.models import Employee


class LeaveType(models.Model):
    class Accrual(models.TextChoices):
        MONTHLY = "monthly", "Accrues monthly"
        UPFRONT = "upfront", "Granted in full at start of cycle"
        NONE = "none", "No balance tracked (e.g. unpaid)"

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)
    annual_entitlement = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Working days per 12 months (for upfront types: per cycle).",
    )
    accrual = models.CharField(max_length=10, choices=Accrual.choices, default=Accrual.MONTHLY)
    cycle_months = models.PositiveSmallIntegerField(
        default=12, help_text="Length of the leave cycle, e.g. 36 for SA sick leave."
    )
    max_carry_over = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Leave blank for unlimited carry-over.",
    )
    allow_negative = models.BooleanField(default=False)
    requires_attachment = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def tracks_balance(self):
        return self.accrual != self.Accrual.NONE


class LeaveLedgerEntry(models.Model):
    """
    Every change to a leave balance is a ledger row. The balance is the sum
    of the ledger, which gives a full audit trail for free.
    """

    class Kind(models.TextChoices):
        ACCRUAL = "accrual", "Accrual"
        GRANT = "grant", "Cycle grant"
        TAKEN = "taken", "Leave taken"
        REVERSAL = "reversal", "Cancellation reversal"
        ADJUSTMENT = "adjust", "Manual adjustment"
        FORFEIT = "forfeit", "Forfeited (carry-over cap)"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_ledger")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    days = models.DecimalField(max_digits=6, decimal_places=2, help_text="Positive adds, negative deducts.")
    effective_date = models.DateField()
    request = models.ForeignKey(
        "LeaveRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries"
    )
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]
        verbose_name_plural = "leave ledger entries"

    def __str__(self):
        return f"{self.employee} {self.leave_type.code} {self.days:+} ({self.get_kind_display()})"

    @classmethod
    def balance(cls, employee, leave_type, as_of=None) -> Decimal:
        qs = cls.objects.filter(employee=employee, leave_type=leave_type)
        if as_of:
            qs = qs.filter(effective_date__lte=as_of)
        return qs.aggregate(total=Sum("days"))["total"] or Decimal("0")


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    start_half_day = models.BooleanField(default=False, help_text="Only the afternoon of the first day.")
    end_half_day = models.BooleanField(default=False, help_text="Only the morning of the last day.")
    days = models.DecimalField(max_digits=6, decimal_places=2, editable=False, default=0)
    reason = models.TextField(blank=True)
    attachment = models.FileField(upload_to="leave_attachments/", blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="leave_decisions"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.employee} {self.leave_type.code} {self.start_date} to {self.end_date}"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date.")
        if self.start_date == self.end_date and self.start_half_day and self.end_half_day:
            raise ValidationError("For a single half day, tick only one half-day option.")
