import { describe, expect, it, vi } from "vitest";
import { loadCareerDataset } from "./loadData";

describe("career dataset loader", () => {
	it("requests a dataset without exposing response details in errors", async () => {
		const dataset = { schema_version: 3 };
		const fetcher = vi.fn(
			async () => new Response(JSON.stringify(dataset), { status: 200 }),
		);

		await expect(
			loadCareerDataset(
				fetcher,
				"/api/stats",
				new AbortController().signal,
			),
		).resolves.toEqual(dataset);
		expect(fetcher).toHaveBeenCalledWith("/api/stats", {
			signal: expect.any(AbortSignal),
			cache: "no-store",
		});
	});

	it("rejects failed responses", async () => {
		const fetcher = vi.fn(async () => new Response(null, { status: 503 }));

		await expect(
			loadCareerDataset(
				fetcher,
				"/api/stats",
				new AbortController().signal,
			),
		).rejects.toThrow("503");
	});

	it("rejects malformed local data", async () => {
		const fetcher = vi.fn(
			async () => new Response("not JSON", { status: 200 }),
		);
		await expect(
			loadCareerDataset(
				fetcher,
				"/api/stats",
				new AbortController().signal,
			),
		).rejects.toThrow();
	});

	it("preserves request cancellation", async () => {
		const failure = new DOMException("Aborted", "AbortError");
		const fetcher = vi.fn().mockRejectedValue(failure);
		await expect(
			loadCareerDataset(
				fetcher,
				"/api/stats",
				new AbortController().signal,
			),
		).rejects.toBe(failure);
	});
});
