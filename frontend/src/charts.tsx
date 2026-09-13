import {
	Area,
	Bar,
	BarChart,
	CartesianGrid,
	ComposedChart,
	Legend,
	LabelList,
	Line,
	ResponsiveContainer,
	Text,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import type { Row } from "./data";
import { display } from "./data";
import { Empty } from "./ui";

export function TrendChart({
	rows,
	series,
	labelKey = "label",
	domain,
	height = 248,
}: {
	rows: Row[];
	series: { key: string; name: string; color: string }[];
	labelKey?: string;
	domain?: [number | string, number | string];
	height?: number;
}) {
	if (!rows.length) return <Empty title="No chart data in this selection" />;
	return (
		<div
			className="chart"
			style={{ height }}
			role="img"
			aria-label={
				series.map((series) => series.name).join(" and ") +
				" over recorded matches"
			}
		>
			<ResponsiveContainer width="100%" height="100%" minWidth={1}>
				<ComposedChart
					data={rows}
					margin={{ top: 15, right: 12, left: -16, bottom: 0 }}
					accessibilityLayer
				>
					<CartesianGrid vertical={false} stroke="#e8e9e6" />
					<XAxis
						dataKey={labelKey}
						tickLine={false}
						axisLine={false}
						minTickGap={34}
						tick={{ fontSize: 11, fill: "#73766f" }}
					/>
					<YAxis
						domain={domain}
						allowDecimals={false}
						tickLine={false}
						axisLine={false}
						tick={{ fontSize: 11, fill: "#73766f" }}
						width={42}
					/>
					<Tooltip
						contentStyle={{
							border: "1px solid #dadfd8",
							borderRadius: 4,
							fontSize: 12,
						}}
					/>
					<Legend
						iconType="plainline"
						wrapperStyle={{ fontSize: 12, paddingTop: 10 }}
					/>
					{series.map((series, index) =>
						index === 0 ? (
							<Area
								key={series.key}
								type="linear"
								dataKey={series.key}
								name={series.name}
								stroke={series.color}
								fill={series.color}
								fillOpacity={0.08}
								strokeWidth={2}
								dot={rows.length < 18}
								isAnimationActive={false}
								connectNulls={false}
							/>
						) : (
							<Line
								key={series.key}
								type="linear"
								dataKey={series.key}
								name={series.name}
								stroke={series.color}
								strokeWidth={2}
								dot={rows.length < 18}
								isAnimationActive={false}
								connectNulls={false}
							/>
						),
					)}
				</ComposedChart>
			</ResponsiveContainer>
		</div>
	);
}
function RankingMarker({
	x = 0,
	y = 0,
	width = 0,
	height = 0,
	fill = "#276f54",
	stem = true,
}: {
	x?: number;
	y?: number;
	width?: number;
	height?: number;
	fill?: string;
	stem?: boolean;
}) {
	const center = y + height / 2;
	return (
		<g>
			{stem && (
				<line
					x1={x}
					y1={center}
					x2={x + width}
					y2={center}
					stroke={fill}
					strokeWidth={3}
				/>
			)}
			<circle
				cx={x + width}
				cy={center}
				r={5}
				fill={fill}
				stroke="white"
				strokeWidth={1.5}
			/>
		</g>
	);
}

function RankingName({
	x = 0,
	y = 0,
	payload,
}: {
	x?: number;
	y?: number;
	payload?: { value: string };
}) {
	return (
		<Text
			x={x - 10}
			y={y}
			width={124}
			textAnchor="end"
			verticalAnchor="middle"
			style={{ fontSize: 12, fill: "#3d423c" }}
		>
			{payload?.value ?? ""}
		</Text>
	);
}

export function RankingChart({
	rows,
	name = "Goals",
	color = "#276f54",
	variant = "bar",
	digits = 0,
}: {
	rows: { name: string; value: number; known?: number; total?: number }[];
	name?: string;
	color?: string;
	variant?: "bar" | "lollipop" | "rating";
	digits?: number;
}) {
	const partial = (row: (typeof rows)[number]) =>
		row.known !== undefined &&
		row.total !== undefined &&
		row.known < row.total;
	const plotted = rows.map((row) => ({
		...row,
		displayValue: `${display(row.value, digits)}${partial(row) ? "*" : ""}`,
	}));
	const maximum =
		variant === "rating"
			? 10
			: Math.max(1, ...rows.map((row) => row.value));
	return (
		<div
			className="ranking-visual"
			data-ranking-variant={variant}
			data-ranking-count={rows.length}
		>
			<div
				className="chart ranking-chart"
				style={{ height: 248 }}
				role="img"
				aria-label={`${name} by player. ${rows.map((row) => `${row.name}: ${display(row.value, digits)}${partial(row) ? `, ${row.known} of ${row.total} appearances recorded` : ""}`).join("; ")}`}
			>
				{!rows.length ? (
					<Empty
						title={`No recorded ${name.toLowerCase()} in this selection`}
					/>
				) : (
					<ResponsiveContainer
						width="100%"
						height="100%"
						minWidth={1}
					>
						<BarChart
							data={plotted}
							layout="vertical"
							margin={{ left: 0, right: 44, top: 8, bottom: 0 }}
							accessibilityLayer
						>
							<CartesianGrid
								horizontal={false}
								vertical={variant === "bar"}
								stroke="#e8e9e6"
							/>
							<XAxis
								type="number"
								domain={[0, maximum]}
								height={24}
								axisLine={false}
								tickLine={false}
								ticks={
									variant === "rating"
										? [0, 5, 10]
										: undefined
								}
								tick={
									variant === "rating"
										? { fontSize: 10, fill: "#73766f" }
										: false
								}
							/>
							<YAxis
								dataKey="name"
								type="category"
								tickLine={false}
								axisLine={false}
								width={136}
								interval={0}
								tick={<RankingName />}
							/>
							<Tooltip
								cursor={{ fill: "#f1f4ef" }}
								content={({ active, payload }) => {
									const row = payload?.[0]?.payload as
										(typeof rows)[number] | undefined;
									return active && row ? (
										<div className="ranking-tooltip">
											<strong>{row.name}</strong>
											<span>
												{name}:{" "}
												{display(row.value, digits)}
											</span>
											{row.known !== undefined &&
												row.total !== undefined && (
													<small>
														{row.known}/{row.total}{" "}
														appearances recorded
													</small>
												)}
										</div>
									) : null;
								}}
							/>
							<Bar
								dataKey="value"
								name={name}
								fill={color}
								barSize={variant === "bar" ? 16 : 3}
								radius={[0, 2, 2, 0]}
								background={{ fill: "#eef1ec" }}
								shape={
									variant === "bar" ? undefined : (
										<RankingMarker
											stem={variant === "lollipop"}
										/>
									)
								}
								isAnimationActive={false}
							>
								<LabelList
									dataKey="displayValue"
									position="right"
									offset={variant === "bar" ? 6 : 11}
									fill="#343b35"
									fontSize={12}
								/>
							</Bar>
						</BarChart>
					</ResponsiveContainer>
				)}
			</div>
			<div className="ranking-note">
				{rows.some(partial) ? "* Partial data" : ""}
			</div>
		</div>
	);
}
