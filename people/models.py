from django.conf import settings
from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    """Employment details linked one-to-one with a Django user account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee"
    )
    employee_number = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, blank=True, related_name="employees"
    )
    manager = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="direct_reports"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    standard_hours_per_day = models.DecimalField(max_digits=4, decimal_places=2, default=8)

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def is_manager(self):
        return self.direct_reports.exists()

    def manages(self, other: "Employee") -> bool:
        return other.manager_id == self.pk
