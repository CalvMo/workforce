from functools import wraps

from django.shortcuts import render

from .models import Employee


def employee_required(view):
    """Attach request.employee, or show a friendly page if the user has no employee record."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            request.employee = request.user.employee
        except Employee.DoesNotExist:
            return render(request, "no_employee.html", status=403)
        return view(request, *args, **kwargs)

    return wrapper
