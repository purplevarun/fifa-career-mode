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

The launcher has three commands: `./run start`, `./run process`, and `./run format`.
`./run process` accepts no flags or other arguments and always rebuilds from scratch.

## Setup

Use Python 3.11+ and Node 22.12+ (or Node 24).

```sh
python3 -m pip install -r processing/requirements.txt
npm --prefix frontend ci
```

## Format Code

```sh
./run format
```

This formats frontend files in place with Prettier, using the existing
`frontend/.prettierrc` tab settings and `frontend/.gitignore` exclusions. It then
formats Python source and tests under `processing/` with Ruff. Generated
`processing/data/` contents, frontend build output, test results, and dependencies
are excluded. Formatting does not process screenshots or reset the database.

The command accepts no arguments and works from any working directory. Ruff is
pinned in `processing/requirements.txt`; the setup commands above install both
formatters.

## Open the Dashboard

```sh
./run start
```

Open http://127.0.0.1:5000. If port 5000 is already in use, startup stops instead
of silently choosing another port. The dashboard reads the current SQLite
database through a local `/api/stats` endpoint. There is no separate server to
start and no JSON export or frontend rebuild needed when stats change.

The main dashboard always follows `processing/data/career.sqlite`, the same
database written by `./run process`. It checks for changes every three seconds
and reloads the dataset when the database or its SQLite write-ahead log changes.
If the data folder is removed, the page stops displaying the old stats and waits;
it automatically loads the newly created database as processing writes it.
Neither a dev-server restart nor a manual browser reload is needed. Deleting
the folder still removes its database, backups, and saved corrections.

The homepage identifies the database being displayed and shows **Last processed**
from its most recent finished processing run, in your local timezone. This time
is saved in SQLite and does not change when the page reloads. Older databases
without run history show **Last OCR saved** instead; this is the timestamp of
their last saved extraction, not a claimed command-completion time. Skipped
sources and OCR errors from a recorded run are displayed separately.

To inspect another database without replacing the main archive, start a separate
read-only dashboard instance on an unused port. These optional settings apply
only to that server process; no `.env` file is required:

```sh
CAREER_DB="/absolute/path/to/preview.sqlite" \
CAREER_DATA_LABEL="Fresh processing preview" \
npm --prefix frontend run dev -- --port 5001 --strictPort
```

Both development and production-preview servers support these settings. They do
not import data or alter the chosen database. Plain `./run start` continues to
use the main archive. An alternate preview follows only its explicitly selected
database; it never replaces or redirects the main archive. `./run start` ignores
preview environment settings so it always opens the processor's main database.

## Overview Rankings

The overview shows the top five Notts County players for goals, assists,
appearances, completed passes, tackles won, and average match rating. All six
rankings follow the season, competition, and preseason filters. Ratings average
only recorded match ratings, not player overall ratings. Passing totals require
all three distance components for each counted appearance. Unknown measurements
are excluded, partial totals are marked, and chart tooltips show record coverage.

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

## Process Screenshots

Put new images into `raw_screenshots/`, then run:

```sh
./run process
```

**Every run deletes the entire `processing/data/` folder first.** This includes
the current database, OCR cache, saved corrections, review history, exports,
previews, and any backups inside that folder. No automatic backup is created.

The command then recreates `processing/data/career.sqlite`, inventories all
remaining original screenshots, runs OCR on every distinct image, and imports
valid statistics automatically. Previously processed images are processed again;
identical file contents are deduplicated within the new scan. Entity UUIDs and
processing history are regenerated on every run. Original screenshots and source
code are not deleted or rewritten.

**No flags and no review or approval step are required.** The former `--clean`,
`--reextract`, `--limit`, and `--screenshots` options are rejected before deletion,
as are any other arguments to `./run process`. The command always writes the main
database and cannot be redirected with `--db`. Symlinked processing or data
directories are rejected to avoid deleting data outside the intended location.

The open main dashboard automatically detects the replacement database and
shows the new run's processing timestamp. During processing it may show partial
new results; old statistics are not retained as a fallback.

