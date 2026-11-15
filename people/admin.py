from django.contrib import admin

from .models import Department, Employee


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["__str__", "employee_number", "department", "manager", "start_date", "end_date"]
    list_filter = ["department"]
    search_fields = ["employee_number", "user__first_name", "user__last_name", "user__email"]
    autocomplete_fields = ["manager", "department", "user"]
