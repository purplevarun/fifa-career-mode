import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  ArrowRightLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  ImageIcon,
  Search,
  Trophy,
  TriangleAlert,
} from "lucide-react";
import type { Comparison, Dataset, MetricComparison, Row } from "./data";
import {
  dateLabel,
  display,
  downloadJson,
  label,
  referenceLabel,
} from "./data";
import {
  CareerLink,
  DataTable,
  Empty,
  IconButton,
  Kpis,
  Modal,
  PageHeading,
  Pill,
  RecordDetails,
  SectionHeading,
  SourceButton,
  SourceImage,
} from "./ui";
import { useCareer } from "./context";
import type { Column } from "./ui";

export function CareerRecords() {
  const { model } = useCareer();
  const [tab, setTab] = useState("transfers"),
    [selected, setSelected] = useState<Row | null>(null);
  return (
    <>
      <PageHeading title="Career records" eyebrow="Transfers & honours" />
      <div className="tabs" role="tablist" aria-label="Career record types">
        {["transfers", "events"].map((value) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? "active" : ""}
            onClick={() => setTab(value)}
          >
            {value === "transfers"
              ? `Transfers (${model.data.player_transfers.length})`
              : `Honours & events (${model.data.competition_events.length})`}
          </button>
        ))}
      </div>
      {tab === "transfers" ? (
        <div className="transfer-list">
          {model.data.player_transfers.map((transfer) => (
            <article className="transfer-record" key={transfer.id}>
              <div className="transfer-icon">
                <ArrowRightLeft size={21} />
              </div>
              <div className="transfer-main">
                <div className="inline">
                  <Pill
                    tone={
                      transfer.transfer_type === "loan" ? "accent" : "neutral"
                    }
                  >
                    {label(String(transfer.transfer_type))}
                  </Pill>
                  <span className="muted tiny">
                    {typeof transfer.effective_on === "string"
                      ? dateLabel(transfer.effective_on)
                      : "Exact transfer date not recorded"}
                  </span>
                </div>
                <CareerLink to={`/players/${transfer.player_id}`}>
                  <h2>{model.players.get(String(transfer.player_id))?.name}</h2>
                </CareerLink>
                <p>
                  {transfer.from_club_id
                    ? model.clubs.get(String(transfer.from_club_id))?.name
                    : "Origin not recorded"}{" "}
                  <ArrowRight size={14} />{" "}
                  {transfer.to_club_id
                    ? model.clubs.get(String(transfer.to_club_id))?.name
                    : "Destination not recorded"}
                </p>
                <dl className="inline-facts">
                  <div>
                    <dt>Contract</dt>
                    <dd>
                      {transfer.contract_months == null
                        ? "-"
                        : `${transfer.contract_months} months`}
                    </dd>
                  </div>
                  <div>
                    <dt>Loan term</dt>
                    <dd>
                      {transfer.loan_months == null
                        ? "-"
                        : `${transfer.loan_months} months`}
                    </dd>
                  </div>
                  <div>
                    <dt>Fee</dt>
                    <dd>
                      {transfer.fee_minor == null
                        ? "Not recorded"
                        : `${transfer.currency ?? ""} ${display(Number(transfer.fee_minor) / 100, 2)}`}
                    </dd>
                  </div>
                </dl>
              </div>
              <div className="transfer-actions">
                <SourceButton sourceId={String(transfer.source_id)} />
                <button
                  className="button secondary"
                  onClick={() => setSelected(transfer)}
                >
                  Full record
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="event-list">
          {model.data.competition_events.map((event) => (
            <article className="event-record" key={event.id}>
              <div className="event-date">
                {typeof event.announced_on === "string"
                  ? dateLabel(event.announced_on)
                  : "Date not recorded"}
              </div>
              <Trophy size={24} className="event-icon" />
              <div>
                <div className="eyebrow">
                  {referenceLabel(
                    model,
                    "competition_season_id",
                    event.competition_season_id,
                  )}
                </div>
                <h2>{label(String(event.event_type))}</h2>
                <p>{String(event.description)}</p>
                {typeof event.player_id === "string" && (
                  <CareerLink
                    to={`/players/${event.player_id}`}
                    className="small-link"
                  >
                    {model.players.get(event.player_id)?.name}{" "}
                    <ArrowRight size={14} />
                  </CareerLink>
                )}
              </div>
              <SourceButton sourceId={String(event.source_id)} />
              <button
                className="button secondary"
                onClick={() => setSelected(event)}
              >
                Full record
              </button>
            </article>
          ))}
        </div>
      )}
      {selected && (
        <Modal title="Career record" onClose={() => setSelected(null)}>
          <RecordDetails record={selected} />
        </Modal>
      )}
    </>
  );
}

function MetricPair({
  metric,
  digits = 0,
}: {
  metric?: MetricComparison;
  digits?: number;
}) {
  if (!metric) return <span className="muted">-</span>;
  return (
    <span
      className={`metric-pair ${metric.result === "match" ? "positive-text" : metric.result === "mismatch" ? "negative-text" : "muted"}`}
      title={`${label(metric.result)}${metric.missing_match_values ? `; ${metric.missing_match_values} missing match values` : ""}${metric.raw_match_average != null ? `; raw mean ${metric.raw_match_average.toFixed(6)}` : ""}`}
    >
      {display(metric.observed, digits)} <span className="divider">/</span>{" "}
      {display(metric.derived, digits)}
      {metric.result === "match" && <Check size={12} />}
    </span>
  );
}
export function Audit() {
  const { model } = useCareer();
  const [tab, setTab] = useState("reconciliation"),
    [selected, setSelected] = useState<Row | null>(null);
  const [season, setSeason] = useState("all"),
    [scope, setScope] = useState("all");
  const comparisons = model.data.season_reconciliation.comparisons.filter(
    (row) =>
      (season === "all" || row.season === season) &&
      (scope === "all" || row.scope === scope),
  );
  const warnings = model.data.match_coverage.warnings;
  const coverage = model.data.match_coverage.summary;
  const columns: Column<Comparison>[] = [
    {
      key: "player",
      title: "Player",
      render: (row) => (
        <span className="stack">
          <strong>{row.player}</strong>
          <small className="muted">{row.season}</small>
        </span>
      ),
    },
    {
      key: "competition",
      title: "Competition",
      render: (row) => row.competition ?? "All competitions",
    },
    ...["appearances", "goals", "assists", "average_rating"].map((key) => ({
      key,
      title: key === "average_rating" ? "Avg rating" : label(key),
      numeric: true,
      value: (row: Comparison) => row.metrics[key]?.observed,
      render: (row: Comparison) => (
        <MetricPair
          metric={row.metrics[key]}
          digits={key === "average_rating" ? 1 : 0}
        />
      ),
    })),
    {
      key: "result",
      title: "Check",
      render: (row) => (
        <Pill
          tone={
            row.result === "match"
              ? "positive"
              : row.result === "mismatch"
                ? "negative"
                : "warning"
          }
        >
          {row.result === "match"
            ? "Matched"
            : row.result === "mismatch"
              ? "Difference"
              : "Partial"}
        </Pill>
      ),
    },
    {
      key: "source_id",
      title: "",
      sortable: false,
      render: (row) => <SourceButton sourceId={row.source_id} />,
    },
  ];
  return (
    <>
      <PageHeading title="Verification" eyebrow="Evidence & reconciliation">
        <IconButton
          label="Download verification reports"
          onClick={() =>
            downloadJson(
              {
                coverage: model.data.match_coverage,
                reconciliation: model.data.season_reconciliation,
              },
              "verification.json",
            )
          }
        >
          <Download size={18} />
        </IconButton>
      </PageHeading>
      <Kpis
        items={[
          {
            label: "Fixtures",
            value: String(coverage.matches),
            detail: `${model.data.match_sources.length} linked screenshots`,
          },
          {
            label: "Team records",
            value: model.data.team_matches.length,
            detail: "Both clubs / all fixtures",
          },
          {
            label: "Season comparisons",
            value: model.data.season_reconciliation.comparisons.length,
            detail: `${model.data.season_reconciliation.summary.mismatched_rows} mismatches`,
          },
          {
            label: "Open warnings",
            value: warnings.length,
            detail: "Goal attribution",
          },
        ]}
      />
      <div className="tabs" role="tablist" aria-label="Verification views">
        {[
          ["reconciliation", "Season reconciliation"],
          ["coverage", "Data coverage"],
          ["warnings", `Warnings (${warnings.length})`],
        ].map(([value, title]) => (
          <button
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? "active" : ""}
            key={value}
            onClick={() => setTab(value)}
          >
            {title}
          </button>
        ))}
      </div>
      {tab === "reconciliation" && (
        <>
          <SectionHeading title="Captured / match-derived">
            <div className="inline">
              <select
                aria-label="Reconciliation season"
                value={season}
                onChange={(event) => setSeason(event.target.value)}
              >
                <option value="all">All seasons</option>
                {model.data.seasons.map((season) => (
                  <option key={season.id} value={season.label}>
                    {season.label}
                  </option>
                ))}
              </select>
              <select
                aria-label="Reconciliation scope"
                value={scope}
                onChange={(event) => setScope(event.target.value)}
              >
                <option value="all">All scopes</option>
                <option value="all_competitions">Season totals</option>
                <option value="competition">By competition</option>
              </select>
            </div>
          </SectionHeading>
          <DataTable
            rows={comparisons}
            columns={columns}
            rowKey={(row) => row.snapshot_id}
            onSelect={setSelected}
            searchLabel="Search reconciliation records"
            searchText={(row) =>
              `${row.player} ${row.competition ?? "All competitions"} ${row.season} ${row.result}`
            }
            defaultSort={{ key: "player" }}
            exportName="season-reconciliation.json"
          />
          <div className="note-strip">
            <span>Rating display: one-decimal truncation.</span>
            <span>Goalkeeper scoring: nine comparisons unavailable.</span>
            <span>Zero-appearance averages: not applicable.</span>
          </div>
        </>
      )}
      {tab === "coverage" && (
        <div className="coverage-grid">
          <section>
            <SectionHeading title="Record availability" />
            <dl className="stats-list large">
              {Object.entries(model.data.coverage.records).map(
                ([name, count]) => (
                  <div key={name}>
                    <dt>{label(name)}</dt>
                    <dd>{display(count)}</dd>
                  </div>
                ),
              )}
            </dl>
          </section>
          <section>
            <SectionHeading title="Review scope" />
            <div className="notice positive">
              <Check size={18} />
              <div>
                <strong>All fixtures, team tables & player cores</strong>
                <p>
                  85 matches / 10 preseason / 1,131 Notts County appearances
                </p>
              </div>
            </div>
            <div className="notice warning">
              <TriangleAlert size={18} />
              <div>
                <strong>Detailed player fields remain partial</strong>
                <p>
                  Passing, defending, movement, opening squad records and some
                  career events.
                </p>
              </div>
            </div>
            <dl className="stats-list large">
              {Object.entries(
                model.data.match_coverage.player_field_availability,
              ).map(([field, detail]) => (
                <div key={field}>
                  <dt>{label(field)}</dt>
                  <dd>
                    {String((detail as Row).recorded)} recorded /{" "}
                    {String((detail as Row).null)} missing
                  </dd>
                </div>
              ))}
            </dl>
            <SectionHeading title="Screenshot review states" />
            <dl className="stats-list">
              {Object.entries(model.data.coverage.source_states).map(
                ([state, count]) => (
                  <div key={state}>
                    <dt>{label(state)}</dt>
                    <dd>{count}</dd>
                  </div>
                ),
              )}
            </dl>
          </section>
        </div>
      )}
      {tab === "warnings" && (
        <div>
          {warnings.length ? (
            warnings.map((warning, index) => (
              <section className="warning-record" key={index}>
                <TriangleAlert size={22} />
                <div>
                  <div className="eyebrow">{String(warning.played_on)}</div>
                  <h2>
                    {String(warning.home_club)} / {String(warning.away_club)}
                  </h2>
                  <p>
                    Team goals: <strong>{String(warning.team_goals)}</strong>.
                    Credited player goals:{" "}
                    <strong>{String(warning.credited_player_goals)}</strong>.
                  </p>
                  <p className="muted">{String(warning.detail)}</p>
                  <CareerLink
                    to={`/matches/${warning.match_id}`}
                    className="button secondary"
                  >
                    Open match <ArrowRight size={15} />
                  </CareerLink>
                </div>
              </section>
            ))
          ) : (
            <Empty title="No reconciliation warnings" />
          )}
        </div>
      )}
      {selected && (
        <Modal
          title={`${selected.player ?? "Record"} / reconciliation`}
          onClose={() => setSelected(null)}
          wide
        >
          <RecordDetails record={selected} />
        </Modal>
      )}
    </>
  );
}

