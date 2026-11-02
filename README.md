# WorkPulse

WorkPulse is a construction site-operations app for managers and team leads. Teams record how much they built each day, on which project and which work type. WorkPulse turns those daily amounts into progress, forecast finish dates, team output and expected material use.

Each company sees only its own teams, projects, stock and daily work.

## Features

**Projects and work**
- Projects with planned work per work type (for example, Facade plaster, 800 m²)
- A task board and timeline, with comments and an activity feed
- A daily sheet: one row per day, one column per work type, team or note
- Board, sheet and daily log all write the same daily reports, so the numbers always agree

**Teams and people**
- Teams, workers and worker types, with a history of who was in which team and when
- A page for each worker and each team
- A Planning board showing which team works where, day by day, with warnings for double bookings

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
| Owner | Everything, including inviting people |
| Manager | Everything except invites: approve days, plan teams, set up work types and stock, send material |
| Team lead | See the projects their teams work on; fill reports, crew, issues, photos and material used for their teams; request material |

## Tech stack

| Part | Technology |
|------|------------|
| Backend | Python 3.12, Django 5, Django REST Framework |
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

   This creates the company **River Co** with teams, workers, three projects, reports, crew, daily logs, stock and a material request. It is safe to run again. Use `--company "Other Co"` to seed a different company.

3. Open <http://localhost:3001> and log in.

### Demo accounts

All demo accounts use the password `Manager-pass-123`.

| Email | Role |
|-------|------|
| `manager@example.com` | Owner |
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
├── docker-compose.yml
├── backend/                Django project
│   ├── config/             settings, URLs, pagination
│   ├── accounts/           login, registration, session, /api/auth/me/
│   ├── companies/          companies, memberships, roles, seed_demo command
│   ├── workforce/          teams, workers, team membership history
│   ├── operations/         projects, work types, scopes, daily reports, sheet, progress
│   ├── work/               tasks, board statuses and phases
│   ├── sitelog/            daily logs, crew attendance, issues, day approval
│   ├── inventory/          stock, material norms, stock levels, material requests
│   └── core/               activity feed, file attachments
└── frontend/               React app
    └── src/
        ├── pages/          one screen per route
        ├── components/     board, sheet, calendar, day log, charts, stock panels
        ├── context/        auth and theme
        └── api/            fetch wrapper (session cookies + CSRF)
```

Each backend app follows the same pattern: `models.py` → `services.py` (business rules) → `serializers.py` → `views.py` (thin) → `tests.py`.

## How it works

The core record is the **site report**: *this team, on this project, on this day, did this amount of this work type*. Every other number is calculated from saved records instead of being stored:

- progress = planned amount − sum of reports
- output per worker-day = reports ÷ crew attendance
- forecast finish = remaining ÷ recent daily output
- expected material = work done × material per unit

Once a manager approves a day, nothing for that project day can change until it is reopened.

For the full walkthrough of the data model, permissions and code conventions, see [project explained](project%20explained).

## Status and roadmap

Phase 1 (site operations core) is built on the `phase1-site-ops` branch. Next phases:

- **Phase 2, planning and detail:** areas (building, floor, room), task dependencies, Gantt, templates, notifications
- **Phase 3, quality, safety and documents:** inspections, punch lists, incidents, drawings, RFIs
- **Phase 4, money (optional):** rates, budgets, cost tracking, purchase orders, invoices from measured work
- **Phase 5, clients and mobile:** client portal, subcontractor access, offline mobile app
- **Phase 6, insights:** portfolio dashboard, exports, weekly reports, AI summaries of daily logs

## Not production-ready yet

This is a development setup:
- `DEBUG` is on.
- The Django secret key and database password are in the repository.
- The servers are Django's `runserver` and the Create React App dev server.

Before deploying, move secrets to environment variables, turn `DEBUG` off, and serve the backend with a production server such as gunicorn.
