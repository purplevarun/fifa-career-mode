# Notts County Career Data: Process and Handoff

Last updated: 2026-09-10

## 1. Goal and Confirmed Decisions

Build a trustworthy career dataset for a React application that visualizes Notts County match, player, season, and competition statistics.

- Original screenshots in `raw_data/` are the source of truth. Read the images, not just the existing OCR text.
- Include every captured match, including preseason games. Missing evidence must be tracked, not silently omitted.
- Every imported match must reference a competition edition. No orphan matches and no nullable competition relationship.
- Add `Competition.is_preseason` as a required boolean. Preseason tournaments are real competitions in this model.
- `Player_Match` is the central performance table, with one record per player per match.
- Player snapshots are essential: preserve season-start, season-end, and other dated observations of overall rating and player details.
- Recommended storage: SQLite for validated relational data; structured JSON for extraction evidence and exports to React.
- Preserve the current screenshots, text files, and OCR script. Do not overwrite them during the new extraction process.
- Build and validate the data pipeline before building the React application. A static JSON-backed app can come first; an editing API can come later.

Scope initially covers this one career save. If another save is added, introduce explicit career scoping before mixing records.

## 2. Current Evidence and Its Limits

The initial analysis scanned all existing text outputs and spot-checked two original player-performance screenshots. This is discovery work, not a completed screenshot extraction.

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

- There are 1,296 source image files and 1,296 text files. Equal counts do not establish a verified one-to-one mapping; build a manifest to check that.
- Text totals approximately 636 KB. There were no identical trimmed text outputs, but different OCR outputs can describe the same screen or match.
- Date and competition normalization produced 85 provisional fixture groups from 95 match summaries, spanning 2018-07-04 through 2019-11-02.
- Ten fixture groups have repeated summary captures. Do not import each summary as a new match.
- Provisional numeric screenshot groups contain 11-17 player-performance captures per match. These are not verified unique appearances.
- Text classification found 88 goalkeeper-performance screens and one opponent-performance screen: Sam Hoskins of Northampton in `Screenshot_976.txt`. Do not assume every player screen is a Notts County player.
- No complete identity resolution, fixture verification, player-row extraction, or database import has been performed.

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

- [The existing OCR script](process_images_to_text.py) keeps text only, discarding bounding boxes and recognition confidence.
- In [the Elliott Hewitt text sample](processed_data/Screenshot_1002.txt), visible zeroes were dropped and attacking/defending columns interleaved. The original image was spot-checked.
- [The Aaron Ramsdale sample](processed_data/Screenshot_108.txt) has a different goalkeeper layout. Its original image was also spot-checked.
- Some match summary text omits the score entirely. A missing score is not 0-0.
- OCR confuses labels and dates, including `Tw0`, `0ne`, `0ctober`, merged words, and missing spaces.
- Standings are partial dashboard snapshots, not a full archive of every club's results.
- Inspected performance screens do not establish minutes played or substitution times. Do not invent these or publish per-90 metrics without evidence.
- Squad season-total screens include disciplinary columns such as YC/RC; this does not establish when those cards happened in individual matches.
- Transfer screens mix weekly wages, contract terms, loan terms, and offer details. These are different fields.

## 3. Planned Data Model

Names below describe logical entities; implementation naming can follow consistent SQLite conventions. Use stable IDs independent of filenames, spelling corrections, ratings, and scores.

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

Starting candidates: the opening squad images corresponding to [Screenshot_70](processed_data/Screenshot_70.txt) and the end-of-season squad images around [Screenshot_1055](processed_data/Screenshot_1055.txt). Their apparent Aaron Ramsdale OVR observations are 62 and 65 respectively in text. These are candidates for image verification, not yet approved season-boundary records. Season 2019/20 end-of-season coverage is not established by this archive.

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
2. Check image readability, duplicate content, filename collisions, and correspondence with text outputs. Preserve original names and bytes; do not rename the archive.
3. Sort by numeric sequence for navigation, not lexical filename order. Filesystem timestamps are not in-game dates.
4. Classify from the images: match facts, outfield performance, goalkeeper performance, squad status/stats, transfer detail, news, career dashboard, competition result, or unknown.
5. Use existing text only as a navigation hint or secondary cross-check. Uncertain classification remains explicit in the manifest.
6. Track per-source state: inventoried, classified, extracted, needs_review, validated, imported, or error. A source with an error must remain visible in coverage reports.

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
3. Use image viewing and region crops as the primary extraction surface. Reuse the existing RapidOCR dependency if helpful, but retain its bounding boxes and confidence instead of flattening the output.
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
3. Preserve source associations for canonical records using appropriate junction tables. Detailed field-level evidence can remain in versioned extraction JSON linked from the database.
4. Use transactions and idempotent imports. Reprocessing unchanged sources must not create new players, matches, appearances, snapshots, or events.
5. Keep reviewed corrections separately from machine candidates. A rerun may propose a conflict, but must not erase a reviewed correction.
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

