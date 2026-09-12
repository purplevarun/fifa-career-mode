import react from "@vitejs/plugin-react";
import { execFile } from "node:child_process";
import type { IncomingMessage, ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const root = fileURLToPath(new URL("../", import.meta.url));

function localStats(
	request: IncomingMessage,
	response: ServerResponse,
	next: () => void,
) {
	if (request.url?.split("?")[0] !== "/api/stats") return next();
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
	const child = execFile(
		"python3",
		["-m", "processing", "data"],
		{ cwd: root, timeout: 15000, maxBuffer: 16 * 1024 * 1024 },
		(error, output) => {
			if (response.destroyed) return;
			if (error) {
				response.statusCode = 503;
				response.end(
					JSON.stringify({
						error: "Local stats database is unavailable",
					}),
				);
				return;
			}
			response.end(output);
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
