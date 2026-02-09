/**
 * Config routes -- read/write .distill.toml from the web UI.
 */
import { dirname } from "node:path";
import { Hono } from "hono";
import { getConfig } from "../lib/config.js";
import { readConfig, writeConfig } from "../lib/toml.js";

const configRoutes = new Hono();

function getProjectDir(): string {
	const config = getConfig();
	if (config.PROJECT_DIR) return config.PROJECT_DIR;
	// Fall back to parent of OUTPUT_DIR or CWD
	return dirname(config.OUTPUT_DIR) || process.cwd();
}

configRoutes.get("/api/config", async (c) => {
	const projectDir = getProjectDir();
	const config = await readConfig(projectDir);
	return c.json(config);
});

configRoutes.put("/api/config", async (c) => {
	const projectDir = getProjectDir();
	const existing = await readConfig(projectDir);
	const updates = (await c.req.json()) as Record<string, unknown>;

	// Deep merge: only merge top-level sections that are provided
	const merged = { ...existing };
	for (const [key, value] of Object.entries(updates)) {
		if (value !== null && typeof value === "object" && !Array.isArray(value)) {
			merged[key as keyof typeof merged] = {
				...((existing[key as keyof typeof existing] as Record<string, unknown>) ?? {}),
				...(value as Record<string, unknown>),
			} as never;
		} else {
			(merged as Record<string, unknown>)[key] = value;
		}
	}

	await writeConfig(projectDir, merged);
	return c.json(merged);
});

configRoutes.get("/api/config/sources", async (c) => {
	const projectDir = getProjectDir();
	const config = await readConfig(projectDir);

	const sources = [
		{
			source: "rss",
			configured: true,
			label: "RSS Feeds",
			description: "Subscribe to RSS/Atom feeds from blogs and news sites",
			availability: "available" as const,
		},
		{
			source: "browser",
			configured: config.intake?.browser_history ?? false,
			label: "Browser History",
			description: "Ingest recent browsing history from Chrome and Safari",
			availability: "available" as const,
		},
		{
			source: "substack",
			configured: (config.intake?.substack_blogs ?? []).length > 0,
			label: "Substack",
			description: "Follow Substack newsletters by URL",
			availability: "available" as const,
		},
		{
			source: "linkedin",
			configured: false,
			label: "LinkedIn",
			description: "Import from LinkedIn GDPR data export",
			availability: "coming_soon" as const,
		},
		{
			source: "twitter",
			configured: false,
			label: "Twitter/X",
			description: "Import from X data export",
			availability: "coming_soon" as const,
		},
		{
			source: "reddit",
			configured: false,
			label: "Reddit",
			description: "Ingest saved and upvoted posts via Reddit API",
			availability: "coming_soon" as const,
		},
		{
			source: "youtube",
			configured: false,
			label: "YouTube",
			description: "Fetch liked videos and transcripts via YouTube API",
			availability: "coming_soon" as const,
		},
		{
			source: "gmail",
			configured: false,
			label: "Gmail",
			description: "Ingest newsletter emails via Gmail API",
			availability: "coming_soon" as const,
		},
	];

	return c.json({ sources });
});

export default configRoutes;
