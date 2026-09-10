# Notts County Career Data: Process and Handoff

Last updated: 2026-09-10

## 1. Goal and Confirmed Decisions

Build a trustworthy career dataset for a React application that visualizes Notts County match, player, season, and competition statistics.

- SQLite in `data/career.sqlite` is the authoritative store for validated application data, reviewed corrections, and import progress. Original screenshots in `raw_data/` remain immutable evidence for checking those records.
- Include every captured match, including preseason games. Missing evidence must be tracked, not silently omitted.
- Every imported match must reference a competition edition. No orphan matches and no nullable competition relationship.
- Add `Competition.is_preseason` as a required boolean. Preseason tournaments are real competitions in this model.
- `Player_Match` is the central performance table, with one record per player per match.
- Player snapshots are essential: preserve season-start, season-end, and other dated observations of overall rating and player details.
- The user confirmed that the first three screenshots are a player-data capture group, not match screens. Similar groups recur at season end or the start of the next season; process them as squad snapshots independently of match groups.
- Implemented storage: SQLite contains image inventory, structured OCR evidence, review history, and canonical records. JSON exports are a read-only copy for React; editable review JSON is an interchange format, not a second authoritative database.
- On the user's 2026-09-10 instruction, the obsolete text-only OCR script and all 1,296 generated text files were removed. All 1,296 original screenshots are preserved. The replacement never reads the retired text pipeline.
- Build and validate the data pipeline before building the React application. A static JSON-backed app can come first; an editing API can come later.

Scope initially covers this one career save. If another save is added, introduce explicit career scoping before mixing records.

## 2. Current Evidence and Its Limits

The initial analysis scanned the legacy text outputs and spot-checked two original player-performance screenshots. The following historical counts were recorded before the text was removed. Current screenshot extraction and import progress is in section 7; the complete archive has not been imported.

| Screen category inferred from text | Files |
| --- | ---: |
| Player performance | 1,162 |
| Match summary / match facts | 95 |
| Squad hub: player details or season totals | 25 |
| Transfer detail | 3 |
| Career dashboard / partial standings | 5 |
| News | 5 |
| Competition result | 1 |
| Total | 1,296 |

- There were 1,296 source images and 1,296 text files. The new image inventory has independently verified 1,296 readable images with 1,296 distinct content hashes.
- Legacy text totaled approximately 636 KB. There were no identical trimmed text outputs, but different OCR outputs can describe the same screen or match.
- Date and competition normalization produced 85 provisional fixture groups from 95 match summaries, spanning 2018-07-04 through 2019-11-02.
- Ten fixture groups have repeated summary captures. Do not import each summary as a new match.
- Provisional numeric screenshot groups contain 11-17 player-performance captures per match. These are not verified unique appearances.
- Text classification found 88 goalkeeper-performance screens and one opponent-performance screen: Sam Hoskins of Northampton in `Screenshot_976.txt`. Do not assume every player screen is a Notts County player.
- These discovery counts are not verified canonical totals. Current imported records are a reviewed pilot subset; identity resolution across the whole archive remains unfinished.

### Provisional competition inventory

These counts are discovery targets to reconcile against images, not totals to force the import to match.

| Competition | Provisional matches | is_preseason |
| --- | ---: | --- |
| European International Cup | 5 | true |
| Invitational Cup | 5 | true |
| EFL League Two | 46 | false |
| EFL League One | 16 | false |
| Carabao Cup | 2 | false |
| Checkatrade Trophy | 7 | false |
| FA Cup | 4 | false |

The July 2018 European International Cup belongs to season 2018/19; the July 2019 Invitational Cup belongs to 2019/20. Confirm fixture details from their screenshots. Preserve displayed labels such as `European Int'l Cup` and `The Emirates FA Cup` as aliases.

If images reveal a standalone preseason friendly, assign it to an explicit preseason-friendly competition edition once that classification is established. An unresolved competition stays in staging for review; it must not become a match with a missing competition or an invented league assignment.

### Known source limitations

