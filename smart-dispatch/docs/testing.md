# Black-box test plan

PID objective: *"To test the system using black-box testing and evaluate it against the project objectives."*

Each test below treats the system as a black box: it gives inputs through the web pages (or the
engine's public function) and checks only the visible output, never the internal code paths. Every
case is automated, so it can be re-run at any time; the latest real results are in
[test-results.md](test-results.md) (regenerate with `python scripts/test_report.py`).

## 1. Functional requirements (FR1–FR10)

Automated in `tests/test_requirements.py`.

| ID | Requirement (PID) | Steps and input | Expected result | Result |
|---|---|---|---|---|
| TC-01 | FR1 Register and log in securely | Register as dispatcher; log in with wrong then right password; register with password `123` | Account created with chosen role; wrong password refused; right password logs in; weak password rejected ("too short") | Pass |
| TC-02 | FR2 Add, edit, delete, list loads | Create load ref `NEW1`; change rate to 1,450; open list; delete; try delivery before pickup | Load saved, rate updated, shown in list, deleted; invalid dates rejected with a message | Pass |
| TC-03 | FR3 Add, edit, list drivers and trucks | Add driver Ali Karimov; edit phone and status; add truck 900 | Changes saved and shown in the Drivers and Trucks lists | Pass |
| TC-04 | FR4 Assign load to driver and truck | Assign available driver and truck to an available load | Load becomes *Dispatched* with that driver and truck | Pass |
| TC-05 | FR5 Update load status | Dispatched load → In transit → Delivered | Load *Delivered*; driver and truck available again | Pass |
| TC-06 | FR6 Load offer gives profit and recommendation | Offer $2,000, 450 loaded + 30 empty miles, 24 h window, press Evaluate | 480 total miles, $4.17 real rate/mile, $1,040 profit at $2.00/mi cost, **Accept** | Pass |
| TC-07 | FR7 Status board by stage | Open the board | Four columns Available, Dispatched, In transit, Delivered; the load in Available | Pass |
| TC-08 | FR8 Manager dashboard | Manager opens dashboard (4 weeks) with one $2,500 load of 800 miles (20 empty) | 1 load, $2,500 gross, $900 profit, 2.5% empty miles, broker and lane listed, chart totals $2,500 | Pass |
| TC-09 | FR9 Manager reports | Assign the load, then open this week's report | 1 load Dispatched; driver Ali K: 1 load, 800 miles; week total 800 miles | Pass |
| TC-10 | FR10 Admin manages users | Admin changes a user's role to manager and deactivates them; a dispatcher opens Users | Role and active flag saved; dispatcher gets *403 No access* | Pass |

## 2. Decision engine: boundary values and equivalence classes

Automated in `tests/test_engine.py`. Settings: cost $2.00/mi, target profit $0.50/mi (target $2.50/mi),
negotiation band 15%, average speed 50 mph, 4 h loading/unloading.

| ID | Class / boundary | Input | Expected | Result |
|---|---|---|---|---|
| TC-11 | Real rate includes empty miles | $2,500, 900 loaded + 100 empty | Posted $2.78/mi, real $2.50/mi, cost $2,000, profit $500, 10% empty | Pass |
| TC-12 | Boundary: exactly at target | $2,500 for 1,000 mi | **Accept** | Pass |
| TC-13 | Inside negotiation band | $2,200 for 1,000 mi (12% under target) | **Negotiate**, counter-offer $2,500 | Pass |
| TC-14 | Below the band, below break-even | $1,500 for 1,000 mi | **Reject**, warning "Below break-even" | Pass |
| TC-15 | Deadhead turns a good rate into Negotiate | $2,900, 1,000 loaded + 300 empty | Real $2.23/mi → **Negotiate**, empty-miles warning (23% > 20%) | Pass |
| TC-16 | Counter-offer rounding | Target $1,025 | Rounded to $25 steps: $1,025 | Pass |
| TC-17 | HOS: one shift | 8 h driving + 4 h dock | 12 h minimum transit | Pass |
| TC-18 | HOS: two shifts | 22 h driving | 33 h (2 × 11 h + 2 × 30 min breaks + 10 h rest) | Pass |
| TC-19 | HOS infeasible beats a great rate | $5,000, 1,100 mi, 24 h window | **Reject** (needs 37 h) | Pass |
| TC-20 | HOS tight window | 400 mi, 13 h window (needs 12 h) | Accept with "tight" warning | Pass |
| TC-21 | Not enough 70-hour cycle hours | 10 h left, needs 24 h | **Reject** | Pass |
| TC-22 | No dates given | No pickup/delivery | HOS "unknown" + warning | Pass |
| TC-23 | Invalid input | 0 loaded miles | Error, no result | Pass |

## 3. Load board and AI Co-Pilot (selected)

Automated in `tests/test_loadboard.py` and `tests/test_copilot.py`.

| ID | Feature | Input | Expected | Result |
|---|---|---|---|---|
| TC-24 | DH-O radius | Search Dallas, DH-O 100 | Fort Worth load (~35 mi) found; Houston (~240 mi) not; Houston found at DH-O 300 | Pass |
| TC-25 | Filters | Destination Memphis; equipment Van | Only matching loads | Pass |
| TC-26 | Minimum $/mile | Min $2.00 | Cheap load and "call for rate" loads excluded | Pass |
| TC-27 | Hidden loads | Past pickup date; already booked | Not shown | Pass |
| TC-28 | Book load | Book at $2,600 with 12 mi DH-O | Load created in TMS with that rate and deadhead; posting marked booked; second booking refused | Pass |
| TC-29 | Lane rate accuracy | Two Dallas→Atlanta loads | Average $/mi exact (catches a real SQLite integer-division bug found during testing) | Pass |
| TC-30 | Email broker | Send from a load | Email delivered, reply-to set to dispatcher, saved in Mailbox | Pass |
| TC-31 | Bulk email | 2 loads, one without email | 1 email sent, other marked "phone only" | Pass |
| TC-32 | AI request | Fake Claude client | Model `claude-opus-5-5`, structured JSON output, fallback enabled; refusal, bad JSON or network error → template used | Pass |
| TC-33 | Call Assistant | Open, log "Got a rate $2,700" | Target and walk-away shown; call saved; $2,700 pre-filled for booking | Pass |
| TC-34 | Broker directory stats | Filter by state TX | Correct load count and average (no double counting) | Pass |

## 4. Security and roles (non-functional)

| ID | Check | Expected | Result |
|---|---|---|---|
| TC-35 | Not logged in opens a page | Redirect to login | Pass |
| TC-36 | Broker opens carrier pages (board, loads, drivers, search, directory, API) | 403 No access | Pass |
| TC-37 | Manager tries to create a load or email a broker | 403 | Pass |
| TC-38 | Registration tries to pick the Admin role | Refused | Pass |
| TC-39 | Another Telegram chat presses a driver's status button | Refused, load unchanged | Pass |
| TC-40 | POD files opened without login | Redirect to login | Pass |
| TC-41 | Deployment check (`DJANGO_DEBUG=0 python manage.py check --deploy`) | No issues (HTTPS-only cookies, HSTS, SSL redirect) | Pass (run manually) |

## 5. Manual checks (for the report and demo video)

These need a person and a browser; record the date and outcome when you do them.

| ID | Check | How |
|---|---|---|
| M-01 | Works on a phone | Open the site on a phone (or Chrome DevTools at 390 px): sidebar becomes a menu, tables scroll |
| M-02 | Telegram bot end to end | Create a link code, link your phone, dispatch a load, tap In transit and Delivered, send a POD photo |
| M-03 | Real email | Configure Gmail (README), send one email to yourself from a load |
| M-04 | AI writing | Set `ANTHROPIC_API_KEY`, press Write with AI on an email and a call script |
| M-05 | Usability | Ask 3–5 dispatchers to find and book a load; time it and note problems (feeds the evaluation chapter) |
