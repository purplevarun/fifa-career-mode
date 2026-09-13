# FIFA Career Stats

A local React dashboard and Python screenshot processor. No cloud service,
authentication, sync, or `.env` configuration is needed.

```text
raw_screenshots/             Put all original screenshots here
processing/                 Python OCR, validation, and SQLite code
processing/data/career.sqlite  Your saved stats (ignored by Git)
frontend/                   Vite/React dashboard
run                         Commands below
```

The launcher has two commands: `./run start` and `./run process`.

## Setup

Use Python 3.11+ and Node 22.12+ (or Node 24).

```sh
python3 -m pip install -r processing/requirements.txt
npm --prefix frontend ci
```

## Open the Dashboard

```sh
./run start
```

Open http://127.0.0.1:5000. If port 5000 is already in use, startup stops instead
of silently choosing another port. The dashboard reads the current SQLite
database through a local `/api/stats` endpoint. There is no separate server to
start and no JSON export or frontend rebuild needed when stats change.

## Player Statistics and Honours

On **Players**, choose a season and use **Player statistic** to rank completed
or attempted passes, key passes, interceptions, tackles, crosses, possession,
and other recorded counts. Totals use unique match appearances in the selected
season and competition; the preseason toggle applies too. **Apps recorded**
shows coverage, and missing values stay unknown rather than becoming zero.
Passing totals combine short, medium, and long passes only when all components
are available. Per-recorded-appearance figures exclude missing records.

Each player's **Season totals** tab includes match-derived detailed totals
separately from captured cumulative season snapshots. **Career records >
Honours & events** shows Player of the Month counts by player and season, with
the award month kept separate from its announcement date.

## Add Screenshots

Put new images into `raw_screenshots/`, then run:

```sh
./run process
```

This inventories images, skips previously extracted content, and automatically
saves valid OCR results as dashboard statistics in SQLite. It also imports cached
results left pending by older processing runs. **No review or approval step is
required.** Click Reload in the dashboard after processing.

Interrupted work resumes by rerunning the same command. Use `--limit 20` to OCR
a smaller batch or `--reextract` to refresh OCR and fill missing stats. Neither
option replaces existing non-null stats or saved corrections.

Supported screens include:

- Match/team stats, player performances, selected-player profiles and season totals.
- Completed transfers and loans, weekly wages, contract lengths and loan lengths.
- Player of the Month (news articles and dashboard banners), player/goalkeeper competition awards, Golden Boot headlines and competition winners.

Offers still in negotiation and award shortlists are not treated as completed
signings or wins. Missing years, selling clubs, fees and competition context stay
unknown. Contract offers are not mistaken for transfer fees. News surnames are
matched to existing players only when unambiguous.

Previously scanned transfer/news/winner screens and award-bearing dashboards are
retried once when their OCR version changes. Newly read fields and additional
events are imported without replacing saved values. Previously recorded player
and club name corrections are reused when the OCR spelling maps unambiguously
to an existing identity.

Player and goalkeeper screenshots are linked to the preceding match summary in
numeric screenshot order. An unrelated or unrecognized screen breaks that
context, so a player is never automatically attached across it. Goalkeeper
counts that include penalties are separated from the recorded shootout score.

Each source is validated and saved in its own transaction. Unsupported screens,
missing required context, and conflicting records are reported under
`import.skipped_sources`; they do not block other valid screenshots. Their OCR
results remain available for later processing. Automatically imported values
are not manually verified, so OCR mistakes that pass validation can still occur.
Existing saved stats and their identifiers are preserved.

## Rebuild From Scratch

```sh
./run process --clean
```

This backs up the existing database to a unique file under
`processing/data/backups/`, verifies that backup, resets the active database to
a fresh schema, and rebuilds statistics automatically from every distinct image
currently in `raw_screenshots/`. The backup path is printed before the reset. If the backup
fails, the existing database is not reset. If no database exists, one is created
without a backup.

**This clears saved stats, approvals, manual corrections, and processing history
from the active database.** Only screenshots still present can be processed
again; deleted originals cannot be reconstructed. With an empty screenshot
folder, the rebuilt database has no stats. Valid new OCR results are saved
automatically; no approval step follows the rebuild.

Original images, existing backups, and old review files are not deleted. Record
IDs are regenerated, so old review files must not be replayed after a reset. `--clean`
cannot be combined with `--limit` or `--screenshots`; it is a full rebuild. After
an interruption, resume with plain `./run process` to keep completed work.
For an OCR refresh that keeps reviewed stats, use `./run process --reextract`
instead.

## Delete Old Screenshots

You can delete old images after checking their results. **Deleting screenshots
does not delete saved matches or player stats.** Images are tracked by their
content hash in the local database, not by the highest filename number:

- A new image reusing an old filename is processed.
- The same image renamed or copied is not processed twice.
- An empty screenshot folder does not clear the database unless you use `--clean`.
- The website does not need screenshots to display saved stats.

Keep `processing/data/career.sqlite`: it contains the stats, review history, and
small processing checkpoints. It is not committed to Git. Processing does not
make another permanent copy of your images or delete them automatically.

## Optional Maintenance

Backups, review tools, and developer checks are available directly through
Python and npm; they are not additional `./run` commands.

`review` and `approve` remain optional maintenance tools for intentional manual
corrections, not requirements for processing. Replacing existing values through
those tools still requires `--replace-reviewed`.

```sh
python3 -m processing status
python3 -m processing backup processing/data/backups/my-backup.sqlite
python3 -W error::ResourceWarning -m unittest discover -s processing/tests -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Use a new backup filename each time. The reviewed database and its recovery copy
were preserved during this cleanup. Git history is not rewritten automatically.

`npm --prefix frontend run preview` opens a production build locally and uses
the same SQLite endpoint. A static upload to a hosting provider is not part of
this local app.

Missing goals scored default to zero for appearances recorded as GK in the
dashboard and reconciliation, with assumed values marked in the data and
verification tooltips. A recorded match position takes precedence over the
displayed position. Existing goal counts are never replaced, and the raw SQLite
values are retained. Other missing values, including outfield goals, stay
unknown. Shootout scores stay separate from match goals, and cumulative season
totals are not added to match totals.

When the recorded player goal total is lower than the team score, the difference
is treated as **assumed opponent own goals**. Verification and match details
label this assumption separately from warnings. Team scores and individual player
credits are never rewritten or assigned to an invented player. Excess player
goal credits still produce a warning, and unknown goal totals stay unknown.
Other warnings identify the fixture and the missing player or team statistics.

Optional real-image OCR regression tests use
`CAREER_OCR_TESTS=1 python3 -W error::ResourceWarning -m unittest discover -s processing/tests -q`
while those original fixtures remain available.