- The retired OCR script kept text only, discarding bounding boxes and recognition confidence.
- In [the Elliott Hewitt source](raw_data/Screenshot%20%281002%29.png), the old OCR dropped visible zeroes and interleaved attacking/defending columns.
- [The Aaron Ramsdale source](raw_data/Screenshot%20%28108%29.png) uses a different goalkeeper layout. It has now been visually reviewed and imported.
- Direct cropped-cell recognition recovers many of the missing digits, but some zeroes, names, separators, and clock readings still need correction. OCR confidence is often low; no OCR candidate is automatically approved.
- Some match summary text omits the score entirely. A missing score is not 0-0.
- OCR confuses labels and dates, including `Tw0`, `0ne`, `0ctober`, merged words, and missing spaces.
- Standings are partial dashboard snapshots, not a full archive of every club's results.
- Inspected performance screens do not establish minutes played or substitution times. Do not invent these or publish per-90 metrics without evidence.
- Squad season-total screens include disciplinary columns such as YC/RC; this does not establish when those cards happened in individual matches.
- Transfer screens mix weekly wages, contract terms, loan terms, and offer details. These are different fields.

## 3. Planned Data Model

Names below describe logical entities; implementation naming can follow consistent SQLite conventions. Use stable IDs independent of filenames, spelling corrections, ratings, and scores.

The implemented schema is [career_data/schema.sql](career_data/schema.sql), version 1. Tables use plural snake_case names. The importer refuses unsupported schema versions and existing unversioned databases instead of overwriting them.

| Entity | Main responsibility and fields |
| --- | --- |
| `Player` | Stable identity, canonical full name, nationality when supported. Keep OCR/display aliases linked to the same ID. Do not use the name as a primary key. |
| `Club` | Notts County, opponents, and transfer counterparties, with canonical names and aliases. |
| `Season` | Label such as `2018/19`, with boundaries supported by career context. |
| `Competition` | Canonical name, format/type, aliases, and `is_preseason`. |
| `Competition_Season` | An edition of a competition in a season; unique `(competition_id, season_id)` for this save. |
| `Match` | Competition edition, date, home/away clubs, venue, stage/round/leg where known, scores, completion and review status. |
| `Player_Match` | Match, player, club at the time, observed position and OVR, participation information, rating, and individual statistics. |
| `Team_Match` | Match and club, with team-level shots, possession, corners, fouls, tackles, accuracy, and other visible match facts. |
| `Player_Snapshot` | Player, season, club, observation date or interval, snapshot kind, OVR, age, positions, squad role, and other visible historical details. |
| `Player_Competition_Snapshot` | Captured cumulative appearances, goals, assists, clean sheets, cards, and average rating for a player, club, competition edition, and observation date. |
| `Player_Transfer` | Player, source/destination clubs where known, permanent/loan type, status, effective date or interval, fee, wage, currency, contract term, and separate loan term. |
| `Competition_Event` | Competition edition, event type, relevant player/club, event or announcement date, and period/stage when applicable. |
| `Source_Image` | Original relative path, content hash, dimensions, numeric filename sequence, screen type, and processing/review status. |

`Match_Competition` is unnecessary: `Match.competition_season_id` provides the required many-to-one relationship. A match's round or stage belongs to its edition, not to a second competition. An aggregate called "All competitions" is a query, not a competition record.

### Competition and match invariants

- `Competition.is_preseason` must be non-null and accept only true/false, represented as checked 0/1 values in SQLite.
- `Competition_Season.competition_id` and `Competition_Season.season_id` are required foreign keys.
- `Match.competition_season_id` is a required foreign key. Enable SQLite foreign-key enforcement on every connection.
- Preserve preseason in storage and JSON exports. Queries may explicitly include/exclude it, but season boundaries must not discard July games.
- Resolve home and away clubs from the image layout, not OCR line order. Both must be known and different before publishing a validated fixture.
- Keep the final score before a shootout separate from shootout scores. Store regulation scores separately if actually observed, plus extra-time/penalty indicators.
- A shootout is not automatically evidence of 120 minutes. Keep match result and advancement/winner information distinct.
- Identify duplicate captures using date, competition edition, clubs, and surrounding context. Date alone is not a globally unique match key. A genuine replay is a separate match.

### Player-match detail

- Enforce unique `(match_id, player_id)` and require the recorded club to be one of the two match clubs.
- Include verified starters and used substitutes; do not manufacture rows for missing captures or unused substitutes. Normally there will be 11 starters plus used substitutes, but screenshot count is not appearance count.
- Keep `started`, `minutes_played`, and played position unknown unless supported by an image. A displayed profile position may differ from the position played.
- Capture observed rating, OVR, goals, assists, shots on/off target, completed/failed short/medium/long passes, key passes, and crosses successful/failed.
- Capture tackles won/lost, fouls, penalties conceded, interceptions, blocks, out-of-position counts, possession won/lost, clearances, headers won/lost, and movement/dribbling fields when visible.
- Use the goalkeeper layout for goals conceded, shots caught/parried, crosses caught, and balls stripped, along with its shared passing/positioning fields.
- Keep unknown values as `null`. Preserve the difference between unreadable, not captured, and not applicable in field metadata. Only write zero when the source supports zero.
- Store counts as numbers and retain source-displayed percentages. Derive aggregate passing/shooting percentages from summed numerators and denominators, not an average of percentages; return null for zero denominators.
- Retain a source link for every recovered field, especially values corrected by visual review.

