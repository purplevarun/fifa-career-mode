import { describe, expect, it } from "vitest";
import { fixture as data } from "../tests/fixture";
import {
	createModel,
	defaultFilters,
	metric,
	overviewRankings,
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
	it("ranks only five Notts players within the selected fixtures", () => {
		const base = selectPerformances(model, model.matches)[0];
		const opponent = selectPerformances(model, model.matches, null).find(
			(row) => row.club_id !== model.nottsId,
		)!;
		const selectedId = opponent.match_id;
		const otherId = model.matches.find(
			(match) => match.id !== selectedId,
		)!.id;
		const players = Array.from({ length: 7 }, (_entry, index) => ({
			...data.players[0],
			id: `00000000-0000-4000-8000-${String(500 + index).padStart(12, "0")}`,
			name: `Ranked ${index + 1}`,
		}));
		const ranked = createModel({
			...data,
			players: [...data.players, ...players],
			player_matches: [
				...players.flatMap((player, index) => [
					{
						...base,
						id: `00000000-0000-4000-8000-${String(600 + index).padStart(12, "0")}`,
						player_id: player.id,
						match_id: selectedId,
						goals: 10 + index,
						assists: 20 + index,
						rating: 7 + index / 10,
						passes_completed_short: 100 + index,
						passes_completed_medium: 10,
						passes_completed_long: 3,
						tackles_won: 30 + index,
					},
					{
						...base,
						id: `00000000-0000-4000-8000-${String(700 + index).padStart(12, "0")}`,
						player_id: player.id,
						match_id: otherId,
						goals: 999,
						assists: 999,
						rating: 10,
					},
				]),
				{
					...opponent,
					goals: 1000,
					assists: 1000,
					rating: 10,
					tackles_won: 1000,
					passes_completed_short: 1000,
					passes_completed_medium: 1000,
					passes_completed_long: 1000,
				},
			],
		});
		const rankings = overviewRankings(
			ranked,
			ranked.matches.filter((match) => match.id === selectedId),
		);
		for (const rows of Object.values(rankings)) {
			expect(rows).toHaveLength(5);
			expect(rows.every((row) => row.name.startsWith("Ranked "))).toBe(
				true,
			);
			expect(rows.every((row) => row.total === 1)).toBe(true);
		}
		expect(rankings.goals.map((row) => row.value)).toEqual([
			16, 15, 14, 13, 12,
		]);
		expect(rankings.assists[0].value).toBe(26);
		expect(rankings.passes_completed[0].value).toBe(119);
		expect(rankings.tackles_won[0].value).toBe(36);
		expect(rankings.rating[0].value).toBeCloseTo(7.6);
		expect(rankings.appearances.map((row) => row.name)).toEqual([
			"Ranked 1",
			"Ranked 2",
			"Ranked 3",
			"Ranked 4",
			"Ranked 5",
		]);
	});
	it("keeps ranking coverage and averages only recorded ratings", () => {
		const base = selectPerformances(model, model.matches)[0];
		const player = data.players[0];
		const unknownPlayer = data.players[1];
		const ranked = createModel({
			...data,
			player_matches: [
				{
					...base,
					id: "00000000-0000-4000-8000-000000000801",
					player_id: player.id,
					match_id: data.matches[0].id,
					rating: 8,
					goals: null,
					assists: null,
					tackles_won: 0,
					passes_completed_short: 1,
					passes_completed_medium: 2,
					passes_completed_long: 3,
				},
				{
					...base,
					id: "00000000-0000-4000-8000-000000000802",
					player_id: player.id,
					match_id: data.matches[1].id,
					rating: 6,
					goals: 2,
					assists: null,
					tackles_won: null,
					passes_completed_short: 9,
					passes_completed_medium: null,
					passes_completed_long: 4,
				},
				{
					...base,
					id: "00000000-0000-4000-8000-000000000803",
					player_id: unknownPlayer.id,
					match_id: data.matches[0].id,
					rating: null,
					goals: null,
					assists: null,
					tackles_won: null,
					passes_completed_short: null,
					passes_completed_medium: null,
					passes_completed_long: null,
				},
			],
		});
		const rankings = overviewRankings(ranked, ranked.matches);
		expect(rankings.rating).toEqual([
			{ id: player.id, name: player.name, value: 7, known: 2, total: 2 },
		]);
		expect(rankings.passes_completed[0]).toMatchObject({
			value: 6,
			known: 1,
			total: 2,
		});
		expect(rankings.goals[0]).toMatchObject({
			value: 2,
			known: 1,
			total: 2,
		});
		expect(rankings.appearances[0]).toMatchObject({
			value: 2,
			known: 2,
			total: 2,
		});
		expect(rankings.tackles_won[0]).toMatchObject({
			value: 0,
			known: 1,
			total: 2,
		});
		expect(rankings.assists).toEqual([]);
		expect(
			Object.values(overviewRankings(ranked, [])).every(
				(rows) => rows.length === 0,
			),
		).toBe(true);
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
