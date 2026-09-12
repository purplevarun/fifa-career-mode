import {
	Area,
	Bar,
	BarChart,
	CartesianGrid,
	ComposedChart,
	Legend,
	Line,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import type { Row } from "./data";
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
export function RankingChart({
	rows,
	name = "Goals",
}: {
	rows: { name: string; value: number }[];
	name?: string;
}) {
	if (!rows.length)
		return <Empty title="No recorded goals in this selection" />;
	return (
		<div
			className="chart"
			style={{ height: 248 }}
			role="img"
			aria-label={`${name} by player`}
		>
			<ResponsiveContainer width="100%" height="100%" minWidth={1}>
				<BarChart
					data={rows}
					layout="vertical"
					margin={{ left: 0, right: 26, top: 5, bottom: 0 }}
					accessibilityLayer
				>
					<CartesianGrid horizontal={false} stroke="#e8e9e6" />
					<XAxis type="number" hide />
					<YAxis
						dataKey="name"
						type="category"
						tickLine={false}
						axisLine={false}
						width={132}
						tick={{ fontSize: 12, fill: "#3d423c" }}
					/>
					<Tooltip
						cursor={{ fill: "#f1f4ef" }}
						contentStyle={{
							fontSize: 12,
							borderRadius: 4,
							borderColor: "#d9dfd6",
						}}
					/>
					<Bar
						dataKey="value"
						name={name}
						fill="#276f54"
						barSize={17}
						radius={[0, 2, 2, 0]}
						label={{
							position: "right",
							fill: "#343b35",
							fontSize: 12,
						}}
						isAnimationActive={false}
					/>
				</BarChart>
			</ResponsiveContainer>
		</div>
	);
}