const tableNames = [
  "matches",
  "player_matches",
  "players",
  "team_matches",
  "player_snapshots",
  "player_competition_snapshots",
  "clubs",
  "competitions",
  "competition_seasons",
  "seasons",
  "player_transfers",
  "competition_events",
  "source_images",
  "match_sources",
  "player_match_sources",
] as const;
type TableName = (typeof tableNames)[number];
export function Explorer() {
  const { model } = useCareer();
  const [parameters, setParameters] = useSearchParams();
  const parameter = parameters.get("table");
  const table: TableName = tableNames.includes(parameter as TableName)
    ? (parameter as TableName)
    : "matches";
  const [selected, setSelected] = useState<Row | null>(null);
  const rows = model.data[table] as unknown as Row[];
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const columns: Column<Row>[] = keys.map((key, index) => ({
    key,
    title: label(key),
    value: (row) => row[key],
    numeric: rows.some((row) => typeof row[key] === "number"),
    render: (row) => {
      const value = row[key],
        resolved = referenceLabel(model, key, value);
      if (value === null)
        return (
          <span className="null-value" title="Not recorded or not applicable">
            null
          </span>
        );
      if (typeof value === "object")
        return (
          <span className="muted">
            {Array.isArray(value) ? `${value.length} items` : "Object"}
          </span>
        );
      if (index > 0 && typeof value === "string") {
        if (key === "source_id") return <SourceButton sourceId={value} text />;
        if (key === "player_id")
          return <CareerLink to={`/players/${value}`}>{resolved}</CareerLink>;
        if (key === "match_id")
          return <CareerLink to={`/matches/${value}`}>{resolved}</CareerLink>;
      }
      return (
        <span
          className={
            key === "id" ||
            (key.endsWith("_id") && resolved === value) ||
            key === "sha256"
              ? "short-id"
              : "raw-cell"
          }
          title={String(value)}
        >
          {key === "id" || key === "sha256"
            ? `${String(value).slice(0, 8)}...`
            : resolved}
        </span>
      );
    },
  }));
  return (
    <>
      <PageHeading title="Data explorer" eyebrow="Complete structured export">
        <IconButton
          label="Download complete dataset"
          onClick={() => downloadJson(model.data, "career.json")}
        >
          <Download size={18} />
        </IconButton>
      </PageHeading>
      <div className="dataset-selector">
        <label>
          Table
          <select
            aria-label="Dataset table"
            value={table}
            onChange={(event) => {
              setParameters({ table: event.target.value });
              setSelected(null);
            }}
          >
            {tableNames.map((table) => (
              <option key={table} value={table}>
                {label(table)} ({model.data[table].length})
              </option>
            ))}
          </select>
        </label>
        <span className="muted">
          Schema {model.data.schema_version} / {keys.length} fields / UUID
          identifiers
        </span>
      </div>
      <DataTable
        key={table}
        rows={rows}
        columns={columns}
        rowKey={(row) =>
          typeof row.id === "string" ? row.id : Object.values(row).join(":")
        }
        onSelect={setSelected}
        searchLabel={`Search ${label(table).toLowerCase()}`}
        searchText={(row) =>
          `${JSON.stringify(row)} ${Object.entries(row)
            .map(([key, value]) => referenceLabel(model, key, value))
            .join(" ")}`
        }
        exportName={`${table}.json`}
      />
      {selected && (
        <Modal
          title={label(table) + " / record"}
          onClose={() => setSelected(null)}
          wide
        >
          <RecordDetails record={selected} />
          <div className="dialog-actions">
            <button
              className="button secondary"
              onClick={() => downloadJson(selected, `${table}-record.json`)}
            >
              <Download size={15} />
              Download record
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

export function Evidence() {
  const { model, openSource } = useCareer();
  const [query, setQuery] = useState(""),
    [type, setType] = useState("all"),
    [status, setStatus] = useState("all"),
    [page, setPage] = useState(0);
  const types = [
    ...new Set(model.data.source_images.map((source) => source.screen_type)),
  ].sort();
  const sources = model.data.source_images
    .filter(
      (source) =>
        (type === "all" || source.screen_type === type) &&
        (status === "all" || source.status === status) &&
        `${source.path} ${source.id}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((left, right) =>
      left.path.localeCompare(right.path, undefined, { numeric: true }),
    );
  const pages = Math.max(1, Math.ceil(sources.length / 18)),
    current = Math.min(page, pages - 1);
  return (
    <>
      <PageHeading title="Source images" eyebrow="Original evidence archive">
        <Pill>{display(model.data.source_images.length)} screenshots</Pill>
      </PageHeading>
      <div className="table-toolbar">
        <label className="search-field">
          <Search size={16} />
          <input
            aria-label="Search screenshots"
            placeholder="Screenshot number or UUID"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
          />
        </label>
        <div className="table-tools">
          <select
            aria-label="Screenshot type"
            value={type}
            onChange={(event) => {
              setType(event.target.value);
              setPage(0);
            }}
          >
            <option value="all">All screen types</option>
            {types.map((type) => (
              <option key={type} value={type}>
                {label(type)}
              </option>
            ))}
          </select>
          <select
            aria-label="Source review status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(0);
            }}
          >
            <option value="all">All review states</option>
            <option value="imported">Fully reviewed</option>
            <option value="needs_review">Partial review</option>
          </select>
        </div>
      </div>
      <div className="source-grid">
        {sources.slice(current * 18, (current + 1) * 18).map((source) => (
          <button
            className="source-tile"
            key={source.id}
            onClick={() => openSource(source.id)}
          >
            <SourceImage source={source} />
            <span className="source-caption">
              <strong>{source.path.split("/").at(-1)}</strong>
              <ImageIcon size={15} />
              <small>{label(source.screen_type)}</small>
              <span
                className={`review-dot ${source.status === "imported" ? "complete" : ""}`}
                title={label(source.status)}
              />
            </span>
          </button>
        ))}
      </div>
      {!sources.length && <Empty title="No matching screenshots" />}
      <div className="pagination">
        <span>{display(sources.length)} sources</span>
        <div>
          <IconButton
            label="Previous screenshots"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            <ChevronLeft size={17} />
          </IconButton>
          <span>
            {current + 1} / {pages}
          </span>
          <IconButton
            label="Next screenshots"
            disabled={current + 1 >= pages}
            onClick={() => setPage(current + 1)}
          >
            <ChevronRight size={17} />
          </IconButton>
        </div>
      </div>
    </>
  );
}

export type AvailableTables = Pick<Dataset, TableName>;
