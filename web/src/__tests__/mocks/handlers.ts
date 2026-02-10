import { http, HttpResponse } from "msw";

interface SaveBody {
	content: string;
}

function isValidSaveBody(body: unknown): body is SaveBody {
	return !!body && typeof (body as SaveBody).content === "string";
}

export const handlers = [
	http.get("/api/dashboard", () => {
		return HttpResponse.json({
			journalCount: 5,
			blogCount: 3,
			intakeCount: 2,
			pendingPublish: 1,
			recentJournals: [
				{
					date: "2026-02-09",
					style: "narrative",
					sessionsCount: 3,
					durationMinutes: 120,
					tags: ["journal", "pipeline"],
					projects: ["distill"],
					filename: "journal-2026-02-09-dev-journal.md",
				},
			],
			activeThreads: [
				{
					name: "content-pipeline",
					status: "active",
					mention_count: 5,
					first_seen: "2026-02-01",
					summary: "Building the content pipeline",
				},
			],
			seedCount: 2,
			activeNoteCount: 1,
		});
	}),

	http.get("/api/journal", () => {
		return HttpResponse.json({
			entries: [
				{
					date: "2026-02-09",
					style: "narrative",
					sessionsCount: 3,
					durationMinutes: 120,
					tags: ["journal", "pipeline"],
					projects: ["distill"],
					filename: "journal-2026-02-09-dev-journal.md",
				},
				{
					date: "2026-02-08",
					style: "analytical",
					sessionsCount: 2,
					durationMinutes: 90,
					tags: ["journal", "testing"],
					projects: ["vermas"],
					filename: "journal-2026-02-08-dev-journal.md",
				},
			],
		});
	}),

	http.get("/api/journal/:date", ({ params }) => {
		const { date } = params;
		if (date === "2026-02-09") {
			return HttpResponse.json({
				meta: {
					date: "2026-02-09",
					style: "narrative",
					sessionsCount: 3,
					durationMinutes: 120,
					tags: ["journal"],
					projects: ["distill"],
				},
				content: "# Dev Journal: February 09, 2026\n\nWorked on the content pipeline today.",
			});
		}
		return new HttpResponse(null, { status: 404 });
	}),

	http.put("/api/journal/:date", async ({ request }) => {
		const body = await request.json();
		if (!isValidSaveBody(body)) {
			return HttpResponse.json({ error: "Invalid request body" }, { status: 400 });
		}
		return HttpResponse.json({ success: true });
	}),

	http.get("/api/blog/posts", () => {
		return HttpResponse.json({
			posts: [
				{
					slug: "weekly-2026-W06",
					title: "Week 6: Building the Pipeline",
					date: "2026-02-07",
					postType: "weekly",
					tags: ["pipeline"],
					themes: ["content-pipeline"],
					platformsPublished: ["obsidian"],
				},
			],
		});
	}),

	http.get("/api/blog/posts/:slug", ({ params }) => {
		const { slug } = params;
		if (slug === "weekly-2026-W06") {
			return HttpResponse.json({
				meta: {
					slug: "weekly-2026-W06",
					title: "Week 6: Building the Pipeline",
					date: "2026-02-07",
					postType: "weekly",
					tags: ["pipeline"],
					themes: ["content-pipeline"],
				},
				content: "# Week 6: Building the Pipeline\n\nThis week focused on the pipeline.",
			});
		}
		return new HttpResponse(null, { status: 404 });
	}),

	http.put("/api/blog/posts/:slug", async ({ params, request }) => {
		const { slug } = params;
		if (slug !== "weekly-2026-W06") {
			return HttpResponse.json({ error: "Not found" }, { status: 404 });
		}
		const body = await request.json();
		if (!isValidSaveBody(body)) {
			return HttpResponse.json({ error: "Invalid request body" }, { status: 400 });
		}
		return HttpResponse.json({ success: true });
	}),

	http.get("/api/publish/queue", () => {
		return HttpResponse.json({
			queue: [
				{
					slug: "weekly-2026-W06",
					title: "Week 6: Building the Pipeline",
					postType: "weekly",
					platform: "twitter",
					published: false,
				},
			],
			postizConfigured: false,
		});
	}),

	http.get("/api/publish/integrations", () => {
		return HttpResponse.json({
			configured: false,
			integrations: [],
		});
	}),

	http.get("/api/seeds", () => {
		return HttpResponse.json({
			seeds: [
				{
					id: "seed-1",
					text: "Write about multi-agent patterns",
					tags: ["blog"],
					created_at: "2026-02-09T10:00:00Z",
					used: false,
					used_in: null,
				},
			],
		});
	}),

	http.get("/api/notes", () => {
		return HttpResponse.json({
			notes: [
				{
					id: "note-1",
					text: "Emphasize the pipeline architecture",
					target: "week:2026-W06",
					created_at: "2026-02-09T10:00:00Z",
					used: false,
				},
			],
		});
	}),

	http.get("/api/memory", () => {
		return HttpResponse.json({
			entries: [],
			threads: [
				{
					name: "content-pipeline",
					status: "active",
					mention_count: 5,
					first_seen: "2026-02-01",
					summary: "Building the content pipeline",
				},
			],
			entities: {},
		});
	}),

	http.get("/api/reading/items", ({ request }) => {
		const url = new URL(request.url);
		const source = url.searchParams.get("source");
		const allItems = [
			{
				id: "rss-mock-1",
				url: "https://example.com/article",
				title: "Mock RSS Article",
				excerpt: "A mock RSS article for testing.",
				word_count: 1200,
				author: "Test Author",
				site_name: "example.com",
				source: "rss",
				content_type: "article",
				tags: ["testing"],
				topics: [],
				published_at: "2026-02-09T08:00:00Z",
				saved_at: "2026-02-09T10:00:00Z",
				metadata: {},
			},
			{
				id: "browser-mock-1",
				url: "https://news.ycombinator.com/item?id=99",
				title: "Mock Browser Page",
				excerpt: "A page visited in the browser.",
				word_count: 500,
				author: "",
				site_name: "news.ycombinator.com",
				source: "browser",
				content_type: "article",
				tags: [],
				topics: [],
				published_at: null,
				saved_at: "2026-02-09T14:00:00Z",
				metadata: {},
			},
		];
		const filtered = source ? allItems.filter((i) => i.source === source) : allItems;
		return HttpResponse.json({
			date: "2026-02-09",
			item_count: filtered.length,
			items: filtered,
			available_sources: ["rss", "browser"],
		});
	}),

	http.get("/api/reading/digests", () => {
		return HttpResponse.json({
			digests: [
				{
					date: "2026-02-09",
					sources: ["rss", "browser"],
					itemCount: 15,
					tags: ["ai"],
					filename: "intake-2026-02-09.md",
				},
			],
		});
	}),

	http.get("/api/reading/digests/:date", ({ params }) => {
		const { date } = params;
		if (date === "2026-02-09") {
			return HttpResponse.json({
				meta: {
					date: "2026-02-09",
					sources: ["rss", "browser"],
					itemCount: 15,
					tags: ["ai"],
					filename: "intake-2026-02-09.md",
				},
				content: "# Intake Digest: February 09, 2026\n\nA collection of articles.",
			});
		}
		return new HttpResponse(null, { status: 404 });
	}),

	http.put("/api/reading/digests/:date", async ({ params, request }) => {
		const { date } = params;
		if (date !== "2026-02-09") {
			return HttpResponse.json({ error: "Not found" }, { status: 404 });
		}
		const body = await request.json();
		if (!isValidSaveBody(body)) {
			return HttpResponse.json({ error: "Invalid request body" }, { status: 400 });
		}
		return HttpResponse.json({ success: true });
	}),
];
