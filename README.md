# Workforce: timesheets and leave (Django starter)

A working starter project for weekly timesheets and leave management, with South African public holidays and BCEA-style leave defaults built in.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo         # demo leave types, projects and users
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in as `staff1`, `staff2`, `manager` or `admin` (password `demo12345`). The admin site is at `/admin/`.

Run the tests with `python manage.py test tests`.

## What is included

**Leave**
- Leave types with their own entitlement, accrual method (monthly, upfront per cycle, or untracked), cycle length and carry-over cap.
- Requests count working days only, excluding weekends and SA public holidays (including Sunday holidays observed on Monday and one-off days such as election days), with half-day support.
- Balance checks that reserve pending requests, overlap detection, and a supporting-document rule for sick leave longer than two days.
- Manager approval and rejection (a reason is required to reject), cancellation with automatic balance reversal, and a team leave view.
- A leave ledger: every accrual, grant, deduction, reversal, adjustment and forfeit is a row, so balances are fully auditable. Ledger rows cannot be edited or deleted in the admin; corrections are new adjustment rows.

**Timesheets**
- One timesheet per employee per week (Monday to Sunday), entered as a project-by-day grid.
- Validation for hours per entry, a 16-hour daily cap across projects, and dates within the week.
- Expected hours per week that account for public holidays and approved leave.
- Draft, submitted, approved and rejected states. Submitted timesheets are locked, and rejected ones reopen for correction.

**Permissions**
- Approvals follow the reporting line (an employee's `manager`). Nobody can approve their own leave or timesheet.
- Users with the `leave.change_leaverequest` or `timesheets.change_timesheet` permission (for example an HR group) can approve for everyone.

## Scheduled jobs

Run this once a day (cron, Windows Task Scheduler, or Celery beat later):

```bash
python manage.py run_leave_jobs
```

It credits monthly accruals for the last completed month and processes cycle rollovers (upfront grants and carry-over forfeits). Both steps are idempotent, so running it more than once does no harm. Use `--as-of YYYY-MM-DD` to back-fill.

## Project layout

```
config/        settings and URL routing
people/        Department, Employee, working-day and holiday utilities, demo seed command
leave/         LeaveType, LeaveRequest, LeaveLedgerEntry, services.py (all leave rules)
timesheets/    Project, Timesheet, TimesheetEntry, services.py (all timesheet rules)
templates/     server-rendered pages
tests/         unit and view tests
```

Business rules live in each app's `services.py`, so the views stay thin and the rules are easy to test or reuse from an API later.

## Leave defaults in the demo data

| Type | Entitlement | Method | Cycle | Carry-over |
|---|---|---|---|---|
| Annual | 15 days | 1.25 days per month | 12 months | up to 5 days |
| Sick | 30 days | granted upfront | 36 months | none |
| Family responsibility | 3 days | granted upfront | 12 months | none |
| Study | 5 days | granted upfront | 12 months | none |
| Unpaid | n/a | not tracked | n/a | n/a |

These follow common BCEA minimums for a five-day week, but company policy and employment contracts vary. Check them with HR before going live. Two simplifications to be aware of: the BCEA allows one day of sick leave per 26 days worked during the first six months of employment (the starter grants the full cycle upfront), and annual leave carry-over rules are often set by company policy rather than law.

## Suggested next steps

1. Move to PostgreSQL and set `SECRET_KEY`, `DEBUG` and `ALLOWED_HOSTS` from environment variables before deploying.
2. Email or Teams notifications on submit, approve and reject (Django signals or a task queue).
3. Payroll and utilisation exports to Excel or CSV.
4. Microsoft 365 single sign-on (for example with `django-allauth` or `mozilla-django-oidc`).
5. A REST API with Django REST Framework if you want a mobile app or a separate front end.
6. Pro-rata entitlements for part-time staff and leave encashment on termination.
