from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from people.decorators import employee_required
from people.permissions import approvable_by

from . import services
from .forms import DecisionForm, LeaveRequestForm
from .models import LeaveLedgerEntry, LeaveRequest


def _errors(exc):
    return "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)


@login_required
@employee_required
def my_leave(request):
    emp = request.employee
    form = LeaveRequestForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit_request(
                emp,
                leave_type=form.cleaned_data["leave_type"],
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                start_half_day=form.cleaned_data["start_half_day"],
                end_half_day=form.cleaned_data["end_half_day"],
                reason=form.cleaned_data["reason"],
                attachment=form.cleaned_data.get("attachment"),
            )
        except ValidationError as exc:
            form.add_error(None, _errors(exc))
        else:
            messages.success(request, "Leave request submitted.")
            return redirect("leave:mine")
    return render(request, "leave/my_leave.html", {
        "form": form,
        "balances": services.balance_summary(emp),
        "requests": emp.leave_requests.select_related("leave_type", "decided_by__user")[:50],
        "ledger": LeaveLedgerEntry.objects.filter(employee=emp).select_related("leave_type")[:30],
    })


@login_required
@employee_required
@require_POST
def cancel(request, pk):
    req = get_object_or_404(LeaveRequest, pk=pk)
    try:
        services.cancel_request(req, request.employee, user=request.user)
        messages.success(request, "Leave request cancelled.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, _errors(exc))
    return redirect(request.POST.get("next") or "leave:mine")


@login_required
@employee_required
def approvals(request):
    emp = request.employee
    qs = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).select_related(
        "employee__user", "leave_type"
    )
    qs = approvable_by(qs, emp, request.user, perm="leave.change_leaverequest")
    rows = [{"req": r, "available": services.available_balance(r.employee, r.leave_type)
             if r.leave_type.tracks_balance else None} for r in qs]
    return render(request, "leave/approvals.html", {"rows": rows, "form": DecisionForm()})


@login_required
@employee_required
@require_POST
def decide(request, pk):
    req = get_object_or_404(LeaveRequest, pk=pk)
    form = DecisionForm(request.POST)
    form.is_valid()
    comment = form.cleaned_data.get("comment", "")
    try:
        if request.POST.get("action") == "approve":
            services.approve_request(req, request.employee, comment, user=request.user)
            messages.success(request, f"Approved leave for {req.employee}.")
        else:
            services.reject_request(req, request.employee, comment, user=request.user)
            messages.success(request, f"Rejected leave for {req.employee}.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, _errors(exc))
    return redirect("leave:approvals")


@login_required
@employee_required
def team_calendar(request):
    """Approved and pending leave for the user's team (their reports, peers and themselves)."""
    emp = request.employee
    team_filter = Q(employee=emp) | Q(employee__manager=emp)
    if emp.manager_id:
        team_filter |= Q(employee__manager_id=emp.manager_id)
    qs = (LeaveRequest.objects.filter(team_filter, status__in=["pending", "approved"])
          .select_related("employee__user", "leave_type").order_by("start_date"))
    return render(request, "leave/team.html", {"requests": qs})
