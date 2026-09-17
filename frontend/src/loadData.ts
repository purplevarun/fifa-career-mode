import type { Dataset } from "./data";

export type DatasetFetcher = (
	input: RequestInfo | URL,
	init?: RequestInit,
) => Promise<Response>;

export async function loadCareerDataset(
	fetcher: DatasetFetcher,
	url: string,
	signal: AbortSignal,
): Promise<Dataset> {
	const response = await fetcher(url, { signal, cache: "no-store" });
	if (!response.ok)
		throw new Error(`Career data request failed (${response.status}).`);
	return (await response.json()) as Dataset;
}

export async function loadStaticCareerDataset(
	fetcher: DatasetFetcher,
	url: string,
	signal: AbortSignal,
): Promise<Dataset> {
	const response = await fetcher(url, { signal, cache: "no-store" });
	if (!response.ok)
		throw new Error(
			`Static career data request failed (${response.status}).`,
		);
	return (await response.json()) as Dataset;
}

export function watchCareerDataset(
	fetcher: DatasetFetcher,
	handlers: {
		onData: (data: Dataset) => void;
		onMissing: () => void;
		onError: (error: unknown) => void;
		onSettled: () => void;
	},
	intervalMs = 3000,
) {
	const controller = new AbortController();
	let revision: string | null | undefined;
	let timer: ReturnType<typeof setTimeout> | undefined;
	async function check() {
		try {
			const response = await fetcher("/api/stats/version", {
				signal: controller.signal,
				cache: "no-store",
			});
			if (!response.ok)
				throw new Error(
					`Career database check failed (${response.status}).`,
				);
			const version = (await response.json()) as { revision: unknown };
			if (
				version.revision !== null &&
				typeof version.revision !== "string"
			) {
				throw new Error("Invalid career database version.");
			}
			if (controller.signal.aborted) return;
			if (version.revision === null) {
				if (revision !== null) handlers.onMissing();
				revision = null;
			} else if (version.revision !== revision) {
				const data = await loadCareerDataset(
					fetcher,
					"/api/stats",
					controller.signal,
				);
				if (controller.signal.aborted) return;
				handlers.onData(data);
				revision = version.revision;
			}
		} catch (error) {
			if (!controller.signal.aborted) {
				revision = undefined;
				handlers.onError(error);
			}
		} finally {
			if (!controller.signal.aborted) {
				handlers.onSettled();
				timer = setTimeout(check, intervalMs);
			}
		}
	}
	void check();
	return () => {
		controller.abort();
		if (timer !== undefined) clearTimeout(timer);
	};
}
