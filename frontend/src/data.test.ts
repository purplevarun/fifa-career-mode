import { describe, expect, it } from "vitest";
import { fixture as data } from "../tests/fixture";
import {
	createModel,
	defaultFilters,
	metric,
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
	it("rejects unsupported exports and missing relationships", () => {
		expect(() => createModel({ ...data, schema_version: 2 })).toThrow(
			/schema-version/,
		);
		expect(() => createModel({ ...data, seasons: [] })).toThrow(
			/relationship/,
		);
	});
});
