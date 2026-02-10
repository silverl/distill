import { afterAll, beforeEach, describe, expect, test } from "bun:test";
import { join } from "node:path";
import { app } from "../index.js";
import { resetConfig, setConfig } from "../lib/config.js";

const FIXTURES_DIR = join(import.meta.dir, "fixtures");

describe("Reading Items API", () => {
	beforeEach(() => {
		setConfig({
			OUTPUT_DIR: FIXTURES_DIR,
			PORT: 3001,
			PROJECT_DIR: "",
			POSTIZ_URL: "",
			POSTIZ_API_KEY: "",
		});
	});

	afterAll(() => {
		resetConfig();
	});

	test("GET /api/reading/items?date= returns all items for a date", async () => {
		const res = await app.request("/api/reading/items?date=2026-02-09");
		expect(res.status).toBe(200);
		const data = await res.json();
		expect(data.date).toBe("2026-02-09");
		expect(data.item_count).toBe(3);
		expect(data.items).toHaveLength(3);
		// Verify body was stripped by Zod
		for (const item of data.items) {
			expect(item).not.toHaveProperty("body");
		}
	});

	test("GET /api/reading/items?date=&source= filters by source", async () => {
		const res = await app.request("/api/reading/items?date=2026-02-09&source=browser");
		expect(res.status).toBe(200);
		const data = await res.json();
		expect(data.item_count).toBe(1);
		expect(data.items).toHaveLength(1);
		expect(data.items[0].source).toBe("browser");
		expect(data.items[0].id).toBe("browser-001");
	});

	test("available_sources includes all sources before filtering", async () => {
		const res = await app.request("/api/reading/items?date=2026-02-09&source=rss");
		expect(res.status).toBe(200);
		const data = await res.json();
		// Even though filtered to rss, available_sources should have all 3
		expect(data.available_sources).toContain("rss");
		expect(data.available_sources).toContain("browser");
		expect(data.available_sources).toContain("substack");
		expect(data.available_sources).toHaveLength(3);
	});

	test("returns empty for missing date", async () => {
		const res = await app.request("/api/reading/items?date=2099-01-01");
		expect(res.status).toBe(200);
		const data = await res.json();
		expect(data.item_count).toBe(0);
		expect(data.items).toHaveLength(0);
		expect(data.available_sources).toHaveLength(0);
	});

	test("returns dates list when no date param provided", async () => {
		const res = await app.request("/api/reading/items");
		expect(res.status).toBe(200);
		const data = await res.json();
		expect(data.dates).toContain("2026-02-09");
		expect(data.items).toHaveLength(0);
	});
});
