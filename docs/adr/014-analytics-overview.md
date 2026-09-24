# ADR-014 — Server-computed analytical overview for the control tower

## Status

Accepted

## Context

The P8.7 discovery audit examined every table, timestamp and join path in the
canonical schema to determine which analytical variables the control tower's
future visualization layer can honestly support. It found two very different
time-story capabilities:

- **Shipments, orders and shipment events** carry genuine recorded history —
  planned and actual departure/arrival dates across ten months of operational
  data — so service performance, shipment volume and departure-month incidence
  are computable today as real time series.
- **The exception workflow** (detection, approval, execution, resolution) has
  no temporal observations in the current dataset: every exception shares one
  batch `detected_at` timestamp, and no resolution or intervention history
  exists yet. The schema supports these series; the data does not.

The audit's honesty constraints therefore bind the design: no fabricated
history, no synthetic snapshots, no metric rendered from data that does not
exist, and no frontend that performs domain arithmetic or invents a time axis.

## Decision

Analytics is a **separate read-only projection**, not an extension of the
operational snapshot. `GET /v1/analytics/overview` (ADR-011's versioned
boundary) serves seven datasets, each computed server-side by a dedicated
read-only repository (`analytics_repo.py`) and composed by one service
function, following the existing API → service → repository → database layering:

1. **Service performance** — on-time percentage by planned-arrival month over
   delivered shipments with recorded actual arrivals, with per-month delivered
   counts preserved.
2. **Exception incidence** — exceptions relative to shipments **by
   planned-departure month**, explicitly not detection-over-time.
3. **Shipment volume** — all recorded shipments by planned-departure month.
4. **Transport mode performance** — on-time percentage per mode over the same
   delivered population.
5. **Carrier performance** — on-time percentage per carrier, with display names.
6. **Warehouse distribution** — exceptions per origin warehouse along the
   exception → shipment → order → warehouse join.
7. **Severity composition** — the open-exception snapshot by severity.

Each dataset carries a `basis` string **as contract metadata**, so the frontend
labels every series truthfully ("Delivered shipments by planned-arrival month",
"Exceptions by shipment departure month") instead of hiding analytical
assumptions in component copy.

Deliberately absent: recovery-performance, resolution-performance and
exception-detection-trend series. The current data cannot support them, and
rendering empty or synthetic charts is worse than rendering none. They become
available exactly when recorded workflow history exists — no contract change
is required to add them.

## Consequences and trade-offs

- **One request powers every visualization variable.** The frontend never
  aggregates, never divides by a zero denominator and never derives a rate.
- **The operational snapshot stays stable.** `ControlTowerSummary` keeps its
  exact contract; analytics evolves independently.
- **Cross-backend by construction.** Queries use only constructs the shared
  persistence layer serves unchanged to SQLite and PostgreSQL (plain
  aggregates, GROUP BY, CASE, substr, julianday). No new table, no migration,
  no schema version change.
- **Plain dictionaries at the boundary** (ADR-011 discipline): no
  persistence-layer row type reaches the service or API layers.
- **Empty is the honest zero.** Fresh databases return empty series with their
  bases intact — the contract never zero-fills months that have no records,
  while months with departing shipments but no exceptions are explicit zeros
  (dropping them would fabricate visual activity).
- **Deferred:** a snapshot/history capability that would one day give
  resolution, recovery and detection analyses real time series, and the
  visualization layer itself (P8.7.2+, hand-rolled SVG, no chart dependency).