### Player snapshots and season boundaries

Snapshots are historical observations, not mutable fields on `Player`.

- Required identity/context: snapshot ID, player ID, season ID, and source evidence; club ID when established.
- Temporal fields: `observed_on` when exact, otherwise nullable `date_from`/`date_to`, plus `date_precision` and `date_basis` describing what is actually known.
- Use `snapshot_kind` such as `season_start`, `season_end`, or `in_season`. A transfer observation can be marked separately if useful.
- Store OVR, observed age, displayed positions, and supported squad/financial details. Age without a birth date must not be converted into an invented exact birthday.
- Establish season-start/end labels from game context, not merely the first/last filename. Preseason observations belong to the upcoming career season.
- An earliest available observation is not automatically a true season-start snapshot. Keep the actual date/context and label missing baselines honestly.
- A player joining midseason may have a first-at-club baseline without having a Notts County season-start observation.
- Retain in-season OVR observations from performance screens; their inferred match date must link back to the confirmed match. They do not replace squad boundary observations.
- Preserve multiple observations per player per season, resolve duplicate captures, and record conflicting values for review instead of overwriting them.
- Compare start and end OVR only when both observations are supported. Distinguish within-season development from the gap between one season's end and the next season's start.

### User-confirmed squad capture groups

On 2026-09-10, the user confirmed that the first three images capture player data: [raw_data/Screenshot (70).png](raw_data/Screenshot%20%2870%29.png), [raw_data/Screenshot (71).png](raw_data/Screenshot%20%2871%29.png), and [raw_data/Screenshot (72).png](raw_data/Screenshot%20%2872%29.png). Together they form the opening squad capture group. This pattern can recur at the end of a season or the beginning of the next season.

- Collect every visible player row across the group, not only the selected player's detail panel. Create or reuse `Player` identities and record their visible OVR and other supported details in `Player_Snapshot`.
- Merge overlapping roster rows within the same capture group and retain their source evidence. Repeated rows are not extra players or extra appearances. Apply selected-panel details only to the selected player, never to every row on that screenshot.
- Keep these squad snapshots independent of fixtures: no `match_id` and no `Player_Match` records should be created from them.
- Keep later capture groups as separate historical observations, even when a player's OVR is unchanged. Establish `season_start` versus `season_end` and the correct season from career context; do not collapse a closing snapshot into the next season's opening snapshot.
- Do not assume every future group contains exactly three screenshots, that every squad screen marks a season boundary, or that its exact capture date is known. Preserve date precision and its basis.
- Implementation follow-up: the current extractor proposes only the selected profile from each squad screen. Full roster-table extraction and group-level overlap resolution remain to be implemented. Do not mark the opening three-image group complete after importing only its selected profiles.

Verified boundary examples: [the opening squad image](raw_data/Screenshot%20%2870%29.png) shows Aaron Ramsdale at OVR 62, age 20, and [the closing squad image](raw_data/Screenshot%20%281055%29.png) shows OVR 65, age 21, with a displayed +3 change. Both are now imported as 2018/19 boundary observations with season-level date precision, not invented exact dates. Their date-basis fields describe the neighboring preseason and season-end evidence. Season 2019/20 end-of-season coverage is not established by this archive.

`Player_Competition_Snapshot` is a separate reconciliation source. Captured cumulative totals must never be added to the per-match totals. Preserve their observation date and exact competition/club scope; retain all-competition totals as such rather than assigning them to an invented competition.

### Transfers, events, and standings

- Permanent transfers and loans need distinct types. Separate a loan's duration from a player's contract length; the Calvert-Lewin source appears to show different terms.
- Do not treat a weekly wage as a fee, or an unknown fee as a free transfer. Store money in integer minor units when the currency is known, retaining the original display value and currency symbol.
- Transfer dates displayed as day/month need a documented year anchor. Do not use real-world transfer history to fill career-save facts.
- Competition events include titles, promotion, elimination, monthly player awards, and tournament player/goalkeeper awards. Keep an award's covered period separate from its announcement date.
- Goals, cards, and substitutions at specific minutes would belong to a future `Match_Event` table, not `Competition_Event`; add it only if sources support those details.
- Retain partial standings as timestamped observations with their scope. Add `Standing_Snapshot` if needed during extraction, without pretending partial tables reconstruct every opponent's season.

