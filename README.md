# WorkPulse

WorkPulse is a construction site-operations app for managers and team leads. Teams record how much they built each day, on which project and which work type. WorkPulse turns those daily amounts into progress, forecast finish dates, team output and expected material use.

It also manages the people: schedules, days off, the days and hours each worker worked, and their pay. There is no clock-in or clock-out.

Each company sees only its own teams, projects, stock and daily work.

## Features

**Projects and work**
- Projects with planned work per work type (for example, Facade plaster, 800 m²)
- A task board and timeline, with comments and an activity feed
- A daily sheet: one row per day, one column per work type, team or note
- Board, sheet and daily log all write the same daily reports, so the numbers always agree

**Teams and people**
- Teams, workers and worker types, with a history of who was in which team and when
- A page for each worker and each team, with hire and leaving dates
- A Planning board showing which team works where, day by day, with warnings for double bookings and how many people are off

**Schedules and days off**
- Schedules as hours per weekday (for example Mon–Fri 8 h, Sat 5 h), for everyone or per worker, changed from a date so past days keep their hours
- A holiday calendar
- Days off (vacation, sick, unpaid, absent and your own kinds), with half days
  - Team leads ask, managers approve
  - Yearly vacation balances

**Hours and timesheet**
- Ticking the crew in the daily log records hours too, pre-filled from each worker's schedule
- A timesheet of workers × days: type hours into a cell, or open a day for several projects, yard/office work or a day off
- Days worked, hours, extra hours, days off and missing days per worker, per week and per period
- Pay groups settle workers on their own cycle (weekly, every two weeks or monthly)
  - A manager approves each group's hours per period, which locks them

**Pay (owner only)**
- Day rates or fixed weekly/monthly amounts, with a history of rate changes
- Pay per period, calculated from the approved timesheet:
  - extra hours (optional multiplier), paid days off and holidays
  - bonuses and deductions
- Cash advances on any day, taken off the next payment, and a running "owed" balance per worker
- Approve pay to freeze it, mark people paid, print payslips, and export a CSV for the accountant (no tax calculation)

**Daily log**
- One page per project per day: work done, crew on site, issues, material used, notes, weather and photos
- A manager approves the day and it locks; reopening unlocks it
- A list of teams that haven't reported yet today

**Progress and performance**
- Percent done, weekly output and output per worker-day for each work type
- A forecast finish date from the last 10 working days of output
- An on track / behind / stalled flag per work type and per project
- Each team's share of the work and its weekly output

**Stock**
- Depot and site locations, lots with expiry dates, receive / transfer / use / adjust movements
- Material used on site is linked to the work type it was used for
- Material per unit of work (for example, 1.4 kg adhesive per m²), with expected vs actual use and shortages
- Minimum stock levels and a "running low" list
- Material requests from site that a manager sends from the depot, in full or in part

**Files**
- Photos (JPEG, PNG, WebP) and PDFs up to 15 MB on daily logs and other records
- Downloads only through a check that the user belongs to that company

## Roles

| Role | Can |
|------|-----|
| Owner | Everything, including inviting people. The only role that sees pay. |
| Manager | Everything except invites and pay: approve days, plan teams, set up work types and stock, send material, set up schedules and holidays, enter hours, approve days off and each period's hours |
| Team lead | See the projects their teams work on; fill reports, crew and hours, issues, photos and material used for their teams; request material; ask for days off for their team; read their team's timesheet |

## Tech stack

| Part | Technology |
|------|------------|
| Backend | Python 3.12, Django 6, Django REST Framework |
| Database | PostgreSQL 16 |
| Frontend | React 19 (Create React App), React Router 7 |
| Auth | Django sessions with CSRF (no JWT) |
| Dev setup | Docker Compose |

## Getting started

