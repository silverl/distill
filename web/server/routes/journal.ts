import { basename, join } from "node:path";
import { Hono } from "hono";
import { JournalFrontmatterSchema, SaveMarkdownSchema } from "../../shared/schemas.js";
import { getConfig } from "../lib/config.js";
import { listFiles, readMarkdown, writeMarkdown } from "../lib/files.js";
import { parseFrontmatter, reconstructMarkdown } from "../lib/frontmatter.js";
import { loadJournalEntries } from "../lib/loaders.js";

const app = new Hono();

app.get("/api/journal", async (c) => {
	const { OUTPUT_DIR } = getConfig();
	const entries = await loadJournalEntries(OUTPUT_DIR);
	return c.json({ entries });
});

app.get("/api/journal/:date", async (c) => {
	const date = c.req.param("date");
	const { OUTPUT_DIR } = getConfig();
	const files = await listFiles(
		join(OUTPUT_DIR, "journal"),
		new RegExp(`^journal-${date}.*\\.md$`),
	);

	if (files.length === 0) {
		return c.json({ error: "Journal entry not found" }, 404);
	}

	const file = files[0];
	if (!file) return c.json({ error: "Journal entry not found" }, 404);
	const raw = await readMarkdown(file);
	if (!raw) return c.json({ error: "Could not read file" }, 500);

	const parsed = parseFrontmatter(raw, JournalFrontmatterSchema);
	if (!parsed) return c.json({ error: "Could not parse frontmatter" }, 500);

	return c.json({
		meta: {
			date: parsed.frontmatter.date,
			style: parsed.frontmatter.style,
			sessionsCount: parsed.frontmatter.sessions_count,
			durationMinutes: parsed.frontmatter.duration_minutes,
			tags: parsed.frontmatter.tags,
			projects: parsed.frontmatter.projects,
			filename: basename(file),
		},
		content: parsed.content,
	});
});

app.put("/api/journal/:date", async (c) => {
	const date = c.req.param("date");
	const { OUTPUT_DIR } = getConfig();

	const body = await c.req.json();
	const parsed = SaveMarkdownSchema.safeParse(body);
	if (!parsed.success) return c.json({ error: "Invalid request body" }, 400);

	const files = await listFiles(
		join(OUTPUT_DIR, "journal"),
		new RegExp(`^journal-${date}.*\\.md$`),
	);

	if (files.length === 0) return c.json({ error: "Journal entry not found" }, 404);

	const file = files[0];
	if (!file) return c.json({ error: "Journal entry not found" }, 404);
	const raw = await readMarkdown(file);
	if (!raw) return c.json({ error: "Could not read file" }, 500);

	const updated = reconstructMarkdown(raw, parsed.data.content);

	try {
		await writeMarkdown(file, updated, OUTPUT_DIR);
	} catch (err) {
		const message = err instanceof Error ? err.message : "Write failed";
		return c.json({ error: message }, 403);
	}

	return c.json({ success: true });
});

export default app;