## 4. Screenshot-First Extraction Method

Working hypothesis: layout-aware reading of the original images can recover visible zeroes and correctly associate the columns that the existing text extraction loses.

Discriminating check: manually transcribe a small set of source images, including zero-valued fields, then compare extraction output field by field. A wrongly assigned or silently omitted value fails the pilot; fix the affected layout or use visual transcription before batch processing.

### Phase A: Inventory and classification

1. Inventory every original image recursively. Record original path, SHA-256 hash, dimensions, and the numeric screenshot sequence when present.
2. Check image readability, duplicate content, and filename collisions. Preserve original names and bytes; do not rename the archive. SQLite `source_images` and `source_paths` hold the inventory.
3. Sort by numeric sequence for navigation, not lexical filename order. Filesystem timestamps are not in-game dates.
4. Classify from the images: match facts, outfield performance, goalkeeper performance, squad status/stats, transfer detail, news, career dashboard, competition result, or unknown.
5. Classify using the original images. The historical text findings in this document are navigation hints only; the old text files no longer exist.
6. Track per-source state in SQLite: `inventoried`, `needs_review`, `imported`, `rejected`, or `error`, with screen type tracked separately. Classification and extraction are currently implemented for a subset of layouts. An approved partial source remains `needs_review`; its checked records still enter the canonical tables.

### Phase B: Pilot before bulk extraction

Start with three fixture anchors and their actual neighboring player captures:

| Pilot | Source image | What it tests |
| --- | --- | --- |
| Opening preseason fixture | [Screenshot (73)](raw_data/Screenshot%20%2873%29.png) | Mandatory preseason edition, missing text score, normal player layouts. |
| First League One fixture | [Screenshot (1159)](raw_data/Screenshot%20%281159%29.png) | Next-season context, repeated summary handling, changed squad. |
| Checkatrade shootout fixture | [Screenshot (808)](raw_data/Screenshot%20%28808%29.png) | Shootout versus match score and competition-specific duration uncertainty. |

Also inspect the squad snapshot candidates above and at least one permanent-transfer and one loan detail screen.

1. Read the whole anchor image, establish date/competition/clubs, and inspect numeric neighbors until the fixture boundary is confirmed. Do not assume a fixed number of images per match.
2. Manually establish expected values for the pilots. Include every visible field needed for the intended import, not just the final score.
3. Use image viewing and region crops as the primary extraction surface. The implementation pins RapidOCR 1.2.3 and retains full-image OCR tokens, crop coordinates, recognition confidence, extractor version, and raw readings in SQLite.
4. Extract template-specific regions: header/score, club labels, player identity, attacking, defending, goalkeeping, squad rows, and transfer/news panels.
5. Normalize crop coordinates to each image's dimensions; confirm layouts before applying templates to another resolution or screen variant. Retain the original coordinate mapping for evidence.
6. Exclude crests, background banners, menu hints, and overlays from data fields. Inspect crops directly when text is ambiguous.
7. Save structured field candidates with source and crop coordinates, raw reading, normalized value, extraction method/version, confidence when available, and review status. Do not invent confidence scores for visual transcription.
8. Confirm every published pilot value against its source image. Unreadable or absent values remain explicit unknowns, never guesses.
9. Run identity, relationship, duplicate, score, and snapshot checks before declaring the pilot passed.

### Phase C: Establish chronology and identity

1. Resolve canonical players and clubs with aliases. Normalize spacing and clear OCR errors, but do not automatically merge ambiguous initials or fuzzy name matches.
2. Build a fixture index from confirmed match facts images, competition/result context, and date anchors. Keep a stable canonical ID as corrections arrive.
3. Link player captures to fixture candidates using confirmed boundaries and visual context. Numeric adjacency alone is insufficient when a menu/news screen interrupts a sequence or a summary repeats.
4. Reconcile repeat captures into one player-match row. Preserve all supporting sources; conflicting values require review rather than last-write-wins behavior.
5. Establish season boundaries, snapshot roles, and inferred date intervals with source evidence. Never assign precise dates from file modification times.
6. Review the opponent-performance capture and any other unexpected club/player combinations explicitly.

