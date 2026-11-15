from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from leave.models import LeaveRequest
from leave.services import balance_summary
from timesheets.models import Timesheet
from timesheets.services import expected_hours, get_or_create_week

from .decorators import employee_required


@login_required
@employee_required
def dashboard(request):
    emp = request.employee
    today = timezone.localdate()
    ts = get_or_create_week(emp, today)
    pending_leave = LeaveRequest.objects.filter(employee__manager=emp, status="pending").count()
    pending_ts = Timesheet.objects.filter(employee__manager=emp, status="submitted").count()
    upcoming = emp.leave_requests.filter(end_date__gte=today, status__in=["pending", "approved"]).select_related("leave_type")[:5]
    return render(request, "dashboard.html", {
        "balances": balance_summary(emp),
        "ts": ts,
        "expected": expected_hours(ts),
        "pending_leave": pending_leave,
        "pending_ts": pending_ts,
        "upcoming": upcoming,
    })
