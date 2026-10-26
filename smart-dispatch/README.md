# Smart Dispatch

Web-based smart dispatch platform for small US carriers (1–5 trucks) and remote
dispatch teams. BIS Project, WIUT, student 00013457.

It manages loads, drivers, trucks and brokers, helps the dispatcher decide which
loads to take with a **load decision and profitability engine**, and gives
managers an **analytics dashboard** of lanes, brokers, empty miles and weekly profit.

![Load offer with live decision engine](docs/screenshots/offer.png)

## Run it

```bash
cd smart-dispatch
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo --reset # anonymised demo data
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in as `dispatcher`, `manager` or `admin`
(password `demo12345`). Run the tests with `python manage.py test tests`.

## How it maps to the PID

| PID requirement | Where |
|---|---|
| Registration, secure login, Dispatcher / Manager / Admin roles | `accounts/` |
| Add, edit, delete, list loads, drivers, trucks (and brokers) | `dispatch/views.py`, `templates/dispatch/` |
| Assign a load to a driver and a truck | `dispatch/services.py` → `assign_load` |
| Status board (Available, Dispatched, In transit, Delivered) | `/board/` |
| Decision engine: real rate per mile incl. empty miles, cost and profit vs cost-per-mile benchmark, hours-of-service check, Accept / Negotiate / Reject | `engine/core.py` |
| Editable cost-per-mile benchmark | `/settings/` (admin) → `engine/models.py` |
| Analytics dashboard: best lanes, best brokers, empty-mile %, weekly gross and profit | `/dashboard/`, `analytics/metrics.py` |
| Reports: loads by status, loads per driver, total miles for a selected week | `/reports/` |
| REST API layer | `POST /api/evaluate/` (used by the live engine panel) |
| Black-box testing | `tests/` (26 tests) |
| Anonymised test data | `python manage.py seed_demo` |

Not built yet: the Telegram bot for driver updates and POD collection (a should-have in the PID).

## Architecture

Layered, as in the PID:

- **Presentation**: Django templates, Bootstrap 5, Chart.js (`templates/`)
- **Application / API**: Django views and a JSON endpoint (`*/views.py`, `config/urls.py`)
- **Business logic**: `engine/core.py` (pure Python, no Django imports, so it is unit-tested on its own) and `dispatch/services.py` (assignment and status rules)
- **Data**: relational models (`*/models.py`), SQLite in development; switch to PostgreSQL in `config/settings.py`

Entities: User, Broker, Driver, Truck, Load, Assignment, CompanySettings.
Broker "average rate per mile" and "number of loads" are calculated from loads
rather than stored, so they can't fall out of date.

## Decision engine rules

With the default settings (cost $2.00/mi, target profit $0.50/mi, 15% band):

1. **Real rate per mile** = rate ÷ (loaded miles + empty miles).
2. **Estimated profit** = rate − total miles × cost per mile.
3. **Hours of service** (simplified FMCSA property-carrying rules): at most 11 h driving per shift,
   a 30-min break after 8 h of driving, 10 h off between shifts, plus loading/unloading time.
   Compared with the pickup-to-delivery window, and optionally with the driver's hours left in the 70-hour cycle.
   The 14-hour window, sleeper-berth splits and the 34-hour restart are not modelled.
4. **Recommendation**:
   - not legally feasible → **Reject**
   - real rate ≥ cost + target profit → **Accept**
   - within 15% of the target rate → **Negotiate**, with a counter-offer rounded up to $25
   - otherwise → **Reject**
5. Warnings for below break-even, empty miles over 20%, and tight schedules (< 2 h slack).

All benchmarks are editable by an admin. They are estimates, not live market rates (see PID limitations).
