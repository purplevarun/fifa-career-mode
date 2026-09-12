import {
	ArrowDown,
	ArrowUp,
	ArrowUpDown,
	ChevronLeft,
	ChevronRight,
	Download,
	Search,
	X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useDeferredValue, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useCareer } from "./context";
import type { Match, Row } from "./data";
import { display, downloadJson, label, referenceLabel } from "./data";
export function CareerLink({
	to,
	children,
	...props
}: {
	to: string;
	children: ReactNode;
	className?: string;
	title?: string;
}) {
	const location = useLocation();
	return (
		<Link to={`${to}${location.search}`} {...props}>
			{children}
		</Link>
	);
}
export function IconButton({
	label: title,
	children,
	onClick,
	disabled = false,
	className = "",
}: {
	label: string;
	children: ReactNode;
	onClick?: () => void;
	disabled?: boolean;
	className?: string;
}) {
	return (
		<button
			type="button"
			className={`icon-button ${className}`}
			title={title}
			aria-label={title}
			onClick={onClick}
			disabled={disabled}
		>
			{children}
		</button>
	);
}
export function Pill({
	children,
	tone = "neutral",
}: {
	children: ReactNode;
	tone?: string;
}) {
	return <span className={`pill ${tone}`}>{children}</span>;
}
export function Result({ match }: { match: Match }) {
	return (
		<span className="result-wrap">
			<Pill
				tone={
					match.result === "W"
						? "positive"
						: match.result === "L"
							? "negative"
							: "neutral"
				}
			>
				{match.result ?? "-"}
			</Pill>
			{match.shootout && (
				<span
					className="tiny"
					title="Penalty shootout result, separate from the drawn match"
				>
					Pens {match.shootout}
				</span>
			)}
		</span>
	);
}
export function StatValue({
	value,
	known,
	total,
	digits = 0,
}: {
	value: number | null;
	known?: number;
	total?: number;
	digits?: number;
}) {
	const partial =
		known !== undefined &&
		total !== undefined &&
		known > 0 &&
		known < total;
	return (
		<span
			className="number"
			title={
				value === null
					? "Not recorded or not applicable"
					: partial
						? `${known} of ${total} records available`
						: undefined
			}
		>
			{display(value, digits)}
			{partial && <sup aria-label="partial data">*</sup>}
		</span>
	);
}
export function PageHeading({
	title,
	eyebrow,
	children,
}: {
	title: string;
	eyebrow?: string;
	children?: ReactNode;
}) {
	return (
		<header className="page-heading">
			<div>
				{eyebrow && <div className="eyebrow">{eyebrow}</div>}
				<h1>{title}</h1>
			</div>
			<div className="heading-actions">{children}</div>
		</header>
	);
}
export function SectionHeading({
	title,
	children,
}: {
	title: string;
	children?: ReactNode;
}) {
	return (
		<div className="section-heading">
			<h2>{title}</h2>
			{children}
		</div>
	);
}
export function Empty({
	title = "No records in this selection",
	detail,
}: {
	title?: string;
	detail?: string;
}) {
	return (
		<div className="empty-state">
			<Search size={22} />
			<h3>{title}</h3>
			{detail && <p>{detail}</p>}
		</div>
	);
}
export function Kpis({
	items,
}: {
	items: { label: string; value: ReactNode; detail?: ReactNode }[];
}) {
	return (
		<div className="kpi-strip">
			{items.map((item) => (
				<div className="kpi" key={item.label}>
					<span className="eyebrow">{item.label}</span>
					<strong>{item.value}</strong>
					<span className="muted">{item.detail}</span>
				</div>
			))}
		</div>
	);
}
export interface Column<Value> {
	key: string;
	title: string;
	value?: (row: Value) => unknown;
	render?: (row: Value) => ReactNode;
	numeric?: boolean;
	sortable?: boolean;
	className?: string;
}
export function DataTable<Value extends Row>({
	rows,
	columns,
	rowKey,
	searchLabel = "Search records",
	searchText,
	defaultSort,
	pageSize = 20,
	onSelect,
	toolbar,
	exportName,
}: {
	rows: Value[];
	columns: Column<Value>[];
	rowKey: (row: Value) => string;
	searchLabel?: string;
	searchText?: (row: Value) => string;
	defaultSort?: { key: string; desc?: boolean };
	pageSize?: number;
	onSelect?: (row: Value) => void;
	toolbar?: ReactNode;
	exportName?: string;
}) {
	const [query, setQuery] = useState("");
	const deferredQuery = useDeferredValue(query);
	const [sort, setSort] = useState(
		defaultSort ?? { key: columns[0]?.key, desc: false },
	);
	const [page, setPage] = useState(0);
	const [size, setSize] = useState(pageSize);
	const text = deferredQuery.trim().toLocaleLowerCase();
	const filtered = text
		? rows.filter((row) =>
			(searchText?.(row) ?? JSON.stringify(row))
				.toLocaleLowerCase()
				.includes(text),
		)
		: rows;
	const column = columns.find((column) => column.key === sort.key);
	const valueOf = (row: Value) =>
		column?.value ? column.value(row) : row[sort.key];
	const sorted = [...filtered].sort((left, right) => {
		const first = valueOf(left),
			second = valueOf(right);
		if (first == null) return second == null ? 0 : 1;
		if (second == null) return -1;
		const comparison =
			typeof first === "number" && typeof second === "number"
				? first - second
				: String(first).localeCompare(String(second), undefined, {
					numeric: true,
				});
		return sort.desc ? -comparison : comparison;
	});
	const pages = Math.max(1, Math.ceil(sorted.length / size)),
		currentPage = Math.min(page, pages - 1);
	const visible = sorted.slice(currentPage * size, (currentPage + 1) * size);
	return (
		<div className="data-table">
			<div className="table-toolbar">
				<label className="search-field">
					<Search size={16} />
					<input
						aria-label={searchLabel}
						placeholder={searchLabel}
						value={query}
						onChange={(event) => {
							setQuery(event.target.value);
							setPage(0);
						}}
					/>
					{query && (
						<button
							className="clear-search"
							aria-label="Clear search"
							onClick={() => {
								setQuery("");
								setPage(0);
							}}
						>
							<X size={14} />
						</button>
					)}
				</label>
				<div className="table-tools">
					{toolbar}
					<span className="record-count">
						{display(filtered.length)} records
					</span>
					{exportName && (
						<IconButton
							label="Download filtered records"
							onClick={() => downloadJson(sorted, exportName)}
						>
							<Download size={16} />
						</IconButton>
					)}
				</div>
			</div>
			<div
				className="table-scroll"
				tabIndex={0}
				role="region"
				aria-label={searchLabel.replace("Search", "").trim() + " table"}
			>
				<table>
					<thead>
						<tr>
							{columns.map((column) => (
								<th
									key={column.key}
									className={`${column.numeric ? "numeric" : ""} ${column.className ?? ""}`}
									aria-sort={
										sort.key === column.key
											? sort.desc
												? "descending"
												: "ascending"
											: "none"
									}
								>
									{column.sortable === false ? (
										column.title
									) : (
										<button
											className="sort-control"
											onClick={() => {
												setSort({
													key: column.key,
													desc:
														sort.key === column.key
															? !sort.desc
															: Boolean(
																column.numeric,
															),
												});
												setPage(0);
											}}
										>
											{column.title}
											{sort.key === column.key ? (
												sort.desc ? (
													<ArrowDown size={12} />
												) : (
													<ArrowUp size={12} />
												)
											) : (
												<ArrowUpDown
													size={12}
													className="sort-idle"
												/>
											)}
										</button>
									)}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{visible.map((row) => (
							<tr key={rowKey(row)}>
								{columns.map((column, index) => (
									<td
										key={column.key}
										className={`${column.numeric ? "numeric" : ""} ${column.className ?? ""}`}
									>
										{onSelect && index === 0 ? (
											<button
												className="text-link"
												onClick={() => onSelect(row)}
											>
												{column.render
													? column.render(row)
													: display(
														column.value?.(
															row,
														) ??
														row[column.key],
													)}
											</button>
										) : column.render ? (
											column.render(row)
										) : (
											display(
												column.value?.(row) ??
												row[column.key],
											)
										)}
									</td>
								))}
							</tr>
						))}
					</tbody>
				</table>
			</div>
			{!visible.length && <Empty />}
			<div className="pagination">
				<span>
					{filtered.length
						? `${currentPage * size + 1}-${Math.min((currentPage + 1) * size, filtered.length)} of ${display(filtered.length)}`
						: "0 records"}
				</span>
				<div>
					<label className="page-size">
						Rows{" "}
						<select
							aria-label="Rows per page"
							value={size}
							onChange={(event) => {
								setSize(Number(event.target.value));
								setPage(0);
							}}
						>
							{[10, 20, 50, 100].map((count) => (
								<option key={count}>{count}</option>
							))}
						</select>
					</label>
					<IconButton
						label="Previous page"
						disabled={currentPage === 0}
						onClick={() => setPage(currentPage - 1)}
					>
						<ChevronLeft size={17} />
					</IconButton>
					<span className="page-count">
						{currentPage + 1} / {pages}
					</span>
					<IconButton
						label="Next page"
						disabled={currentPage + 1 >= pages}
						onClick={() => setPage(currentPage + 1)}
					>
						<ChevronRight size={17} />
					</IconButton>
				</div>
			</div>
		</div>
	);
}
export function Modal({
	title,
	children,
	onClose,
	wide = false,
}: {
	title: string;
	children: ReactNode;
	onClose: () => void;
	wide?: boolean;
}) {
	const dialog = useRef<HTMLDialogElement>(null);
	useEffect(() => {
		const element = dialog.current;
		element?.showModal();
		return () => element?.close();
	}, []);
	return (
		<dialog
			ref={dialog}
			className={`modal ${wide ? "wide" : ""}`}
			aria-label={title}
			onCancel={(event) => {
				event.preventDefault();
				onClose();
			}}
			onClick={(event) => {
				if (event.target === event.currentTarget) {
					const bounds = event.currentTarget.getBoundingClientRect();
					if (
						event.clientX < bounds.left ||
						event.clientX > bounds.right ||
						event.clientY < bounds.top ||
						event.clientY > bounds.bottom
					)
						onClose();
				}
			}}
		>
			<div className="modal-heading">
				<h2>{title}</h2>
				<IconButton label="Close dialog" onClick={onClose}>
					<X size={20} />
				</IconButton>
			</div>
			<div className="modal-body">{children}</div>
		</dialog>
	);
}
export function RecordDetails({ record }: { record: Row }) {
	const { model } = useCareer();
	return (
		<dl className="record-details">
			{Object.entries(record).map(([field, value]) => (
				<div key={field}>
					<dt>{label(field)}</dt>
					<dd>
						{value !== null && typeof value === "object" ? (
							<pre>{JSON.stringify(value, null, 2)}</pre>
						) : (
							<>
								<span
									className={
										field === "id" || field.endsWith("_id")
											? "code-value"
											: ""
									}
								>
									{referenceLabel(model, field, value)}
								</span>
								{field.endsWith("_id") && value && (
									<small className="code-value muted">
										{String(value)}
									</small>
								)}
							</>
						)}
					</dd>
				</div>
			))}
		</dl>
	);
}
