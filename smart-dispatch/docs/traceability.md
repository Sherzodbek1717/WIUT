# Requirements traceability and evaluation

How each PID objective and requirement is met, where it is in the code, and the test evidence.
Status: **Met**, **Partly met** or **Student task** (work the student must do; the software cannot).

## Objectives

| PID objective | Status | Evidence |
|---|---|---|
| Analyse dispatch methods, TMS products and load boards; identify the gap | Student task | Literature/competitor review in the report. The as-is vs to-be process diagrams in [design.md](design.md) support it |
| Primary research: survey of 40+ dispatchers and small fleet owners, plus interviews | Student task | Questionnaire and interview guide ready in [survey.md](survey.md); results go in the report |
| Design interface, database and architecture (prototypes, ERD) | Met | [design.md](design.md): ERD generated from the real models, architecture, use cases, processes, sequence diagram; screenshots in `docs/screenshots`. Figma prototypes: student task if the module requires Figma files specifically |
| Develop the TMS core (record loads, drivers, trucks; assign; track status) | Met | FR2–FR5, FR7 below |
| Develop the decision and profitability engine | Met | FR6 below; `engine/core.py`; TC-06, TC-11–TC-23 |
| Develop the analytics dashboard (best lanes, best brokers, empty-mile %, weekly profit) | Met | FR8; `analytics/`; TC-08 |
| Plan and track with a Gantt chart | Student task | Keep the Gantt chart updated with the supervisor; Git history (`git log`) shows real progress dates |
| Black-box testing and evaluation against objectives | Met (testing) / Student task (evaluation write-up) | [testing.md](testing.md), [test-results.md](test-results.md): 87 automated tests passing; manual checks M-01–M-05 |

## Scope items

| In-scope item (PID) | Status | Where | Tests |
|---|---|---|---|
| Registration and secure login with dispatcher and manager roles | Met (plus broker and admin roles) | `accounts/` | TC-01, TC-35–TC-38 |
| Manage loads, drivers, trucks (add, edit, delete, list) | Met | `dispatch/views.py` | TC-02, TC-03 |
| Assign a load to a driver and a truck | Met | `dispatch/services.py` | TC-04 |
| Status board (Available, Dispatched, In transit, Delivered) | Met | `/board/` | TC-07 |
| Decision engine (real rate/mile incl. empty miles, cost/profit vs benchmark, HOS, Accept/Negotiate/Reject) | Met | `engine/core.py`, `/settings/` for the benchmark | TC-06, TC-11–TC-23 |
| Analytics dashboard (best lanes, best brokers, empty-mile %, weekly gross and profit) | Met | `/dashboard/` | TC-08 |
| Reports (loads by status, per driver, total miles for a selected week) | Met | `/reports/` | TC-09 |
| Telegram bot for driver status updates and POD (should-have) | Met | `telegram_bot/` | `tests/test_telegram_bot.py`, M-02 |

## Functional requirements

| FR | Requirement | Status | Test |
|---|---|---|---|
| FR1 | Register and log in securely | Met | TC-01 |
| FR2 | Add, edit, delete and list loads | Met | TC-02 |
| FR3 | Add, edit and list drivers and trucks | Met | TC-03 |
| FR4 | Assign a load to a driver and a truck | Met | TC-04 |
| FR5 | Update the status of a load | Met (web and Telegram) | TC-05 |
| FR6 | Enter a load offer, get profitability and Accept/Negotiate/Reject | Met (manual offer and every load-board result) | TC-06, TC-12–TC-15 |
| FR7 | Status board of current loads by stage | Met | TC-07 |
| FR8 | Manager dashboard: best lanes, best brokers, weekly profit | Met | TC-08 |
| FR9 | Manager reports: loads by status, loads per driver | Met | TC-09 |
| FR10 | Administrator manages user accounts | Met | TC-10 |

## Architecture (PID "System Architecture")

| PID layer | Status | Where |
|---|---|---|
| Presentation: HTML + Bootstrap, charts | Met | `templates/`, Bootstrap 5, Chart.js |
| Application/API: REST API between front end and server | Met | [api.md](api.md): `/api/evaluate/` (used live by the load-offer page), `/api/loadboard/search/`, `/api/loads/` |
| Business logic: engine, assignment, reporting | Met | `engine/core.py`, `dispatch/services.py`, `analytics/metrics.py`, `loadboard/search.py` |
| Data: relational DB of loads, drivers, trucks, brokers, assignments, users | Met | SQLite (dev) / PostgreSQL-ready; [design.md](design.md) ERD |
| Python + Django, GitHub version control | Met | Django 5.2; GitHub repository |

## Out of scope (kept out, as the PID says)

| Out of scope | Status |
|---|---|
| External load boards (DAT, Truckstop), ELD, GPS | Not integrated. The load board is the platform's own marketplace |
| Payments, invoicing, accounting | Not built |
| Automated reading of rate confirmations (AI/OCR) | Not built |
| Mobile-native app | Not built; the website is responsive and drivers use Telegram |

## Beyond the PID (scope extension; agree it with the supervisor)

| Addition | Why it adds value |
|---|---|
| Load board: Search Loads/Trucks with DH-O/DH-D radius, lane rate, decision engine on every result | Applies the engine where dispatchers actually choose loads (DAT One-style) |
| AI Co-Pilot: AI-written broker emails, bulk email, Mailbox | Cuts repetitive typing (Neblo-style) |
| Call Assistant with target and walk-away rates, call log | Supports negotiation (Numeo-style) without an autonomous voice agent |
| Broker directory with lanes and average rates | Helps choose brokers (Numeo-style) |

## Known limitations (for the evaluation chapter)

1. Distances are straight-line × 1.17 road factor, not true road miles (no paid routing API).
2. The hours-of-service check is simplified (no 14-hour window, sleeper berth or 34-hour restart).
3. Demo marketplace data is invented; real loads would need DAT/Truckstop partner APIs.
4. Profit uses one cost-per-mile benchmark for the whole fleet, at today's setting (past loads are re-priced if it changes).
5. Single company per installation (no multi-tenant separation between carriers).
6. AI features need a paid Anthropic API key; without it the system uses templates.
7. Sean AI does not place phone calls itself; an AI voice agent needs telephony services and legal disclosure.
8. Usability is untested with real users until manual check M-05 is done.
