import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import {
  createModel,
  defaultFilters,
  metric,
  selectMatches,
  selectPerformances,
  summarize,
} from "./data";

const data = JSON.parse(
  readFileSync(
    new URL("../../data/exports/career.json", import.meta.url),
    "utf8",
  ),
);
const model = createModel(data);
describe("career data calculations", () => {
  it("includes every fixture and preserves preseason filtering", () => {
    expect(selectMatches(model, defaultFilters)).toHaveLength(85);
    expect(
      selectMatches(model, { ...defaultFilters, preseason: false }),
    ).toHaveLength(75);
  });
  it("uses unique appearances and keeps opponent records out of Notts totals", () => {
    expect(selectPerformances(model, model.matches)).toHaveLength(1131);
    expect(selectPerformances(model, model.matches, null)).toHaveLength(1132);
  });
  it("reconciles the complete League Two season", () => {
    const league = model.data.competitions.find(
      (competition) => competition.name === "EFL League Two",
    )!;
    const summary = summarize(
      selectMatches(model, { ...defaultFilters, competition: league.id }),
    );
    expect(summary.played).toBe(46);
    expect(summary.leaguePoints).toBe(83);
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
      (player) => player.name === "Aaron Ramsdale",
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
    expect(() => createModel({ ...data, seasons: [] })).toThrow(/relationship/);
  });
});
