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
});