### Phase D: Complete extraction in resumable batches

1. Work in complete fixture groups, with manageable batches such as five fixtures. Finish and validate one batch before expanding it.
2. Extract match facts, both teams' visible stats, and all supported player performances, including goalkeepers and substitutes.
3. Process squad, transfer, standings, competition-result, and news images as their own screen families. These are not miscellaneous files to skip after match extraction.
4. At each batch boundary, update per-image states, fixture coverage, resolved identities, and the review queue.
5. Record missing captures, unreadable values, uncertain dates, and unresolved associations explicitly. Missing player coverage is a review item, not a reason to create synthetic rows.
6. Reconcile completed batches against captured season and competition totals. A discrepancy can indicate missing appearances, duplicated captures, OCR mistakes, or different competition scope; investigate rather than altering values to fit.

### Phase E: Import and export

1. Create the versioned SQLite schema with required foreign keys, unique keys, and type/range checks.
2. Import only records meeting required identity and relationship checks. Keep unresolved candidates in staging and report them; never discard them silently.
3. Preserve source associations with `match_sources`, `player_match_sources`, and source foreign keys on the other records. Structured extraction evidence and reviewed payloads are stored as JSON inside SQLite, so removing scratch review files does not remove approved corrections.
4. Use transactions and idempotent imports. Reprocessing unchanged sources must not create new players, matches, appearances, snapshots, or events.
5. Keep reviewed corrections separately from machine candidates. A rerun may propose a conflict, but must not erase a reviewed correction. Normal imports fill unknown fields and reject conflicting known values; explicit `--replace-reviewed` permits intentional corrections, including clearing a value to null, and appends an audit record. Identity changes involving already-linked matches or appearances are rejected and require a separate reviewed migration.
6. Export stable-ID JSON datasets and derived summaries with a schema version, generation time, provenance references, and coverage information.
7. Recompute derived results after approved corrections. React consumes validated records and exposes known coverage limits; it does not parse OCR.

## 5. Validation and Publication Gates

- Archive coverage: every source image has a manifest entry and an accountable state; distinguish duplicate sources, completed extraction, errors, and pending review.
- Match coverage: reconcile against the provisional 85 fixtures and seven competitions, explaining additions, merges, or unresolved groups rather than forcing those counts.
- Competition integrity: every imported match resolves to an existing competition edition and season; verify both known preseason competitions are flagged and exported.
- Identity integrity: no dangling player/club IDs, no duplicate player-match keys, and no player appearance assigned to a club outside that fixture.
- Score integrity: nonnegative goals, separate shootout scores, and no result computed from unknown scores. Compare player goals with team scores only when coverage and own-goal handling make that comparison valid.
- Stat integrity: nonnegative counts, percentages in 0-100, supported rating/OVR ranges, correct attacking/defending associations, and explicit unknown/not-applicable fields.
- Appearance coverage: report verified player count, missing/ambiguous identities, and duplicate captures per fixture. Do not treat a count of 11 screenshots as proof of a complete starting XI.
- Snapshot integrity: preserve date certainty, source evidence, season, and snapshot kind. Missing start/end evidence must not produce a fabricated OVR change.
- Season reconciliation: compare derived appearances, goals, assists, clean sheets, and other available metrics with captured cumulative stats at the same cutoff and scope. Track differences rather than overwriting source facts.
- Standings reconciliation: the May 2019 dashboard appears to show Notts County with 46 played and 83 points. Verify the image before using this as a League Two cross-check.
- Import repeatability: rerun the pilot import and verify unchanged row counts and IDs; test that reviewed corrections survive re-extraction.
- Export integrity: validate JSON structure, foreign references, null handling, preseason inclusion, snapshot history, and aggregate consistency with SQLite.
- Publication honesty: label partial coverage and do not advertise full-league histories, minutes-based metrics, or timeline events that the images do not support.

## 6. Implemented Workflow and Reproducibility

```text
raw_data/                    immutable original screenshots
career_data/
  __main__.py                command-line interface
  database.py                initialization, inventory, integrity checks
  extraction.py              screenshot classification and crop recognition
  pipeline.py                staging, review, canonical imports, export, backup
  schema.sql                 relational schema, constraints, source links
tests/                       focused importer and real-image OCR tests
requirements.txt             pinned direct image/OCR dependencies
DATA_PROCESS.md              living workflow and handoff
data/
  career.sqlite              canonical data, source inventory, OCR, reviews
  review/                    editable scratch review documents
  exports/career.json         derived read-only dataset for React
  backups/                   consistent local SQLite backup copies
```

