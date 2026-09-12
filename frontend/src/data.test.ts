import { describe, expect, it } from "vitest";
import { fixture as data } from "../tests/fixture";
import {
	createModel,
	defaultFilters,
	metric,
	performanceMetric,
	selectMatches,
	selectPerformances,
	summarize,
} from "./data";

const model = createModel(data);
describe("career data calculations", () => {
	it("includes every fixture and preserves preseason filtering", () => {
		expect(selectMatches(model, defaultFilters)).toHaveLength(4);
		expect(
			selectMatches(model, { ...defaultFilters, preseason: false }),
		).toHaveLength(3);
	});
	it("uses unique appearances and keeps opponent records out of Notts totals", () => {
		expect(selectPerformances(model, model.matches)).toHaveLength(4);
		expect(selectPerformances(model, model.matches, null)).toHaveLength(5);
	});
	it("calculates league points separately from cups and preseason", () => {
		const league = model.data.competitions.find(
			(competition) => competition.name === "EFL League Two",
		)!;
		const summary = summarize(
			selectMatches(model, { ...defaultFilters, competition: league.id }),
		);
		expect(summary.played).toBe(2);
		expect(summary.leaguePoints).toBe(4);
	});
	it("does not count shootout goals as match goals or draws as wins", () => {
		const match = model.matches.find(
			(match) => match.played_on === "2019-02-14",
		)!;
		expect(match.result).toBe("D");
		expect(match.shootout).toBe("W");
		expect(summarize([match]).goalsFor.value).toBe(0);
	});
	it("retains unknown values and exposes partial sums", () => {
		expect(metric([{ goals: null }], "goals")).toEqual({
			value: null,
			known: 0,
			total: 1,
		});
		expect(metric([{ goals: 0 }, { goals: null }], "goals")).toEqual({
			value: 0,
			known: 1,
			total: 2,
		});
		const goalkeeper = model.data.players.find(
			(player) => player.name === "Test Goalkeeper",
		)!;
		expect(
			metric(
				selectPerformances(model, model.matches).filter(
					(row) => row.player_id === goalkeeper.id,
				),
				"goals",
			).value,
		).toBeNull();
	});
	it("sums passing components only for fully recorded appearances", () => {
		const fields = [
			"passes_completed_short",
			"passes_completed_medium",
			"passes_completed_long",
		];
		expect(
			metric(
				[
					{
						passes_completed_short: 5,
						passes_completed_medium: 4,
						passes_completed_long: 1,
					},
					{
						passes_completed_short: 4,
						passes_completed_medium: null,
						passes_completed_long: 1,
					},
					{
						passes_completed_short: 0,
						passes_completed_medium: 0,
						passes_completed_long: 0,
					},
					{},
				],
				fields,
			),
		).toEqual({ value: 10, known: 2, total: 4 });
		expect(metric([], fields)).toEqual({ value: null, known: 0, total: 0 });
		expect(
			metric([{ passes_completed_short: Number.NaN }], fields).value,
		).toBeNull();
	});
	it("distinguishes attempted and completed passes without summing percentages", () => {
		const rows = [
			{
				passes_completed_short: 5,
				passes_completed_medium: 4,
				passes_completed_long: 1,
				passes_failed_short: 2,
				passes_failed_medium: 1,
				passes_failed_long: 0,
				key_passes: 2,
				interceptions: 3,
			},
		];
		expect(performanceMetric(rows, "passes_completed").value).toBe(10);
		expect(performanceMetric(rows, "passes_attempted").value).toBe(13);
		expect(performanceMetric(rows, "passes_failed").value).toBe(3);
		expect(performanceMetric(rows, "key_passes").value).toBe(2);
		expect(performanceMetric(rows, "interceptions").value).toBe(3);
		expect(
			performanceMetric(
				[{ ...rows[0], passes_failed_long: null }],
				"passes_attempted",
			).value,
		).toBeNull();
	});
	it("rejects unsupported exports and missing relationships", () => {
		expect(() => createModel({ ...data, schema_version: 2 })).toThrow(
			/schema-version/,
		);
		expect(() => createModel({ ...data, seasons: [] })).toThrow(
			/relationship/,
		);
	});
});
