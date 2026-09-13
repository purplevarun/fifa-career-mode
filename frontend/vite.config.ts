import react from "@vitejs/plugin-react";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { statSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const root = fileURLToPath(new URL("../", import.meta.url));
const database = process.env.CAREER_DB;
const databasePath = resolve(root, database || "processing/data/career.sqlite");
const dataSource = {
	label:
		process.env.CAREER_DATA_LABEL ||
		(database ? "Preview database" : "Main archive"),
	preview: Boolean(database),
};

function fileVersion(path: string) {
	try {
		const info = statSync(path, { bigint: true });
		return [info.dev, info.ino, info.size, info.mtimeNs, info.ctimeNs]
			.map(String)
			.join(":");
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
		throw error;
	}
}

function localStats(
	request: IncomingMessage,
	response: ServerResponse,
	next: () => void,
) {
	const route = request.url?.split("?")[0];
	if (route !== "/api/stats" && route !== "/api/stats/version") return next();
	response.setHeader("Content-Type", "application/json");
	response.setHeader("Cache-Control", "no-store");
	if (request.method !== "GET") {
		response.statusCode = 405;
		response.setHeader("Allow", "GET");
		response.end(JSON.stringify({ error: "Method not allowed" }));
		return;
	}
	if (
		request.headers.origin &&
		request.headers.origin !== `http://${request.headers.host}`
	) {
		response.statusCode = 403;
		response.end(JSON.stringify({ error: "Local access only" }));
		return;
	}
	if (route === "/api/stats/version") {
		try {
			const mainVersion = fileVersion(databasePath);
			const revision =
				mainVersion === null
					? null
					: createHash("sha256")
							.update(
								`${mainVersion}:${fileVersion(`${databasePath}-wal`) ?? ""}`,
							)
							.digest("hex");
			response.end(JSON.stringify({ revision }));
		} catch {
			response.statusCode = 503;
			response.end(
				JSON.stringify({
					error: "Local stats database is unavailable",
				}),
			);
		}
		return;
	}
	const child = execFile(
		"python3",
		["-m", "processing", ...(database ? ["--db", database] : []), "data"],
		{ cwd: root, timeout: 15000, maxBuffer: 16 * 1024 * 1024 },
		(error, output) => {
			if (response.destroyed) return;
			try {
				if (error) throw error;
				response.end(
					JSON.stringify({
						...JSON.parse(output),
						data_source: dataSource,
					}),
				);
			} catch {
				response.statusCode = 503;
				response.end(
					JSON.stringify({
						error: "Local stats database is unavailable",
					}),
				);
			}
		},
	);
	request.on("aborted", () => child.kill());
}

export default defineConfig({
	base: "./",
	plugins: [
		react(),
		{
			name: "local-sqlite-stats",
			configureServer(server) {
				server.middlewares.use(localStats);
			},
			configurePreviewServer(server) {
				server.middlewares.use(localStats);
			},
		},
	],
	server: { host: "127.0.0.1" },
	preview: { host: "127.0.0.1" },
});
