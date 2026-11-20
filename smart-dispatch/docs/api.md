# JSON API

The PID's application/API layer. The API uses the same login session and role rules as the web pages
(log in first in the browser, then open the URLs). Responses are JSON; invalid input returns HTTP 400
with an `errors` object.

| Method | URL | Who | What |
|---|---|---|---|
| POST | `/api/evaluate/` | Logged-in users | Run the decision engine on a load offer |
| GET | `/api/loadboard/search/` | Dispatchers, managers, admins | Search loads (same filters as Search Loads), each with the engine's verdict |
| GET | `/api/loads/` | Carrier staff (not brokers) | Booked loads in the TMS, optional `?status=` |

## POST /api/evaluate/

Used live by the **New load offer** page as the dispatcher types.

Request body:

```json
{"rate": "2300", "loaded_miles": 1000, "deadhead_miles": 50,
 "pickup_at": "2026-12-01T08:00", "delivery_at": "2026-12-03T08:00",
 "driver_hours_available": 40}
```

Response (shortened; real output with the default settings):

```json
{"recommendation": "negotiate", "real_rate_per_mile": "2.19", "estimated_profit": "200.00",
 "counter_offer": "2625", "hos": {"status": "feasible", "required_transit_hours": 35.0},
 "reasons": ["Real rate $2.19/mi is below the $2.50/mi target but close enough to counter at $2,625."],
 "warnings": []}
```

At `"rate": "2200"` the same request returns `"reject"`: $2,200 is more than 15% below the $2,625 target.

## GET /api/loadboard/search/

Parameters: `origin` (required, "City, ST"), `dh_o`, `destination`, `dh_d`, `equipment`
(`V`, `R`, `F`, `SD`, `PO`, `BT`), `driver_type` (`solo`/`team`), `load_type`, `date_from`, `date_to`,
`max_weight`, `min_rpm`, `sort` (`age`, `rpm`, `rate`, `dho`, `trip`, `pickup`).

Example: `/api/loadboard/search/?origin=Dallas, TX&dh_o=100&equipment=V&sort=rpm`

```json
{"count": 24, "lane_rate_per_mile": "2.10",
 "results": [{"id": 1148, "origin": "Dallas, TX", "destination": "Springfield, MO", "pickup_date": "2026-11-20",
              "equipment": "Van", "trip_miles": 427, "dh_o": 0, "dh_d": null, "weight_lbs": 22000, "rate": "1200.00", "rate_per_mile": "2.81",
              "real_rate_per_mile": "2.81", "recommendation": "accept", "company": "Lone Oak Logistics Demo",
              "contact_phone": "(555) 010-2006", "contact_email": ""}]}
```

## GET /api/loads/

Parameters: `status` (`available`, `dispatched`, `in_transit`, `delivered`).

```json
{"count": 2, "results": [{"id": 268, "reference": "RC467121", "broker": "Broker Bravo Freight",
  "origin": "Charlotte, NC", "destination": "Atlanta, GA",
  "pickup_at": "2026-11-20T21:03:44+00:00", "delivery_at": "2026-11-23T07:03:44+00:00",
  "rate": "2100.00", "loaded_miles": 922, "deadhead_miles": 123, "real_rate_per_mile": "2.01",
  "status": "in_transit", "driver": "Driver Two", "truck": "102"}]}
```