## 6. Planned Artifacts and Reproducibility

Only this document is being created at the documentation checkpoint. The following data artifacts and commands do not exist yet; settle their exact filenames while implementing the pilot.

```text
raw_data/                    existing immutable screenshots
processed_data/              existing legacy text, navigation only
process_images_to_text.py    existing script, unchanged
DATA_PROCESS.md              this living plan and handoff
data/
  source_manifest.json      image inventory and per-source progress
  staging/                  structured, source-linked extraction candidates
  corrections.json          explicit reviewed overrides and reasons
  review_queue.json         unresolved fields, identities, and associations
  career.sqlite             validated canonical data
  exports/                  versioned JSON for React
```

- Give extraction artifacts a schema version, extractor version, source hash, and timestamps. Crop/preprocessing settings must be reproducible.
- Store paths relative to the repository; do not encode a particular user's machine path into data.
- Choose and document runnable inventory, pilot, batch, validation, import, and export commands as they are implemented. Do not present unimplemented commands as ready to run.
- Prefer the existing Python direction and standard-library SQLite support; choose OCR changes based on pilot evidence. No new framework, hosted database, or remote image upload is required.
- Use a project-local environment for dependencies and record versions. Avoid changing the system Python or requiring administrator access.
- The current terminal has Node available, but `rg` was unavailable during initial analysis. Use available workspace search tools for inspection.
- Preserve originals and reviewed corrections as authoritative inputs. Generated outputs should be reproducible; inspect existing ignore rules before deciding which large artifacts to commit.

## 7. Progress and Resume Checkpoint

### Milestones

- [x] Initial text inventory and representative source-image spot checks.
- [x] Record confirmed requirements, provisional findings, model, validation gates, and handoff process.
- [ ] Inventory and classify every source image in a persistent manifest.
- [ ] Verify the three pilot fixtures and associated player screens directly from images.
- [ ] Verify opening/end-of-season squad snapshots and transfer/loan examples.
- [ ] Implement and pass structured extraction and validation for the pilot.
- [ ] Establish canonical identities, fixture boundaries, and season anchors.
- [ ] Extract and review all remaining screenshot families in batches.
- [ ] Reconcile match data against season snapshots and standings evidence.
- [ ] Create and validate the SQLite import, including rerun/correction behavior.
- [ ] Produce verified JSON exports and coverage summaries.
- [ ] Build the React visualization application on the validated dataset.

### Latest checkpoint: 2026-09-10, documentation

- Completed: initial discovery and this process specification.
- Source images spot-checked so far: `Screenshot (1002).png` and `Screenshot (108).png`, for OCR limitations only. Neither represents a fully extracted/validated fixture.
- Canonical fixtures imported: 0. Player-match records imported: 0. Player snapshots imported: 0.
- Last completed extraction batch: none. No source manifest, staging JSON, extraction implementation, SQLite database, or React application has been created.
- Existing data files and the legacy OCR script remain unchanged.
- Immediate next action: inventory the original images and begin the three-fixture pilot, starting with `Screenshot (73).png` and its visually confirmed player-screen sequence.
- Known open issues: reliable score/stat reading, repeat capture resolution, player identity variants, match-to-player linkage, exact snapshot dates, and incomplete/unreadable observations.

### How to resume and update this document

1. Read this document and check the current worktree. Preserve unrelated user changes.
2. Read the latest checkpoint plus the manifest and review queue, if implemented. Do not restart from screenshot 70 solely because this document contains an initial checkpoint.
3. Inspect the most recent validated fixture and any pending partial batch before selecting new work. Use explicit source states, not just the largest filename processed.
4. Continue the next unchecked milestone. If evidence changes the schema or extraction approach, record the decision and reason here before broad reprocessing.
5. After every batch or significant decision, update the milestone status and checkpoint with source IDs, fixture IDs, completed counts by entity, unresolved IDs/reasons, commands/checks actually run, and the exact next action.
6. Record partial work and failures as well as successes. A future session should be able to resume without guessing what was imported or visually verified.

### Decision log

- 2026-09-10: Use the raw screenshots as primary evidence; legacy OCR is a discovery aid only.
- 2026-09-10: All matches, including preseason, must belong to a competition edition; `Competition.is_preseason` is required.
- 2026-09-10: Preserve player snapshots, particularly season-start/end OVR and their date certainty, instead of overwriting player attributes.
- 2026-09-10: Recommend SQLite canonical storage with structured extraction JSON and frontend JSON exports; implementation waits for the screenshot pilot.
