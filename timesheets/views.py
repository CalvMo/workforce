from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from people.decorators import employee_required
from people.utils import holiday_name, week_start_for

from . import services
from .models import Project, Timesheet, TimesheetEntry


def _errors(exc):
    return "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)


def _parse_week(value):
    try:
        return week_start_for(date.fromisoformat(value))
    except (TypeError, ValueError):
        return week_start_for(timezone.localdate())


def _grid(ts, extra_project_ids=()):
    entries = {(e.project_id, e.date): e for e in ts.entries.select_related("project")}
    project_ids = {pid for pid, _ in entries} | set(extra_project_ids)
    projects = Project.objects.filter(pk__in=project_ids).order_by("code")
    days = ts.days()
    rows = []
    for p in projects:
        cells = [{"date": d, "entry": entries.get((p.pk, d))} for d in days]
        total = sum((c["entry"].hours for c in cells if c["entry"]), Decimal("0"))
        rows.append({"project": p, "cells": cells, "total": total})
    day_totals = [
        sum((e.hours for (pid, d), e in entries.items() if d == day), Decimal("0")) for day in days
    ]
    headers = [{"date": d, "holiday": holiday_name(d), "weekend": d.weekday() >= 5} for d in days]
    return rows, headers, day_totals


@login_required
@employee_required
def week(request):
    emp = request.employee
    week_start = _parse_week(request.GET.get("week"))
    ts = services.get_or_create_week(emp, week_start)

    if request.method == "POST" and ts.is_editable:
        try:
            with transaction.atomic():
                for key, raw in request.POST.items():
                    if not key.startswith("h_"):
                        continue
                    _, pid, iso = key.split("_", 2)
                    project = get_object_or_404(Project, pk=pid)
                    d = date.fromisoformat(iso)
                    raw = (raw or "").strip()
                    if raw in ("", "0", "0.0", "0.00"):
                        TimesheetEntry.objects.filter(timesheet=ts, project=project, date=d).delete()
                        continue
                    try:
                        hours = Decimal(raw)
                    except InvalidOperation:
                        raise ValidationError(f"'{raw}' is not a valid number of hours.")
                    services.save_entry(ts, project=project, entry_date=d, hours=hours)
            if request.POST.get("submit"):
                services.submit_timesheet(ts, emp)
                messages.success(request, "Timesheet submitted for approval.")
            else:
                messages.success(request, "Timesheet saved.")
            return redirect(f"{request.path}?week={week_start.isoformat()}")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, _errors(exc))

    add_id = request.GET.get("add")
    extra = [int(add_id)] if add_id and add_id.isdigit() else []
    rows, headers, day_totals = _grid(ts, extra)
    used = {r["project"].pk for r in rows}
    return render(request, "timesheets/week.html", {
        "ts": ts,
        "rows": rows,
        "headers": headers,
        "day_totals": day_totals,
        "expected": services.expected_hours(ts),
        "available_projects": Project.objects.filter(active=True).exclude(pk__in=used),
        "prev_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
    })


@login_required
@employee_required
def history(request):
    sheets = request.employee.timesheets.prefetch_related("entries")[:26]
    return render(request, "timesheets/history.html", {"sheets": sheets})


@login_required
@employee_required
def approvals(request):
    emp = request.employee
    qs = Timesheet.objects.filter(status=Timesheet.Status.SUBMITTED).select_related("employee__user")
    if not request.user.has_perm("timesheets.change_timesheet"):
        qs = qs.filter(employee__manager=emp)
    qs = qs.exclude(employee=emp)
    rows = [{"ts": ts, "expected": services.expected_hours(ts)} for ts in qs]
    return render(request, "timesheets/approvals.html", {"rows": rows})


@login_required
@employee_required
def review(request, pk):
    ts = get_object_or_404(Timesheet.objects.select_related("employee__user"), pk=pk)
    if not (ts.employee_id == request.employee.pk or services._can_decide(request.employee, ts, request.user)):
        raise PermissionDenied
    rows, headers, day_totals = _grid(ts)
    return render(request, "timesheets/review.html", {
        "ts": ts, "rows": rows, "headers": headers, "day_totals": day_totals,
        "expected": services.expected_hours(ts),
    })


@login_required
@employee_required
@require_POST
def decide(request, pk):
    ts = get_object_or_404(Timesheet, pk=pk)
    approve = request.POST.get("action") == "approve"
    try:
        services.decide_timesheet(ts, request.employee, approve, request.POST.get("comment", ""), user=request.user)
        messages.success(request, f"Timesheet {'approved' if approve else 'rejected'}.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, _errors(exc))
        return redirect("timesheets:review", pk=pk)
    return redirect("timesheets:approvals")