If processing fails or is interrupted, the old data is already deleted. The new
folder can contain partial results. Rerunning `./run process` deletes those too
and starts from the beginning; it does not resume a cache. With no screenshots,
the recreated database has no statistics.

Unreadable single-digit player and team counts get a contrast-normalized,
enlarged-glyph retry.
Three-copy and five-copy readings must agree before a digit is recovered; the
original and retry readings remain in the OCR evidence. Blank or ambiguous cells
stay unknown. Each rebuild uses the current OCR implementation on every image.

Supported screens include:

- Match/team stats, player performances, selected-player profiles and season totals.
- Completed transfers and loans, weekly wages, contract lengths and loan lengths.
- Player of the Month (news articles and dashboard banners), player/goalkeeper competition awards, Golden Boot headlines and competition winners.

Offers still in negotiation and award shortlists are not treated as completed
signings or wins. Missing years, selling clubs, fees and competition context stay
unknown. Contract offers are not mistaken for transfer fees. News surnames are
matched to existing players only when unambiguous.

Player and goalkeeper screenshots are linked to the preceding match summary in
numeric screenshot order. An unrelated or unrecognized screen breaks that
context, so a player is never automatically attached across it. Goalkeeper
counts that include penalties are separated from the recorded shootout score.

Each source is validated and saved in its own transaction. Unsupported screens,
missing required context, and conflicting records are reported under
`import.skipped_sources`; they do not block attempts to import other valid
screenshots. OCR failures, unimportable extracted records, and database validation
errors produce a nonzero exit code and an incomplete result, not a rollback to
the deleted database. Screens with no supported statistics can be skipped.
Automatically imported values
are not manually verified, so OCR mistakes that pass validation can still occur.

## OCR Reliability

OCR improvements are implemented in the processor and tested against values
visible in original screenshots. Processing does not load a saved-answer file
to override fresh extraction. Each rebuild starts without earlier SQLite-only
corrections or learned aliases, so its results may differ from manually corrected
archives.
Recognition and relationship validation cannot guarantee 100% accuracy for
arbitrary screenshots. Unsupported screens and missing context are reported;
zero coverage warnings does not mean every screenshot yielded a record.

## Delete Old Screenshots

**Keep the original screenshots for any statistics you want to rebuild.** Deleting
an image does not immediately change the displayed database, but the next
`./run process` rebuilds from only the remaining files. Data supported only by
deleted originals will be lost. Images are identified by content hash, not by
the highest filename number:

- A new image reusing an old filename is processed.
- Identical copied files are processed once per rebuild.
- An empty screenshot folder produces an empty database on the next run.
- The website reads SQLite; it does not need the images until processing runs again.

Keep `processing/data/career.sqlite`: it contains the stats, review history, and
small processing checkpoints. It is not committed to Git and is replaced on
every processing run. Processing does not make another permanent copy of your
images or delete the originals automatically.

## Optional Maintenance

Backups, review tools, and developer checks are available directly through
Python and npm; they are not additional `./run` commands.

`review` and `approve` remain optional maintenance tools for intentional manual
corrections, not requirements for processing. Replacing existing values through
those tools still requires `--replace-reviewed`; those manual changes are lost
on the next full processing run. Store any manual backup **outside**
`processing/data/` if it needs to survive processing.

```sh
python3 -m processing status
python3 -m processing backup backups/my-backup.sqlite
python3 -W error::ResourceWarning -m unittest discover -s processing/tests -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Use a new backup filename each time. Git history is not rewritten automatically.

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
is treated as **assumed opponent own goals** by the reconciliation logic, without
displaying an assumption notice. Team scores and individual player
credits are never rewritten or assigned to an invented player. Excess player
goal credits still produce a warning, and unknown goal totals stay unknown.
Other warnings identify the fixture and the missing player or team statistics.

Optional real-image OCR regression tests use
`CAREER_OCR_TESTS=1 python3 -W error::ResourceWarning -m unittest discover -s processing/tests -q`
while those original fixtures remain available.
