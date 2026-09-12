import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { fixture } from "../tests/fixture";
import App from "./App";
import { Audit, CareerRecords, Explorer } from "./archive";
import nottsCountyCrest from "./assets/notts-county-crest.png";
import { CareerContext } from "./context";
import { createModel, defaultFilters } from "./data";
import {
	Competitions,
	MatchDetail,
	Matches,
	Overview,
	PlayerDetail,
	Players,
} from "./pages";

const model = createModel(fixture);

describe("local stats pages", () => {
	it("shows the club crest while career data loads", () => {
		const html = renderToStaticMarkup(<App />);
		expect(html).toContain(`src="${nottsCountyCrest}"`);
		expect(html).toContain('alt="Notts County crest"');
		expect(html).toContain('draggable="false"');
		expect(html).not.toContain("lucide-shield");
	});

	it("labels goalkeeper zero assumptions in otherwise matched verification rows", () => {
		const reviewed = createModel({
			...fixture,
			season_reconciliation: {
				...fixture.season_reconciliation,
				comparisons: fixture.season_reconciliation.comparisons.map(
					(row) => ({
						...row,
						result: "match",
						metrics: {
							...row.metrics,
							goals: {
								observed: 0,
								derived: 0,
								result: "match",
								difference: 0,
								missing_match_values: 0,
								assumed_zero_match_values: 1,
							},
						},
					}),
				),
			},
		});
		const html = renderToStaticMarkup(
			<MemoryRouter initialEntries={["/audit"]}>
				<CareerContext
					value={{
						model: reviewed,
						filters: defaultFilters,
						matches: reviewed.matches,
					}}
				>
					<Audit />
				</CareerContext>
			</MemoryRouter>,
		);
		expect(html).toContain("1 goalkeeper goal values assumed zero");
		expect(html).toContain("Matched");
		expect(html).not.toContain("nine comparisons unavailable");
	});

	it.each(["passes_completed", "key_passes", "interceptions"])(
		"ranks recorded %s within selected fixtures and preserves unknowns",
		(statistic) => {
			const detailed = createModel({
				...fixture,
				player_matches: fixture.player_matches.map((row, index) => ({
					...row,
					passes_completed_short:
						index === 0 ? 5 : index === 4 ? 999 : null,
					passes_completed_medium:
						index === 0 || index === 4 ? 4 : null,
					passes_completed_long:
						index === 0 || index === 4 ? 1 : null,
					key_passes: index === 0 ? 2 : null,
					interceptions: index === 0 ? 3 : null,
				})),
			});
			const matches = detailed.matches.filter(
				(match) => match.competition.id === fixture.competitions[0].id,
			);
			const html = renderToStaticMarkup(
				<MemoryRouter initialEntries={[`/players?stat=${statistic}`]}>
					<CareerContext
						value={{
							model: detailed,
							filters: defaultFilters,
							matches,
						}}
					>
						<Players />
					</CareerContext>
				</MemoryRouter>,
			);
			expect(html).toContain("recorded totals");
			expect(html).toContain("1/3 appearances recorded");
			expect(html).toContain("Apps recorded");
			expect(html).toContain("1/2");
			expect(html).toContain('aria-label="partial data"');
			expect(html).not.toContain("999");
			expect(html).not.toContain("Test Opponent");
		},
	);

	it.each([
		{
			name: "overview",
			route: "/",
			location: "/",
			element: <Overview />,
			title: "Career overview",
		},
		{
			name: "matches",
			route: "/matches",
			location: "/matches",
			element: <Matches />,
			title: "Matches",
		},
		{
			name: "match detail",
			route: "/matches/:id",
			location: `/matches/${fixture.matches[2].id}`,
			element: <MatchDetail />,
			title: "4-3 on penalties",
		},
		{
			name: "players",
			route: "/players",
			location: "/players",
			element: <Players />,
			title: "Players",
		},
		{
			name: "player detail",
			route: "/players/:id",
			location: `/players/${fixture.players[0].id}`,
			element: <PlayerDetail />,
			title: "Test Forward",
		},
		{
			name: "competitions",
			route: "/competitions",
			location: "/competitions",
			element: <Competitions />,
			title: "Competitions",
		},
		{
			name: "career records",
			route: "/career",
			location: "/career",
			element: <CareerRecords />,
			title: "Career records",
		},
		{
			name: "verification",
			route: "/audit",
			location: "/audit",
			element: <Audit />,
			title: "Verification",
		},
		{
			name: "data explorer",
			route: "/data",
			location: "/data",
			element: <Explorer />,
			title: "Data explorer",
		},
	])(
		"renders $name without image metadata",
		({ route, location, element, title }) => {
			const html = renderToStaticMarkup(
				<MemoryRouter initialEntries={[location]}>
					<CareerContext
						value={{
							model,
							filters: defaultFilters,
							matches: model.matches,
						}}
					>
						<Routes>
							<Route path={route} element={element} />
						</Routes>
					</CareerContext>
				</MemoryRouter>,
			);
			expect(html).toContain(title);
			expect(html).not.toContain("View source screenshot");
			expect(html).not.toContain("/evidence/");
		},
	);
	it("groups monthly honours by player and season and shows the award month", () => {
		const data = {
			...fixture,
			competition_events: [
				{
					id: "00000000-0000-4000-8000-000000000090",
					player_id: fixture.players[0].id,
					competition_season_id: fixture.competition_seasons[0].id,
					event_type: "player_of_the_month",
					period: "2018-08",
					announced_on: null,
					description: "August winner",
				},
				{
					id: "00000000-0000-4000-8000-000000000091",
					player_id: fixture.players[0].id,
					competition_season_id: fixture.competition_seasons[0].id,
					event_type: "player_of_the_month",
					period: "2018-09",
					announced_on: "2018-10-05",
					description: "September winner",
				},
				{
					id: "00000000-0000-4000-8000-000000000092",
					player_id: fixture.players[1].id,
					competition_season_id: fixture.competition_seasons[1].id,
					event_type: "goalkeeper_of_the_competition",
					period: "2018/19",
					description: "Cup winner",
				},
			],
		};
		const model = createModel(data);
		const filters = {
			...defaultFilters,
			season: fixture.seasons[0].id,
			competition: fixture.competitions[0].id,
		};
		const html = renderToStaticMarkup(
			<MemoryRouter initialEntries={["/career?tab=events"]}>
				<CareerContext
					value={{ model, filters, matches: model.matches }}
				>
					<CareerRecords />
				</CareerContext>
			</MemoryRouter>,
		);
		expect(html).toContain("Player of the Month");
		expect(html).toContain("August 2018");
		expect(html).toContain("September 2018");
		expect(html).toContain(">2</td>");
		expect(html).not.toContain("Cup winner");
		expect(html).not.toContain("Date not recorded");
	});
});
