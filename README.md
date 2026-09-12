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

## Setup

Use Python 3.11+ and Node 22.12+ (or Node 24).

```sh
python3 -m pip install -r processing/requirements.txt
npm --prefix frontend ci
```

## Open the Dashboard

```sh
./run dev
```

Open the localhost URL printed by Vite. The dashboard reads the current SQLite
database through a local `/api/stats` endpoint. There is no separate server to
start and no JSON export or frontend rebuild needed when stats change.

## Add Screenshots

Put new images into `raw_screenshots/`, then run:

```sh
./run process
```

This inventories images, skips previously extracted content, and saves new OCR
results in SQLite. Interrupted work resumes by rerunning the same command. Use
`--limit 20` to process a smaller batch or `--reextract` to refresh OCR candidates.
Neither option overwrites reviewed stats.

OCR now proposes:

- Match/team stats, player performances, selected-player profiles and season totals.
- Completed transfers and loans, weekly wages, contract lengths and loan lengths.
- Player of the Month (news articles and dashboard banners), player/goalkeeper competition awards, Golden Boot headlines and competition winners.

Offers still in negotiation and award shortlists are not treated as completed
signings or wins. Missing years, selling clubs, fees and competition context stay
unknown. Contract offers are not mistaken for transfer fees. News surnames are
matched to existing players only when unambiguous and still require review.

Previously scanned transfer/news/winner screens and award-bearing dashboards are
retried once when their OCR version changes. New review files preserve reviewed values while proposing newly
read fields and additional events; the saved stats are not changed by extraction.

OCR can misread numbers or associate a player with the wrong match. New results
therefore produce an editable review file under `processing/data/reviews/`.
Check those values against the originals, supply missing match/season context,
and approve the file shown by the processor:

```sh
./run approve processing/data/reviews/<review-file>.json --note "Checked against originals"
```

Approval saves the stats in one SQLite transaction. Click Reload in the
dashboard to see them. Existing reviewed data is preserved; intentional
corrections require `--replace-reviewed`.

## Delete Old Screenshots

You can delete old images after checking their results. **Deleting screenshots
does not delete saved matches or player stats.** Images are tracked by their
content hash in the local database, not by the highest filename number:

- A new image reusing an old filename is processed.
- The same image renamed or copied is not processed twice.
- An empty screenshot folder does not clear the database.
- The website does not need screenshots to display saved stats.

Keep `processing/data/career.sqlite`: it contains the stats, review history, and
small processing checkpoints. It is not committed to Git. Processing does not
make another permanent copy of your images or delete them automatically.

## Backups and Checks

```sh
./run status
./run backup processing/data/backups/my-backup.sqlite
./run test
./run check
./run e2e
```

Use a new backup filename each time. The reviewed database and its recovery copy
were preserved during this cleanup. Git history is not rewritten automatically.

`./run build` and `./run preview` also work locally; preview uses the same SQLite
endpoint. A static upload to a hosting provider is not part of this local app.

Missing/unreviewed values stay unknown, shootout scores stay separate from match
goals, and cumulative season totals are not added to match totals. Optional
real-image OCR regression tests use `CAREER_OCR_TESTS=1 ./run test` while those
original fixtures remain available.
