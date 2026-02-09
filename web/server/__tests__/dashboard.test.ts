import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { join } from "node:path";
import { app } from "../index.js";
import { resetConfig, setConfig } from "../lib/config.js";

const FIXTURES = join(import.meta.dir, "fixtures");

describe("GET /api/dashboard", () => {
	beforeAll(() => {
		setConfig({
			OUTPUT_DIR: FIXTURES,
			PORT: 3001,
			PROJECT_DIR: "",
			POSTIZ_URL: "",
			POSTIZ_API_KEY: "",
		});
	});

	afterAll(() => {
		resetConfig();
	});

	test("returns dashboard data", async () => {
		const res = await app.request("/api/dashboard");
		expect(res.status).toBe(200);

		const data = await res.json();
		expect(data).toHaveProperty("journalCount");
		expect(data).toHaveProperty("blogCount");
		expect(data).toHaveProperty("intakeCount");
		expect(data).toHaveProperty("pendingPublish");
		expect(data).toHaveProperty("projectCount");
		expect(data).toHaveProperty("activeProjects");
		expect(data).toHaveProperty("recentJournals");
		expect(data).toHaveProperty("activeThreads");
		expect(data).toHaveProperty("seedCount");
		expect(data).toHaveProperty("activeNoteCount");
	});

	test("returns correct journal count", async () => {
		const res = await app.request("/api/dashboard");
		const data = await res.json();
		// fixtures/journal has 1 file
		expect(data.journalCount).toBe(1);
	});

	test("returns active threads from memory", async () => {
		const res = await app.request("/api/dashboard");
		const data = await res.json();
		expect(data.activeThreads.length).toBeGreaterThan(0);
		expect(data.activeThreads[0]).toHaveProperty("name");
		expect(data.activeThreads[0]).toHaveProperty("status", "active");
	});

	test("returns seed count from seeds file", async () => {
		const res = await app.request("/api/dashboard");
		const data = await res.json();
		// fixtures/seeds.json has 1 unused seed
		expect(data.seedCount).toBe(1);
	});

	test("returns active note count", async () => {
		const res = await app.request("/api/dashboard");
		const data = await res.json();
		// fixtures/notes.json has 1 unused note
		expect(data.activeNoteCount).toBe(1);
	});

	test("returns project count and active projects", async () => {
		const res = await app.request("/api/dashboard");
		const data = await res.json();
		// Journal fixture has projects: [distill, vermas]
		expect(data.projectCount).toBe(2);
		expect(data.activeProjects.length).toBeGreaterThan(0);
		expect(data.activeProjects[0]).toHaveProperty("name");
		expect(data.activeProjects[0]).toHaveProperty("lastSeen");
		expect(data.activeProjects[0]).toHaveProperty("journalCount");
	});

	test("activeProjects are ordered by most recently seen first", async () => {
		const res = await app.request("/api/dashboard");
		const data = await res.json();
		// Both distill and vermas appear in the 2026-02-09 fixture, so both have lastSeen = 2026-02-09
		// They should both appear and be sorted by lastSeen descending
		expect(data.activeProjects.length).toBe(2);
		for (let i = 0; i < data.activeProjects.length - 1; i++) {
			expect(data.activeProjects[i].lastSeen >= data.activeProjects[i + 1].lastSeen).toBe(true);
		}
	});
});
