from django.contrib import admin

from .models import Project, Timesheet, TimesheetEntry


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "client", "billable", "active"]
    list_filter = ["billable", "active"]
    search_fields = ["code", "name", "client"]


class EntryInline(admin.TabularInline):
    model = TimesheetEntry
    extra = 0


@admin.register(Timesheet)
class TimesheetAdmin(admin.ModelAdmin):
    list_display = ["employee", "week_start", "status", "total_hours", "decided_by"]
    list_filter = ["status"]
    date_hierarchy = "week_start"
    inlines = [EntryInline]
