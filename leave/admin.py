from django.contrib import admin

from .models import LeaveLedgerEntry, LeaveRequest, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "annual_entitlement", "accrual", "cycle_months", "max_carry_over", "active"]


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ["employee", "leave_type", "start_date", "end_date", "days", "status", "decided_by"]
    list_filter = ["status", "leave_type"]
    search_fields = ["employee__user__first_name", "employee__user__last_name"]
    readonly_fields = ["days", "decided_by", "decided_at", "status"]
    date_hierarchy = "start_date"


@admin.register(LeaveLedgerEntry)
class LeaveLedgerEntryAdmin(admin.ModelAdmin):
    """Ledger rows are append-only. Corrections are made with new ADJUSTMENT rows."""

    list_display = ["employee", "leave_type", "kind", "days", "effective_date", "note", "created_by"]
    list_filter = ["kind", "leave_type"]
    search_fields = ["employee__user__first_name", "employee__user__last_name", "note"]
    date_hierarchy = "effective_date"

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        super().save_model(request, obj, form, change)