You need [Docker](https://www.docker.com/) with Docker Compose.

1. Start the app:

   ```bash
   docker compose up --build
   ```

   The backend runs its database migrations on start.

2. In a second terminal, load the demo data:

   ```bash
   docker compose exec backend python manage.py seed_demo
   ```

   This creates the company **River Co** with teams, workers, three projects, reports, crew, daily logs, stock and a material request. It also adds:
   - schedules, holidays and days off
   - October's hours, in a weekly pay group and a monthly one
   - pay rates, paid weeks, an advance and a bonus

   The week of 26 Oct and the monthly October pay are left open to try. It is safe to run again. Use `--company "Other Co"` to seed a different company.

3. Open <http://localhost:3001> and log in.

### Demo accounts

All demo accounts use the password `Manager-pass-123`.

| Email | Role |
|-------|------|
| `manager@example.com` | Owner (the only account that sees Pay) |
| `office@example.com` | Manager |
| `mira@example.com` | Team lead |
| `arben@example.com` | Team lead |
| `lira@example.com` | Team lead |

### Ports

| Service | URL |
|---------|-----|
| Frontend | <http://localhost:3001> |
| Backend API | <http://localhost:8001/api/> |
| Django admin | <http://localhost:8001/admin/> |
| PostgreSQL | `localhost:5433` (database `grind_db`, user `grind_user`) |

The frontend sends `/api` requests to the backend through its dev proxy, so the browser only talks to port 3001.

## Running tests

Backend tests:

```bash
docker compose exec backend python manage.py test
```

Check that the frontend builds:

```bash
docker compose exec frontend npm run build
```

## Project structure

```text
workpulse/
├── docker-compose.yml          db, backend and frontend containers
├── backend/                    Django project
│   ├── config/                 settings, URLs (every app under /api/), pagination
│   ├── accounts/               login, logout, register, /api/auth/me/
│   ├── companies/              companies, memberships and roles
│   │   ├── permissions.py      who may do what: members, leads, owner-only pay (CanSeePay)
│   │   ├── viewsets.py         CompanyScopedViewSet, the base of almost every API view
│   │   ├── testing.py          auth_client and other test helpers
│   │   └── management/commands/seed_demo.py
│   ├── workforce/              teams, workers, employment dates, team membership history
│   │   └── services.py         active_on (does a date range cover a day?), move_worker
│   ├── operations/             projects, catalogs, scopes, site reports, sheet, team placements
│   │   └── progress.py         pace, forecasts, team performance, company overview
│   ├── work/                   tasks, board statuses and phases, comments
│   ├── sitelog/                daily logs, issues, crew attendance and hours
│   │   └── services.py         ensure_day_open (the day lock), set_attendance (the one crew write path)
│   ├── timesheets/             schedules, holidays, days off, other work, pay groups, periods
│   │   ├── schedule.py         WorkCalendar: scheduled hours, expected hours, a full day
│   │   ├── leave.py            day-off requests, decisions, yearly balances
│   │   ├── periods.py          pay group cycles, approving and reopening hours
│   │   ├── locks.py            the period lock (ensure_worker_open, ensure_company_open)
│   │   └── sheet.py            the timesheet: worker × day, totals, weeks
│   ├── payroll/                pay settings, rates, bonuses, payments, pay runs, payslips (owner only)
│   │   ├── calc.py             the pay rules, as pure functions over timesheet rows
│   │   └── services.py         owed balances, approve and reopen pay, CSV export
│   ├── inventory/              stock, material norms, stock levels, material requests
│   │   └── usage.py            expected vs actual material, shortages
│   └── core/                   activity feed, file attachments
└── frontend/                   React app
    └── src/
        ├── App.js              all routes
        ├── setupProxy.js       forwards /api to the backend in development
        ├── api/                client.js (api, apiList, apiUpload) and auth.js
        ├── context/            AuthContext (user, role) and ThemeContext (light/dark)
        ├── pages/              one screen per route
        └── components/         Layout (sidebar), ui.js (shared styles and fields), charts,
                                board, sheet, day log, timesheet day panel, pay, stock panels
```

Each backend app follows the same pattern: `models.py` → `services.py` (business rules) → `serializers.py` → `views.py` (thin) → `tests.py`.

## How it works

The core record is the **site report**: *this team, on this project, on this day, did this amount of this work type*. Every other number is calculated from saved records instead of being stored:

- progress = planned amount − sum of reports
- output per worker-day = reports ÷ crew attendance
- forecast finish = remaining ÷ recent daily output
- expected material = work done × material per unit
- hours worked = crew hours + other work; extra hours = hours above the schedule
- pay = days or shares of a fixed amount × the rate, from the approved timesheet

There are three locks, each building on the one before:
1. Once a manager approves a project day, nothing for that day can change until it is reopened.
2. Once a manager approves a pay group's period, its hours, days off and schedules are locked.
3. Once the owner approves pay for that period, the hours can't be reopened until the pay is reopened.

Approved pay lines are the only calculated numbers that are stored, so later rate changes can't rewrite what was paid.

### Login and companies

- Login uses Django sessions with CSRF; there are no tokens. `POST /api/auth/login/` sets a `sessionid` cookie, and writes also send an `X-CSRFToken` header copied from the `csrftoken` cookie.
- The session also stores which company you're working in. `CompanyScopedViewSet` filters every list to that company, and narrows it further for team leads.
- Because of the cookies, the browser must reach the API on the same site as the app: in development through the proxy on port 3001, in production by serving `/api` from the same domain.

For the full walkthrough of the data model, permissions and code conventions, see [project explained](project%20explained).

## Status and roadmap

Phase 1 (site operations core) and **People & pay** (schedules, days off, hours, timesheet, pay) are merged. People & pay brought worker rates forward from the money phase. Next phases:

- **Phase 2, planning and detail:** areas (building, floor, room), task dependencies, Gantt, templates, notifications
- **Phase 3, quality, safety and documents:** inspections, punch lists, incidents, drawings, RFIs
- **Phase 4, money (optional):** budgets, labour and material cost per project, purchase orders, invoices from measured work
- **Phase 5, clients and mobile:** client portal, subcontractor access, offline mobile app
- **Phase 6, insights:** portfolio dashboard, exports, weekly reports, AI summaries of daily logs

## Not production-ready yet

This is a development setup:
- `DEBUG` is on.
- The Django secret key and database password are in the repository.
- The servers are Django's `runserver` and the Create React App dev server.

Before deploying, move secrets to environment variables, turn `DEBUG` off, and serve the backend with a production server such as gunicorn.
