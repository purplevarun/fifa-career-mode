import { afterEach, describe, expect, it, vi } from "vitest";
import { loadCareerDataset, watchCareerDataset } from "./loadData";

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

describe("career database changes", () => {
	afterEach(() => vi.useRealTimers());

	it("loads a recreated database automatically and avoids unchanged data downloads", async () => {
		vi.useFakeTimers();
		let revision: string | null = "original";
		const fetcher = vi.fn(
			async (url: RequestInfo | URL) =>
				new Response(
					JSON.stringify(
						url === "/api/stats/version"
							? { revision }
							: { schema_version: 3, generation: revision },
					),
				),
		);
		const handlers = {
			onData: vi.fn(),
			onMissing: vi.fn(),
			onError: vi.fn(),
			onSettled: vi.fn(),
		};
		const stop = watchCareerDataset(fetcher, handlers);
		await vi.advanceTimersByTimeAsync(0);
		expect(handlers.onData).toHaveBeenLastCalledWith({
			schema_version: 3,
			generation: "original",
		});
		await vi.advanceTimersByTimeAsync(3000);
		expect(handlers.onData).toHaveBeenCalledTimes(1);

		revision = null;
		await vi.advanceTimersByTimeAsync(3000);
		expect(handlers.onMissing).toHaveBeenCalledTimes(1);
		revision = "fresh";
		await vi.advanceTimersByTimeAsync(3000);
		expect(handlers.onData).toHaveBeenLastCalledWith({
			schema_version: 3,
			generation: "fresh",
		});
		expect(handlers.onError).not.toHaveBeenCalled();
		expect(
			fetcher.mock.calls.filter(([url]) => url === "/api/stats"),
		).toHaveLength(2);
		stop();
		await vi.advanceTimersByTimeAsync(6000);
		expect(handlers.onData).toHaveBeenCalledTimes(2);
	});

	it("recovers when processing starts after the page opened", async () => {
		vi.useFakeTimers();
		let available = false;
		const fetcher = vi.fn(
			async (url: RequestInfo | URL) =>
				new Response(
					JSON.stringify(
						url === "/api/stats/version"
							? { revision: available ? "created" : null }
							: { schema_version: 3 },
					),
				),
		);
		const handlers = {
			onData: vi.fn(),
			onMissing: vi.fn(),
			onError: vi.fn(),
			onSettled: vi.fn(),
		};
		const stop = watchCareerDataset(fetcher, handlers);
		await vi.advanceTimersByTimeAsync(0);
		expect(handlers.onMissing).toHaveBeenCalledTimes(1);
		expect(handlers.onData).not.toHaveBeenCalled();
		available = true;
		await vi.advanceTimersByTimeAsync(3000);
		expect(handlers.onData).toHaveBeenCalledWith({ schema_version: 3 });
		stop();
	});

	it("retries a transient data error without requiring another database change", async () => {
		vi.useFakeTimers();
		let failing = true;
		const fetcher = vi.fn(async (url: RequestInfo | URL) => {
			if (url === "/api/stats/version")
				return new Response(JSON.stringify({ revision: "new" }));
			return failing
				? new Response(null, { status: 503 })
				: new Response(JSON.stringify({ schema_version: 3 }));
		});
		const handlers = {
			onData: vi.fn(),
			onMissing: vi.fn(),
			onError: vi.fn(),
			onSettled: vi.fn(),
		};
		const stop = watchCareerDataset(fetcher, handlers);
		await vi.advanceTimersByTimeAsync(0);
		expect(handlers.onError).toHaveBeenCalledTimes(1);
		failing = false;
		await vi.advanceTimersByTimeAsync(3000);
		expect(handlers.onData).toHaveBeenCalledWith({ schema_version: 3 });
		stop();
	});

	it("cancels an in-flight check on cleanup", async () => {
		vi.useFakeTimers();
		let resolve: ((response: Response) => void) | undefined;
		const fetcher = vi.fn(
			(_url: RequestInfo | URL, _init?: RequestInit) =>
				new Promise<Response>((done) => {
					resolve = done;
				}),
		);
		const handlers = {
			onData: vi.fn(),
			onMissing: vi.fn(),
			onError: vi.fn(),
			onSettled: vi.fn(),
		};
		const stop = watchCareerDataset(fetcher, handlers);
		stop();
		resolve?.(new Response(JSON.stringify({ revision: "new" })));
		await vi.advanceTimersByTimeAsync(6000);
		expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true);
		expect(fetcher).toHaveBeenCalledTimes(1);
		expect(handlers.onData).not.toHaveBeenCalled();
		expect(handlers.onError).not.toHaveBeenCalled();
		expect(handlers.onSettled).not.toHaveBeenCalled();
	});
});