SQLite is not a disposable generated file: it contains human-reviewed corrections and progress that automatic OCR alone cannot reproduce. It is eligible for version control. Scratch review files, exports, SQLite journal files, and local backups are ignored by Git. No implementation changes have been committed or pushed yet. Preserve both the database and original screenshots when moving or backing up the project; a local backup alone does not protect against loss of the machine.

### Runtime and setup

The implementation was verified with the already-installed Python 3.14.5, SQLite 3.50.4, Pillow 12.2.0, and rapidocr-onnxruntime 1.2.3. It uses standard-library SQLite and runs OCR locally, without uploading images. Python 3.11 or later is required. Dependencies are listed in [requirements.txt](requirements.txt).

For an isolated environment on a fresh machine:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Use `.venv/bin/python` in place of `python3` below when using that environment. No administrator permissions or system-wide installation is required. The current implementation run used the already-available interpreter and dependencies; it did not create a new virtual environment.

### Adding screenshots

1. Add images to `raw_data/`, using new filenames. Do not overwrite existing screenshots. Numeric filename sequences help navigation but are not in-game dates or guaranteed match IDs.
2. Run the incremental import command. It inventories all images but OCRs at most 20 unprocessed images by default. Rerun to continue; unchanged images with extraction results are skipped by content hash.

```sh
python3 -m career_data import --limit 20
python3 -m career_data status
```

The initial archive still has many pending images, so this command resumes that backlog first. To target newly added screenshots, use an explicit selection:

```sh
python3 -m career_data import --screenshots 1159 --limit 1
```

`--screenshots` accepts numbers and inclusive ranges, such as `73,76,808-810`. Every requested number must exist; gaps are reported rather than silently skipped. `remaining` in the import report refers to that run's selection, not the whole archive. Use `status` for overall coverage.

3. Export an editable review document for the selected images. Choose a new output filename each time; the command deliberately refuses to overwrite an existing review file.

```sh
python3 -m career_data review --screenshots 1159 --output data/review/wycombe-check.json
```

Inspect the original images and correct the `records` in that file. Keep the `source_id` unchanged. Set `complete` to true only after reviewing the relevant data for the source; leave it false when other rows or facts on that image remain outstanding. A generated document for a previously reviewed source starts from its reviewed payload, not fresh OCR guesses. Raw OCR/crop evidence remains available in the `extractions` table.

Match records must have a verified date, competition, season, and home/away clubs. Missing scores stay null. A newly named competition also requires `competition_kind` and boolean `is_preseason`; the seven known competitions are already registered. The career uses July-June seasons, and exact match/snapshot dates are checked against their assigned season.

Player-performance records need a confirmed `match_id`, or a `match_source_id` that resolves to one approved match. The review command can propose a known match ID for explicitly selected performance images:

```sh
python3 -m career_data review --screenshots 74-87 --match 1 --output data/review/opening-check.json
```

This sets review context only. Verify the association visually before approval. The importer never guesses a player's match solely from the preceding filename.

For unimplemented layouts, the generated `records` list is empty and the source remains queued. Manual transcription into supported record types is possible: `match`, `player_match`, `player_snapshot`, `player_competition_snapshot`, `player_transfer`, and `competition_event`. An empty record list cannot be approved. See the existing pilot review in SQLite for examples; standings do not yet have a canonical table or importer.

4. Approve the checked document. The entire document is imported in one transaction; invalid fields, broken relationships, or conflicting known values roll back the batch. JSON for React is refreshed after approval.

```sh
python3 -m career_data approve data/review/wycombe-check.json --note "Describe what was checked against the original images"
python3 -m career_data validate
```

Do not run approval merely because OCR completed. In this first version, every new extraction requires visual review. Repeating an unchanged approval does not duplicate canonical records. Intentional corrections to previously known values require `--replace-reviewed`; do not use that flag for routine reruns. A later image of an existing player or fixture merges into its existing identity when the reviewed identifiers agree, or raises a conflict rather than overwriting a different observation.

### Maintenance commands

```sh
python3 -m career_data inventory
python3 -m career_data export
python3 -m career_data import --screenshots 108 --limit 1 --reextract
python3 -m career_data backup data/backups/manual-checkpoint.sqlite
python3 -m unittest discover -s tests -v
CAREER_OCR_TESTS=1 python3 -m unittest discover -s tests -v
```

