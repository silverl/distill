import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { app } from "../index.js";
import { resetConfig, setConfig } from "../lib/config.js";

const FIXTURES = join(import.meta.dir, "fixtures");

describe("GET /api/blog/posts", () => {
	beforeAll(async () => {
		setConfig({
			OUTPUT_DIR: FIXTURES,
			PORT: 3001,
			PROJECT_DIR: "",
			POSTIZ_URL: "",
			POSTIZ_API_KEY: "",
		});
		// Create blog fixtures
		await mkdir(join(FIXTURES, "blog", "weekly"), { recursive: true });
		await mkdir(join(FIXTURES, "blog", "themes"), { recursive: true });
		await writeFile(
			join(FIXTURES, "blog", "weekly", "weekly-2026-W06.md"),
			`---
title: "Week 6: Building the Pipeline"
date: 2026-02-07
type: blog
post_type: weekly
slug: weekly-2026-W06
week: 2026-W06
tags:
  - pipeline
  - architecture
themes:
  - content-pipeline
projects:
  - distill
---

# Week 6: Building the Pipeline

This week focused on building out the content pipeline.`,
			"utf-8",
		);
		await writeFile(
			join(FIXTURES, "blog", "themes", "theme-multi-agent-patterns.md"),
			`---
title: Multi-Agent Patterns in Practice
date: 2026-02-06
type: blog
post_type: thematic
slug: theme-multi-agent-patterns
tags:
  - multi-agent
themes:
  - multi-agent
  - architecture
---

# Multi-Agent Patterns in Practice

A deep dive into multi-agent coordination.`,
			"utf-8",
		);
	});

	afterAll(async () => {
		resetConfig();
		await rm(join(FIXTURES, "blog", "weekly"), { recursive: true, force: true });
		await rm(join(FIXTURES, "blog", "themes"), { recursive: true, force: true });
	});

	test("returns blog posts", async () => {
		const res = await app.request("/api/blog/posts");
		expect(res.status).toBe(200);

		const data = await res.json();
		expect(data).toHaveProperty("posts");
		expect(data.posts.length).toBe(2);
	});

	test("posts are sorted by date descending", async () => {
		const res = await app.request("/api/blog/posts");
		const data = await res.json();

		for (let i = 0; i < data.posts.length - 1; i++) {
			expect(data.posts[i].date >= data.posts[i + 1].date).toBe(true);
		}
	});

	test("blog posts include projects", async () => {
		const res = await app.request("/api/blog/posts");
		const data = await res.json();
		const weekly = data.posts.find((p: { slug: string }) => p.slug === "weekly-2026-W06");
		expect(weekly).toBeDefined();
		expect(weekly.projects).toEqual(["distill"]);
	});

	test("includes platform publish status from blog memory", async () => {
		const res = await app.request("/api/blog/posts");
		const data = await res.json();
		const weekly = data.posts.find((p: { slug: string }) => p.slug === "weekly-2026-W06");
		expect(weekly).toBeDefined();
		expect(weekly.platformsPublished).toContain("obsidian");
		expect(weekly.platformsPublished).toContain("twitter");
	});
});

describe("GET /api/blog/posts/:slug", () => {
	beforeAll(async () => {
		setConfig({
			OUTPUT_DIR: FIXTURES,
			PORT: 3001,
			PROJECT_DIR: "",
			POSTIZ_URL: "",
			POSTIZ_API_KEY: "",
		});
		await mkdir(join(FIXTURES, "blog", "weekly"), { recursive: true });
		await writeFile(
			join(FIXTURES, "blog", "weekly", "weekly-2026-W06.md"),
			`---
title: "Week 6: Building the Pipeline"
date: 2026-02-07
type: blog
post_type: weekly
slug: weekly-2026-W06
projects:
  - distill
---

# Week 6

Content here.`,
			"utf-8",
		);
	});

	afterAll(async () => {
		resetConfig();
		await rm(join(FIXTURES, "blog", "weekly"), { recursive: true, force: true });
	});

	test("returns a specific blog post", async () => {
		const res = await app.request("/api/blog/posts/weekly-2026-W06");
		expect(res.status).toBe(200);

		const data = await res.json();
		expect(data).toHaveProperty("meta");
		expect(data).toHaveProperty("content");
		expect(data.meta.slug).toBe("weekly-2026-W06");
		expect(data.content).toContain("Week 6");
	});

	test("detail response includes meta.projects", async () => {
		const res = await app.request("/api/blog/posts/weekly-2026-W06");
		const data = await res.json();
		expect(data.meta).toHaveProperty("projects");
		expect(data.meta.projects).toEqual(["distill"]);
	});

	test("returns 404 for nonexistent slug", async () => {
		const res = await app.request("/api/blog/posts/nonexistent-slug");
		expect(res.status).toBe(404);
	});
});
