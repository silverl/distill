import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { app } from "../index.js";
import { resetConfig, setConfig } from "../lib/config.js";
import type { ServerConfig } from "../lib/config.js";

const TMP_DIR = join(import.meta.dir, "fixtures", "_tmp_projects");

const baseConfig: ServerConfig = {
	OUTPUT_DIR: join(TMP_DIR, "output"),
	PORT: 3001,
	PROJECT_DIR: TMP_DIR,
	POSTIZ_URL: "",
	POSTIZ_API_KEY: "",
};

describe("Projects API", () => {
	beforeAll(async () => {
		await rm(TMP_DIR, { recursive: true, force: true });
		await mkdir(join(TMP_DIR, "output", "journal"), { recursive: true });
		await mkdir(join(TMP_DIR, "output", "blog", "weekly"), { recursive: true });
		await mkdir(join(TMP_DIR, "output", "blog", "themes"), { recursive: true });
		await mkdir(join(TMP_DIR, "output", "projects"), { recursive: true });

		// Write .distill.toml with project config
		await writeFile(
			join(TMP_DIR, ".distill.toml"),
			[
				"[[projects]]",
				'name = "distill"',
				'description = "Content pipeline"',
				'url = "https://github.com/example/distill"',
				'tags = ["pipeline", "content"]',
				"",
				"[[projects]]",
				'name = "vermas"',
				'description = "Multi-agent system"',
				'tags = ["agents"]',
			].join("\n"),
			"utf-8",
		);

		// Write journal fixtures
		await writeFile(
			join(TMP_DIR, "output", "journal", "journal-2026-02-09-dev-journal.md"),
			`---
date: 2026-02-09
type: journal
style: dev-journal
sessions_count: 3
duration_minutes: 120
tags:
  - journal
projects:
  - distill
  - vermas
---

# Journal entry`,
			"utf-8",
		);

		await writeFile(
			join(TMP_DIR, "output", "journal", "journal-2026-02-08-dev-journal.md"),
			`---
date: 2026-02-08
type: journal
style: dev-journal
sessions_count: 2
duration_minutes: 90
tags:
  - journal
projects:
  - distill
---

# Another entry`,
			"utf-8",
		);

		// Journal with organic-only project (not in .distill.toml)
		await writeFile(
			join(TMP_DIR, "output", "journal", "journal-2026-02-07-dev-journal.md"),
			`---
date: 2026-02-07
type: journal
style: dev-journal
sessions_count: 1
duration_minutes: 45
tags:
  - journal
projects:
  - side-project
---

# Side project entry`,
			"utf-8",
		);

		// Journal with empty projects array (should NOT create phantom projects)
		await writeFile(
			join(TMP_DIR, "output", "journal", "journal-2026-02-06-dev-journal.md"),
			`---
date: 2026-02-06
type: journal
style: dev-journal
sessions_count: 1
duration_minutes: 30
tags:
  - journal
projects: []
---

# No project entry`,
			"utf-8",
		);

		// Write blog fixture with projects
		await writeFile(
			join(TMP_DIR, "output", "blog", "weekly", "weekly-2026-W06.md"),
			`---
title: "Week 6"
date: 2026-02-07
type: blog
post_type: weekly
slug: weekly-2026-W06
tags:
  - pipeline
themes:
  - content-pipeline
projects:
  - distill
---

# Week 6`,
			"utf-8",
		);

		// Blog-only project (no journal entries for this project)
		await writeFile(
			join(TMP_DIR, "output", "blog", "themes", "theme-ci-pipelines.md"),
			`---
title: "CI Pipeline Patterns"
date: 2026-02-05
type: blog
post_type: thematic
slug: theme-ci-pipelines
tags:
  - ci
themes:
  - ci-pipelines
projects:
  - ci-tools
---

# CI Pipeline Patterns`,
			"utf-8",
		);

		// Write a project note
		await writeFile(
			join(TMP_DIR, "output", "projects", "project-distill.md"),
			"# Distill\n\nProject notes here.",
			"utf-8",
		);

		// Blog memory/state stubs
		await writeFile(
			join(TMP_DIR, "output", "blog", ".blog-memory.json"),
			JSON.stringify({ posts: [] }),
			"utf-8",
		);
		await writeFile(
			join(TMP_DIR, "output", "blog", ".blog-state.json"),
			JSON.stringify({ posts: [] }),
			"utf-8",
		);

		setConfig(baseConfig);
	});

	afterAll(async () => {
		resetConfig();
		await rm(TMP_DIR, { recursive: true, force: true });
	});

	test("GET /api/projects returns project list", async () => {
		const res = await app.request("/api/projects");
		expect(res.status).toBe(200);

		const data = await res.json();
		expect(data).toHaveProperty("projects");
		expect(data.projects.length).toBe(4);
	});

	test("projects include stats from journal/blog data", async () => {
		const res = await app.request("/api/projects");
		const data = await res.json();

		const distill = data.projects.find((p: { name: string }) => p.name === "distill");
		expect(distill).toBeDefined();
		expect(distill.journalCount).toBe(2);
		expect(distill.blogCount).toBe(1);
		expect(distill.totalSessions).toBe(5); // 3 + 2
		expect(distill.totalDurationMinutes).toBe(210); // 120 + 90
		expect(distill.description).toBe("Content pipeline");
		expect(distill.hasProjectNote).toBe(true);
	});

	test("projects are sorted by lastSeen descending", async () => {
		const res = await app.request("/api/projects");
		const data = await res.json();

		// distill was last seen 2026-02-09, vermas also 2026-02-09
		// Both should appear
		const names = data.projects.map((p: { name: string }) => p.name);
		expect(names).toContain("distill");
		expect(names).toContain("vermas");
	});

	test("vermas has correct stats", async () => {
		const res = await app.request("/api/projects");
		const data = await res.json();

		const vermas = data.projects.find((p: { name: string }) => p.name === "vermas");
		expect(vermas).toBeDefined();
		expect(vermas.journalCount).toBe(1);
		expect(vermas.blogCount).toBe(0);
		expect(vermas.description).toBe("Multi-agent system");
		expect(vermas.hasProjectNote).toBe(false);
	});

	test("GET /api/projects/:name returns project detail", async () => {
		const res = await app.request("/api/projects/distill");
		expect(res.status).toBe(200);

		const data = await res.json();
		expect(data).toHaveProperty("summary");
		expect(data).toHaveProperty("journals");
		expect(data).toHaveProperty("blogs");
		expect(data).toHaveProperty("projectNoteContent");

		expect(data.summary.name).toBe("distill");
		expect(data.journals.length).toBe(2);
		expect(data.blogs.length).toBe(1);
		expect(data.projectNoteContent).toContain("Project notes here");
	});

	test("GET /api/projects/:name returns filtered journals only", async () => {
		const res = await app.request("/api/projects/vermas");
		expect(res.status).toBe(200);

		const data = await res.json();
		expect(data.journals.length).toBe(1);
		expect(data.journals[0].date).toBe("2026-02-09");
		expect(data.blogs.length).toBe(0);
		expect(data.projectNoteContent).toBeNull();
	});

	test("GET /api/projects/:name returns 404 for unknown project", async () => {
		const res = await app.request("/api/projects/nonexistent");
		expect(res.status).toBe(404);
	});

	test("organic-only project appears with empty config fields", async () => {
		const res = await app.request("/api/projects");
		const data = await res.json();

		const sideProject = data.projects.find((p: { name: string }) => p.name === "side-project");
		expect(sideProject).toBeDefined();
		expect(sideProject.description).toBe("");
		expect(sideProject.url).toBe("");
		expect(sideProject.tags).toEqual([]);
		expect(sideProject.journalCount).toBe(1);
		expect(sideProject.totalSessions).toBe(1);
	});

	test("empty projects array does not create phantom projects", async () => {
		const res = await app.request("/api/projects");
		const data = await res.json();

		// Should be 4: distill, vermas (config), side-project (organic), ci-tools (blog-only)
		// The journal with projects: [] should NOT add any project
		expect(data.projects.length).toBe(4);
		const names = data.projects.map((p: { name: string }) => p.name);
		expect(names).not.toContain("");
	});

	test("blog-only project has zero journal stats", async () => {
		const res = await app.request("/api/projects");
		const data = await res.json();

		const ciTools = data.projects.find((p: { name: string }) => p.name === "ci-tools");
		expect(ciTools).toBeDefined();
		expect(ciTools.journalCount).toBe(0);
		expect(ciTools.lastSeen).toBe("");
		expect(ciTools.totalSessions).toBe(0);
		expect(ciTools.blogCount).toBe(1);
	});
});