- `inventory` performs no OCR. Source IDs are SHA-256 content hashes; different filenames for identical bytes share one source.
- `export` regenerates `data/exports/career.json`, including stable IDs, relationships, real boolean preseason flags, source references, and coverage counts. React can fetch this JSON without opening SQLite in the browser.
- `--reextract` refreshes machine candidates but never canonical records or reviewed corrections. Unsupported layouts and extraction errors remain visible for follow-up.
- `backup` uses SQLite's backup API and refuses an existing destination. Use a new name for each checkpoint. The current verified copy is `data/backups/2026-09-10-pilot.sqlite`.
- The default test command skips four real-image OCR tests. Setting `CAREER_OCR_TESTS=1` runs all 29 tests against the included original images as well as temporary-database tests.
- Global `--root` and `--db` options go before the subcommand, for example `python3 -m career_data --db data/career.sqlite status`.
- Source paths and crop coordinates are repository-relative and normalized. The extractor currently supports the observed 1366x768 layout and proportionally scaled 16:9 images; different aspect ratios are queued instead of using incorrect crop coordinates. Same-aspect layouts with different UI placement still require visual review.
- RapidOCR 1.2.3 exposes `text_recognizer(crops)`, not the newer `text_rec` interface. Its `use_det=False` call keyword does not disable detection. The implementation calls the pinned recognizer directly for numeric cells; keep this in mind before upgrading OCR.
- `rg` was unavailable in this terminal; use available workspace search tools. No system packages or editor extensions were installed.

## 7. Progress and Resume Checkpoint

### Milestones

- [x] Initial text inventory and representative source-image spot checks.
- [x] Record confirmed requirements, provisional findings, model, validation gates, and handoff process.
- [x] Inventory all 1,296 original images with hashes, dimensions, and readability checks in SQLite.
- [x] Implement and test extraction/review/import/export/backup commands.
- [x] Verify the opening preseason fixture and all 14 associated player-performance screens.
- [x] Verify the other pilot match headers, including shootout separation and the first League One fixture.
- [ ] Complete the player-performance groups for the remaining pilot fixtures.
- [x] Verify example opening/end-of-season player snapshots, season totals, and transfer/loan facts; retain incomplete source coverage.
- [x] Pass focused unit and real-screenshot validation for the implemented layouts and importer.
- [ ] Establish canonical identities, fixture boundaries, and season anchors.
- [ ] Extract and review all remaining screenshot families in batches.
- [ ] Reconcile match data against season snapshots and standings evidence.
- [x] Create and validate the SQLite import, including rerun/correction behavior and a backup.
- [x] Produce the first verified, explicitly partial JSON export and coverage counts.
- [ ] Build the React visualization application on the validated dataset.

### Latest checkpoint: 2026-09-10, first working importer

- Database: `data/career.sqlite`, schema version 1; approximately 1.4 MB at this checkpoint. Backup: `data/backups/2026-09-10-pilot.sqlite`. React export: `data/exports/career.json`.
- Inventory: 1,296 readable, distinct source images; no original screenshots modified or removed.
- Extracted/classified: 25 images. Source states: 19 `imported`, 6 `needs_review`, 1,271 `inventoried` and awaiting extraction.
- Canonical records: 16 players, 5 clubs, 2 seasons, 7 competitions, 6 competition editions, 4 matches, 8 team-match rows, 15 player-match rows, 17 player snapshots, 6 player-competition snapshots, 2 transfers, and 2 competition events.
- Complete Notts County player group: match 1 has 14 unique player-performance records. Their 1 goal, 1 assist, 5 shots on target, 1 shot off target, and goalkeeper's 1 goal conceded reconcile with the corresponding summary. Starting status and minutes remain unknown.
- Snapshot history includes Ramsdale's 2018/19 opening OVR 62 and closing OVR 65, with season-level date precision, plus 15 match-time OVR observations across the imported appearances. Captured season totals are stored separately, not added to appearance aggregates.
- Reviewed sources: 70, 73-87, 101, 108, 808, 1053, 1055, 1124, 1159, and 1231. Source 1054 was visually checked for May 2019 context and final standings but has no canonical record yet.
- Partial sources still queued: 70 and 1055 (other squad rows), 1053 (other news), 1124 and 1231 (dates, financial details, and profile/other offer rows), and 1054 (dashboard/standings).
- Transfer examples are Matty James, permanent, and Dominic Calvert-Lewin, loan. Unknown selling/lending clubs, year-qualified transfer dates, currency codes, and fees were not invented. Contract and loan durations are separate; displayed wages remain in source evidence pending financial normalization.
- Competition events: Notts County's 2018/19 League Two title and Ramsdale's goalkeeper award, both announced 2019-05-04. Other news headlines do not establish award recipients and were not guessed.
- Scratch review documents: `data/review/pilot.json` and `data/review/opening-match.json`. Approved payloads and review notes are stored in SQLite, so these files are not required to preserve approved data. They may be regenerated with `review` using a new filename.
- Validation completed: all 29 tests passed with `CAREER_OCR_TESTS=1`; SQLite integrity and foreign-key checks passed; reapproving the 14-player review skipped all 14 sources without duplicates; forced OCR refresh of source 108 preserved its reviewed zero assists and clearances; original-image Git diff was empty.
- Removed at user request: the legacy Python OCR script and 1,296 generated text files. The implementation, database, and current document changes have not been committed or pushed.

