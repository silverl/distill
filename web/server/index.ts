/**
 * Hono server — mounts API routes and serves static React build.
 */
import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import { getConfig } from "./lib/config.js";
import blog from "./routes/blog.js";
import config from "./routes/config.js";
import dashboard from "./routes/dashboard.js";
import journal from "./routes/journal.js";
import memory from "./routes/memory.js";
import notes from "./routes/notes.js";
import pipeline from "./routes/pipeline.js";
import projects from "./routes/projects.js";
import publish from "./routes/publish.js";
import reading from "./routes/reading.js";
import seeds from "./routes/seeds.js";

const app = new Hono();

// Middleware
app.use("*", logger());
app.use("/api/*", cors());

// API routes
app.route("/", config);
app.route("/", pipeline);
app.route("/", dashboard);
app.route("/", journal);
app.route("/", blog);
app.route("/", reading);
app.route("/", projects);
app.route("/", publish);
app.route("/", seeds);
app.route("/", notes);
app.route("/", memory);

// Health check
app.get("/api/health", (c) => c.json({ status: "ok" }));

// Static files (production)
if (process.env.NODE_ENV === "production") {
	app.use("/*", serveStatic({ root: "./dist" }));
	// SPA fallback
	app.get("*", serveStatic({ path: "./dist/index.html" }));
}

// Export type for Hono RPC client
export type AppType = typeof app;
export { app };

// Start server when run directly
if (import.meta.main) {
	const config = getConfig();
	console.log(`Distill web server starting on port ${config.PORT}`);
	console.log(`Reading data from: ${config.OUTPUT_DIR}`);

	Bun.serve({
		fetch: app.fetch,
		port: config.PORT,
	});
}
