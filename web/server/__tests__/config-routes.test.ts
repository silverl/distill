import { afterAll, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { app } from "../index.js";
import { resetConfig, setConfig } from "../lib/config.js";
import type { ServerConfig } from "../lib/config.js";

const TMP_DIR = join(import.meta.dir, "fixtures", "_tmp_config");

const baseConfig: ServerConfig = {
	OUTPUT_DIR: join(TMP_DIR, "output"),
	PORT: 3001,
	PROJECT_DIR: TMP_DIR,
	POSTIZ_URL: "",
	POSTIZ_API_KEY: "",
};

describe("Config API", () => {
	beforeEach(async () => {
		await rm(TMP_DIR, { recursive: true, force: true });
		await mkdir(join(TMP_DIR, "output"), { recursive: true });
		setConfig(baseConfig);
	});

	afterAll(async () => {
		resetConfig();
		await rm(TMP_DIR, { recursive: true, force: true });
	});

	test("GET /api/config returns empty object when no .distill.toml exists", async () => {
		const res = await app.request("/api/config");
		expect(res.status).toBe(200);
		const data = await res.json();
		expect(data).toEqual({});
	});

	test("GET /api/config returns parsed config when .distill.toml exists", async () => {
		const tomlContent = [
			"[output]",
			'directory = "./my-insights"',
			"",
			"[journal]",
			'style = "casual"',
			"target_word_count = 800",
			"",
			"[blog]",
			"include_diagrams = false",
			'platforms = ["obsidian", "ghost"]',
		].join("\n");
		await writeFile(join(TMP_DIR, ".distill.toml"), tomlContent, "utf-8");

		const res = await app.request("/api/config");
		expect(res.status).toBe(200);
		const data = await res.json();
		expect(data.output.directory).toBe("./my-insights");
		expect(data.journal.style).toBe("casual");
		expect(data.journal.target_word_count).toBe(800);
		expect(data.blog.include_diagrams).toBe(false);
		expect(data.blog.platforms).toEqual(["obsidian", "ghost"]);
	});

	test("PUT /api/config merges partial updates", async () => {
		// Start with an existing config
		const tomlContent = ["[journal]", 'style = "casual"', "target_word_count = 800"].join("\n");
		await writeFile(join(TMP_DIR, ".distill.toml"), tomlContent, "utf-8");

		// Send partial update
		const res = await app.request("/api/config", {
			method: "PUT",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				journal: { target_word_count: 1200 },
				blog: { include_diagrams: true },
			}),
		});
		expect(res.status).toBe(200);
		const data = await res.json();

		// Original journal.style should be preserved, target_word_count updated
		expect(data.journal.style).toBe("casual");
		expect(data.journal.target_word_count).toBe(1200);
		// New section should be added
		expect(data.blog.include_diagrams).toBe(true);

		// Verify persistence by re-reading
		const getRes = await app.request("/api/config");
		const getData = await getRes.json();
		expect(getData.journal.style).toBe("casual");
		expect(getData.journal.target_word_count).toBe(1200);
		expect(getData.blog.include_diagrams).toBe(true);
	});

	test("GET /api/config/sources returns source status array", async () => {
		// Write a config with some sources configured
		const tomlContent = [
			"[intake]",
			"browser_history = true",
			'substack_blogs = ["https://example.substack.com"]',
		].join("\n");
		await writeFile(join(TMP_DIR, ".distill.toml"), tomlContent, "utf-8");

		const res = await app.request("/api/config/sources");
		expect(res.status).toBe(200);
		const data = await res.json();
		expect(data.sources).toBeInstanceOf(Array);
		expect(data.sources.length).toBe(8);

		// Available sources
		const rss = data.sources.find((s: { source: string }) => s.source === "rss");
		expect(rss.configured).toBe(true);
		expect(rss.label).toBe("RSS Feeds");
		expect(rss.availability).toBe("available");
		expect(rss.description).toBeTruthy();

		const browser = data.sources.find((s: { source: string }) => s.source === "browser");
		expect(browser.configured).toBe(true);
		expect(browser.availability).toBe("available");

		const substack = data.sources.find((s: { source: string }) => s.source === "substack");
		expect(substack.configured).toBe(true);
		expect(substack.availability).toBe("available");

		// Coming soon sources
		const reddit = data.sources.find((s: { source: string }) => s.source === "reddit");
		expect(reddit.configured).toBe(false);
		expect(reddit.availability).toBe("coming_soon");
		expect(reddit.description).toBeTruthy();

		const youtube = data.sources.find((s: { source: string }) => s.source === "youtube");
		expect(youtube.configured).toBe(false);
		expect(youtube.availability).toBe("coming_soon");

		const gmail = data.sources.find((s: { source: string }) => s.source === "gmail");
		expect(gmail.configured).toBe(false);
		expect(gmail.availability).toBe("coming_soon");

		const linkedin = data.sources.find((s: { source: string }) => s.source === "linkedin");
		expect(linkedin.availability).toBe("coming_soon");

		const twitter = data.sources.find((s: { source: string }) => s.source === "twitter");
		expect(twitter.availability).toBe("coming_soon");
	});
});
