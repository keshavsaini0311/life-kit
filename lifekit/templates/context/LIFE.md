# Life — the map

One place to talk to. The router (`life` skill) sends work to the right area and files what it
learns back into the file that owns it. **Always read `personal/rules.md` first.**

## Areas enabled for $name

| Area | Folder | Skills | What it owns |
|---|---|---|---|
$domain_table

Learning (`learning/`) is always on: actions, outcomes and the weekly learning report.

## Routing

| You say something like | Goes to |
|---|---|
$routing_table

Mixed messages fan out. Don't pick one area and drop the rest.

## Where the logs live

Each area owns its own data; there is deliberately no second combined copy.

| Log | File |
|---|---|
| Check-ins, spending, actions, outcomes | `learning/events.jsonl` (via the CLI) |
$log_table

## Automatic upkeep

`life-kit maintain` runs nightly before the review (if the `maintain` runner is installed): it
imports bank CSVs from `finance/inbox/`, rebuilds this and last month's ledger, refreshes the
learning report and writes a freshness list to `.local/reports/maintenance-YYYY-MM-DD.md`.
If a file has not been updated in weeks, say so instead of quietly using stale numbers.

## Adding an area later

Re-run `life-kit --workspace $workspace setup`; it asks only what is new.