| Match ID | Date | Fixture and score | Competition edition | Imported player rows |
| --- | --- | --- | --- | ---: |
| 1 | 2018-07-04 | Notts County 1-1 Dundee FC | European International Cup 2018/19, preseason | 14 |
| 2 | 2018-07-08 | Livorno 0-1 Notts County | European International Cup 2018/19, preseason | 1 |
| 3 | 2019-02-14 | Notts County 0-0 Shrewsbury; 4-3 on penalties | Checkatrade Trophy 2018/19 | 0 |
| 4 | 2019-08-03 | Notts County 1-1 Wycombe | EFL League One 2019/20 | 0 |

### Exact next work

1. Read `status` and the existing database; do not reinitialize or delete it. The opening fixture is already reviewed and must not be recreated.
2. Complete the player screens around sources 808 and 1159 for matches 3 and 4, confirming their boundaries from images. The documented three-fixture pilot is not complete until those groups are reviewed. Match 2 also has only its goalkeeper so far.
3. Inspect the next-season Invitational Cup images and import that preseason edition; its competition is already registered with `is_preseason = true`, but no Invitational match has been imported yet.
4. Complete opening/closing squad snapshots for the other players, resolving aliases against the 16 existing identities. Keep uncertainty about exact observation dates explicit.
5. Improve the remaining cell-level OCR misses, particularly zero clearances and some goalkeeper assists, using image-based tests. Do not loosen validation or turn arbitrary missing values into zero.
6. Add and verify transfer/news/standings layouts as needed. Current automated extraction covers match facts, outfield performance, goalkeeper performance, and the selected squad profile only; other screens retain full OCR evidence for manual review.
7. Continue extraction in bounded batches and reconcile the full match history with captured competition totals and final standings. The archive is not yet ready to present as a complete career dataset.

### How to resume and update this document

1. Read this document and check the current worktree. Preserve unrelated user changes.
2. Read the latest checkpoint and SQLite source states, extractions, and reviews. Do not restart from screenshot 70 solely because it is the first image.
3. Inspect the most recent validated fixture and any pending partial batch before selecting new work. Use explicit source states, not just the largest filename processed.
4. Continue the next unchecked milestone. If evidence changes the schema or extraction approach, record the decision and reason here before broad reprocessing.
5. After every batch or significant decision, update the milestone status and checkpoint with source IDs, fixture IDs, completed counts by entity, unresolved IDs/reasons, commands/checks actually run, and the exact next action.
6. Record partial work and failures as well as successes. A future session should be able to resume without guessing what was imported or visually verified.

### Decision log

- 2026-09-10: Use the raw screenshots as primary evidence. Initial legacy OCR findings are retained here as historical discovery notes only.
- 2026-09-10: All matches, including preseason, must belong to a competition edition; `Competition.is_preseason` is required.
- 2026-09-10: Preserve player snapshots, particularly season-start/end OVR and their date certainty, instead of overwriting player attributes.
- 2026-09-10: Implement SQLite as the canonical application store, including structured OCR evidence, corrections, and progress. Export JSON for React; no backend API or React UI has been built yet.
- 2026-09-10: Remove the legacy OCR script and generated text at the user's request, while preserving every original screenshot.
- 2026-09-10: Require visual approval in this first importer version. Numeric crop extraction is useful but not sufficiently reliable for unattended canonical imports.
- 2026-09-10: Keep the database eligible for version control and provide explicit SQLite backups; ignore only scratch reviews, derived exports, journals, and local backup copies.
