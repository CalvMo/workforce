from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from people.models import Employee

MAX_HOURS_PER_DAY = Decimal("16")


class Project(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    client = models.CharField(max_length=150, blank=True)
    billable = models.BooleanField(default=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Timesheet(models.Model):
    """One timesheet per employee per week (Monday to Sunday)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="timesheets")
    week_start = models.DateField(help_text="Always a Monday.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="timesheet_decisions"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "week_start"], name="one_timesheet_per_week")
        ]

    def __str__(self):
        return f"{self.employee} week of {self.week_start}"

    def clean(self):
        if self.week_start and self.week_start.weekday() != 0:
            raise ValidationError("Week start must be a Monday.")

    @property
    def week_end(self):
        return self.week_start + timedelta(days=6)

    @property
    def is_editable(self):
        return self.status in (self.Status.DRAFT, self.Status.REJECTED)

    @property
    def total_hours(self) -> Decimal:
        return self.entries.aggregate(t=Sum("hours"))["t"] or Decimal("0")

    def days(self):
        return [self.week_start + timedelta(days=i) for i in range(7)]


class TimesheetEntry(models.Model):
    timesheet = models.ForeignKey(Timesheet, on_delete=models.CASCADE, related_name="entries")
    project = models.ForeignKey(Project, on_delete=models.PROTECT)
    date = models.DateField()
    hours = models.DecimalField(max_digits=4, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["date", "project__code"]
        verbose_name_plural = "timesheet entries"
        constraints = [
            models.UniqueConstraint(fields=["timesheet", "project", "date"], name="one_entry_per_project_day")
        ]

    def __str__(self):
        return f"{self.date} {self.project.code} {self.hours}h"

    def clean(self):
        ts = self.timesheet
        if self.hours is not None and (self.hours <= 0 or self.hours > MAX_HOURS_PER_DAY):
            raise ValidationError(f"Hours must be between 0 and {MAX_HOURS_PER_DAY}.")
        if ts and self.date and not (ts.week_start <= self.date <= ts.week_end):
            raise ValidationError("Entry date must fall within the timesheet week.")
        if ts and self.date and self.hours:
            others = (
                TimesheetEntry.objects.filter(timesheet=ts, date=self.date)
                .exclude(pk=self.pk)
                .aggregate(t=Sum("hours"))["t"] or Decimal("0")
            )
            if others + self.hours > MAX_HOURS_PER_DAY:
                raise ValidationError(f"Total hours on {self.date} would exceed {MAX_HOURS_PER_DAY}.")
