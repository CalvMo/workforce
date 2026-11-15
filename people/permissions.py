"""Shared approval rules for leave requests and timesheets.

Approval follows the reporting line: an employee's manager may decide on their
items, nobody may decide on their own, and a user holding the app's "change"
permission (for example an HR group) may decide for everyone else.
"""

from .models import Employee


def can_approve(approver: Employee | None, subject: Employee, user=None, *, perm: str) -> bool:
    """May `approver` (backed by `user`) decide on an item belonging to `subject`?"""
    if approver and approver.pk == subject.pk:
        return False  # nobody approves their own items
    if approver and approver.manages(subject):
        return True
    return bool(user and user.has_perm(perm))


def approvable_by(qs, approver: Employee, user, *, perm: str):
    """Narrow a queryset of items (with an `employee` field) to those `approver` may decide on."""
    if not user.has_perm(perm):
        qs = qs.filter(employee__manager=approver)
    return qs.exclude(employee=approver)
