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
