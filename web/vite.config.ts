import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { createReadStream, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, sep } from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));

export default defineConfig({
  base: "./",
  plugins: [
    react(),
    {
      name: "local-evidence-originals",
      configureServer(server) {
        server.middlewares.use("/originals", (request, response, next) => {
          if (request.method !== "GET" && request.method !== "HEAD")
            return next();
          const identifier = request.url?.split("?")[0]?.slice(1);
          try {
            const data = JSON.parse(
              readFileSync(
                resolve(root, "web/public/data/career.json"),
                "utf8",
              ),
            ) as { source_images: { id: string; path: string }[] };
            const source = data.source_images.find(
              (source) => source.id === identifier,
            );
            if (!source) {
              response.statusCode = 404;
              response.end();
              return;
            }
            const path = resolve(root, source.path);
            if (!path.startsWith(resolve(root, "raw_data") + sep)) {
              response.statusCode = 403;
              response.end();
              return;
            }
            response.setHeader("Content-Type", "image/png");
            response.setHeader("Cache-Control", "public, max-age=86400");
            const stream = createReadStream(path);
            stream.on("error", () => {
              response.statusCode = 404;
              response.end();
            });
            if (request.method === "HEAD") {
              stream.destroy();
              response.end();
              return;
            }
            stream.pipe(response);
          } catch {
            response.statusCode = 503;
            response.end("Run npm run sync-data");
          }
        });
      },
    },
  ],
  server: { host: "127.0.0.1" },
});
