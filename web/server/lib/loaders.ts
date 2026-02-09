/**
 * Shared data-loading helpers for journal entries and blog posts.
 * Used by journal, blog, projects, and dashboard routes.
 */
import { basename, join } from "node:path";
import {
	BlogFrontmatterSchema,
	BlogMemorySchema,
	type BlogPost,
	type JournalEntry,
	JournalFrontmatterSchema,
} from "../../shared/schemas.js";
import { listFiles, readJson, readMarkdown } from "./files.js";
import { parseFrontmatter } from "./frontmatter.js";

/**
 * Parse all journal files into JournalEntry objects, sorted by date descending.
 */
export async function loadJournalEntries(outputDir: string): Promise<JournalEntry[]> {
	const files = await listFiles(join(outputDir, "journal"), /^journal-.*\.md$/);
	const entries: JournalEntry[] = [];
	for (const file of files) {
		const raw = await readMarkdown(file);
		if (!raw) continue;
		const parsed = parseFrontmatter(raw, JournalFrontmatterSchema);
		if (parsed) {
			entries.push({
				date: parsed.frontmatter.date,
				style: parsed.frontmatter.style,
				sessionsCount: parsed.frontmatter.sessions_count,
				durationMinutes: parsed.frontmatter.duration_minutes,
				tags: parsed.frontmatter.tags,
				projects: parsed.frontmatter.projects,
				filename: basename(file),
			});
		}
	}
	entries.sort((a, b) => b.date.localeCompare(a.date));
	return entries;
}

/**
 * Collect all blog markdown files from weekly + themes directories.
 */
export async function collectBlogFiles(outputDir: string): Promise<string[]> {
	const [weeklyFiles, thematicFiles] = await Promise.all([
		listFiles(join(outputDir, "blog", "weekly"), /\.md$/),
		listFiles(join(outputDir, "blog", "themes"), /\.md$/),
	]);
	return [...weeklyFiles, ...thematicFiles];
}

/**
 * Parse all blog files into BlogPost objects, sorted by date descending.
 */
export async function loadBlogPosts(outputDir: string): Promise<BlogPost[]> {
	const [files, blogMemory] = await Promise.all([
		collectBlogFiles(outputDir),
		readJson(join(outputDir, "blog", ".blog-memory.json"), BlogMemorySchema),
	]);

	const posts: BlogPost[] = [];
	for (const file of files) {
		const raw = await readMarkdown(file);
		if (!raw) continue;
		const parsed = parseFrontmatter(raw, BlogFrontmatterSchema);
		if (parsed) {
			const slug = parsed.frontmatter.slug ?? basename(file, ".md");
			const memoryPost = blogMemory?.posts.find((p) => p.slug === slug);
			posts.push({
				slug,
				title: parsed.frontmatter.title ?? slug,
				postType: parsed.frontmatter.post_type ?? "unknown",
				date: parsed.frontmatter.date ?? "",
				tags: parsed.frontmatter.tags,
				themes: parsed.frontmatter.themes,
				projects: parsed.frontmatter.projects,
				filename: basename(file),
				platformsPublished: memoryPost?.platforms_published ?? [],
			});
		}
	}
	posts.sort((a, b) => b.date.localeCompare(a.date));
	return posts;
}
