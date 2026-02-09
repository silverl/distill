/**
 * Zod schemas — single source of truth for all data types.
 * Used by server for validation and by frontend for type inference.
 */
import { z } from "zod";

// --- Unified Memory ---

export const DailyEntrySchema = z.object({
	date: z.string(), // ISO date string
	sessions: z.array(z.string()).default([]),
	reads: z.array(z.string()).default([]),
	themes: z.array(z.string()).default([]),
	insights: z.array(z.string()).default([]),
	decisions: z.array(z.string()).default([]),
	open_questions: z.array(z.string()).default([]),
});

export const MemoryThreadSchema = z.object({
	name: z.string(),
	summary: z.string(),
	first_seen: z.string(),
	last_seen: z.string(),
	mention_count: z.number().default(1),
	status: z.string().default("active"),
});

export const EntityRecordSchema = z.object({
	name: z.string(),
	entity_type: z.string(),
	first_seen: z.string(),
	last_seen: z.string(),
	mention_count: z.number().default(1),
	context: z.array(z.string()).default([]),
});

export const PublishedRecordSchema = z.object({
	slug: z.string(),
	title: z.string(),
	post_type: z.string(),
	date: z.string(),
	platforms: z.array(z.string()).default([]),
});

export const UnifiedMemorySchema = z.object({
	entries: z.array(DailyEntrySchema).default([]),
	threads: z.array(MemoryThreadSchema).default([]),
	entities: z.record(z.string(), EntityRecordSchema).default({}),
	published: z.array(PublishedRecordSchema).default([]),
});

// --- Blog Memory ---

export const BlogPostSummarySchema = z.object({
	slug: z.string(),
	title: z.string(),
	post_type: z.string(),
	date: z.string(),
	key_points: z.array(z.string()).default([]),
	themes_covered: z.array(z.string()).default([]),
	examples_used: z.array(z.string()).default([]),
	platforms_published: z.array(z.string()).default([]),
	postiz_ids: z.array(z.string()).default([]),
});

export const BlogMemorySchema = z.object({
	posts: z.array(BlogPostSummarySchema).default([]),
});

// --- Blog State ---

export const BlogPostRecordSchema = z.object({
	slug: z.string(),
	post_type: z.string(),
	generated_at: z.string(),
	source_dates: z.array(z.string()).default([]),
	file_path: z.string().default(""),
});

export const BlogStateSchema = z.object({
	posts: z.array(BlogPostRecordSchema).default([]),
});

// --- Seeds ---

export const SeedIdeaSchema = z.object({
	id: z.string(),
	text: z.string(),
	tags: z.array(z.string()).default([]),
	created_at: z.string(),
	used: z.boolean().default(false),
	used_in: z.string().nullable().default(null),
});

export const CreateSeedSchema = z.object({
	text: z.string().min(1),
	tags: z.array(z.string()).default([]),
});

// --- Editorial Notes ---

export const EditorialNoteSchema = z.object({
	id: z.string(),
	text: z.string(),
	target: z.string().default(""),
	created_at: z.string(),
	used: z.boolean().default(false),
});

export const CreateNoteSchema = z.object({
	text: z.string().min(1),
	target: z.string().default(""),
});

// --- Journal Frontmatter ---

export const JournalFrontmatterSchema = z.object({
	date: z.string(),
	type: z.string().default("journal"),
	style: z.string().default("dev-journal"),
	sessions_count: z.number().default(0),
	duration_minutes: z.number().default(0),
	tags: z.array(z.string()).default([]),
	projects: z.array(z.string()).default([]),
	created: z.string().optional(),
});

// --- Blog Frontmatter ---

export const BlogFrontmatterSchema = z.object({
	title: z.string().optional(),
	date: z.string().optional(),
	type: z.string().default("blog"),
	post_type: z.string().optional(),
	week: z.string().optional(),
	slug: z.string().optional(),
	tags: z.array(z.string()).default([]),
	themes: z.array(z.string()).default([]),
	projects: z.array(z.string()).default([]),
	created: z.string().optional(),
});

// --- Intake Frontmatter ---

export const IntakeFrontmatterSchema = z.object({
	date: z.string().optional(),
	type: z.string().default("intake"),
	sources: z.array(z.string()).default([]),
	item_count: z.number().default(0),
	tags: z.array(z.string()).default([]),
	created: z.string().optional(),
});

// --- API Response types ---

export const DashboardResponseSchema = z.object({
	journalCount: z.number(),
	blogCount: z.number(),
	intakeCount: z.number(),
	pendingPublish: z.number(),
	projectCount: z.number(),
	activeProjects: z.array(
		z.object({
			name: z.string(),
			lastSeen: z.string(),
			journalCount: z.number(),
		}),
	),
	recentJournals: z.array(
		z.object({
			date: z.string(),
			style: z.string(),
			sessionsCount: z.number(),
			durationMinutes: z.number(),
			projects: z.array(z.string()),
		}),
	),
	activeThreads: z.array(MemoryThreadSchema),
	recentlyPublished: z.array(PublishedRecordSchema),
	seedCount: z.number(),
	activeNoteCount: z.number(),
});

export const JournalEntrySchema = z.object({
	date: z.string(),
	style: z.string(),
	sessionsCount: z.number(),
	durationMinutes: z.number(),
	tags: z.array(z.string()),
	projects: z.array(z.string()),
	filename: z.string(),
});

export const JournalDetailSchema = z.object({
	meta: JournalEntrySchema,
	content: z.string(),
});

export const BlogPostSchema = z.object({
	slug: z.string(),
	title: z.string(),
	postType: z.string(),
	date: z.string(),
	tags: z.array(z.string()),
	themes: z.array(z.string()),
	projects: z.array(z.string()),
	filename: z.string(),
	platformsPublished: z.array(z.string()),
});

export const BlogDetailSchema = z.object({
	meta: BlogPostSchema,
	content: z.string(),
});

export const IntakeDigestSchema = z.object({
	date: z.string(),
	sources: z.array(z.string()),
	itemCount: z.number(),
	tags: z.array(z.string()),
	filename: z.string(),
});

export const IntakeDetailSchema = z.object({
	meta: IntakeDigestSchema,
	content: z.string(),
});

export const PublishQueueItemSchema = z.object({
	slug: z.string(),
	title: z.string(),
	postType: z.string(),
	date: z.string(),
	platform: z.string(),
	published: z.boolean(),
});

export const PublishRequestSchema = z.object({
	platform: z.string(),
	mode: z.enum(["draft", "schedule", "now"]).default("draft"),
	integrationId: z.string().optional(),
});

export const PostizIntegrationSchema = z.object({
	id: z.string(),
	name: z.string(),
	provider: z.string(),
	identifier: z.string().default(""),
});

// --- Distill Config (mirrors Python DistillConfig) ---

export const OutputConfigSchema = z.object({
	directory: z.string().default("./insights"),
});

export const SessionsConfigSchema = z.object({
	sources: z.array(z.string()).default(["claude", "codex"]),
	include_global: z.boolean().default(false),
	since_days: z.number().default(2),
});

export const JournalConfigSchema = z.object({
	style: z.string().default("dev-journal"),
	target_word_count: z.number().default(600),
	model: z.string().nullable().default(null),
	memory_window_days: z.number().default(7),
});

export const BlogConfigSchema = z.object({
	target_word_count: z.number().default(1200),
	include_diagrams: z.boolean().default(true),
	model: z.string().nullable().default(null),
	platforms: z.array(z.string()).default(["obsidian"]),
});

export const IntakeConfigSchema = z.object({
	feeds_file: z.string().default(""),
	opml_file: z.string().default(""),
	use_defaults: z.boolean().default(true),
	browser_history: z.boolean().default(false),
	substack_blogs: z.array(z.string()).default([]),
	rss_feeds: z.array(z.string()).default([]),
	target_word_count: z.number().default(800),
	model: z.string().nullable().default(null),
	publishers: z.array(z.string()).default(["obsidian"]),
});

export const GhostConfigSchema = z.object({
	url: z.string().default(""),
	admin_api_key: z.string().default(""),
	newsletter_slug: z.string().default(""),
	auto_publish: z.boolean().default(true),
});

export const PostizConfigSchema = z.object({
	url: z.string().default(""),
	api_key: z.string().default(""),
	default_type: z.string().default("draft"),
	schedule_enabled: z.boolean().default(false),
});

export const RedditConfigSchema = z.object({
	client_id: z.string().default(""),
	client_secret: z.string().default(""),
	username: z.string().default(""),
});

export const YouTubeConfigSchema = z.object({
	api_key: z.string().default(""),
});

export const NotificationsConfigSchema = z.object({
	slack_webhook: z.string().default(""),
	ntfy_url: z.string().default(""),
	ntfy_topic: z.string().default("distill"),
	enabled: z.boolean().default(true),
});

export const ProjectConfigSchema = z.object({
	name: z.string(),
	description: z.string(),
	url: z.string().default(""),
	tags: z.array(z.string()).default([]),
});

export const DistillConfigSchema = z.object({
	output: OutputConfigSchema.default({}),
	sessions: SessionsConfigSchema.default({}),
	journal: JournalConfigSchema.default({}),
	blog: BlogConfigSchema.default({}),
	intake: IntakeConfigSchema.default({}),
	ghost: GhostConfigSchema.default({}),
	postiz: PostizConfigSchema.default({}),
	reddit: RedditConfigSchema.default({}),
	youtube: YouTubeConfigSchema.default({}),
	notifications: NotificationsConfigSchema.default({}),
	projects: z.array(ProjectConfigSchema).default([]),
});

// --- Source Status ---

export const SourceStatusSchema = z.object({
	source: z.string(),
	configured: z.boolean(),
	label: z.string(),
	description: z.string().default(""),
	availability: z.enum(["available", "coming_soon"]).default("available"),
});

// --- Pipeline Status ---

export const PipelineStatusSchema = z.object({
	status: z.enum(["idle", "running", "completed", "failed"]),
	log: z.string().default(""),
	startedAt: z.string().nullable().default(null),
	completedAt: z.string().nullable().default(null),
	error: z.string().nullable().default(null),
});

export const PipelineRunResponseSchema = z.object({
	id: z.string(),
	started: z.boolean(),
});

// --- Project views ---

export const ProjectSummarySchema = z.object({
	name: z.string(),
	description: z.string(),
	url: z.string().default(""),
	tags: z.array(z.string()).default([]),
	journalCount: z.number(),
	blogCount: z.number(),
	totalSessions: z.number(),
	totalDurationMinutes: z.number(),
	lastSeen: z.string(),
	hasProjectNote: z.boolean(),
});

export const ProjectDetailSchema = z.object({
	summary: ProjectSummarySchema,
	journals: z.array(JournalEntrySchema),
	blogs: z.array(BlogPostSchema),
	projectNoteContent: z.string().nullable(),
});

// --- Save (edit) ---

export const SaveMarkdownSchema = z.object({
	content: z.string(),
});

export type SaveMarkdown = z.infer<typeof SaveMarkdownSchema>;

// --- Inferred types ---

export type DailyEntry = z.infer<typeof DailyEntrySchema>;
export type MemoryThread = z.infer<typeof MemoryThreadSchema>;
export type EntityRecord = z.infer<typeof EntityRecordSchema>;
export type PublishedRecord = z.infer<typeof PublishedRecordSchema>;
export type UnifiedMemory = z.infer<typeof UnifiedMemorySchema>;
export type BlogPostSummary = z.infer<typeof BlogPostSummarySchema>;
export type BlogMemory = z.infer<typeof BlogMemorySchema>;
export type BlogPostRecord = z.infer<typeof BlogPostRecordSchema>;
export type BlogState = z.infer<typeof BlogStateSchema>;
export type SeedIdea = z.infer<typeof SeedIdeaSchema>;
export type CreateSeed = z.infer<typeof CreateSeedSchema>;
export type EditorialNote = z.infer<typeof EditorialNoteSchema>;
export type CreateNote = z.infer<typeof CreateNoteSchema>;
export type JournalFrontmatter = z.infer<typeof JournalFrontmatterSchema>;
export type BlogFrontmatter = z.infer<typeof BlogFrontmatterSchema>;
export type IntakeFrontmatter = z.infer<typeof IntakeFrontmatterSchema>;
export type DashboardResponse = z.infer<typeof DashboardResponseSchema>;
export type JournalEntry = z.infer<typeof JournalEntrySchema>;
export type JournalDetail = z.infer<typeof JournalDetailSchema>;
export type BlogPost = z.infer<typeof BlogPostSchema>;
export type BlogDetail = z.infer<typeof BlogDetailSchema>;
export type IntakeDigest = z.infer<typeof IntakeDigestSchema>;
export type IntakeDetail = z.infer<typeof IntakeDetailSchema>;
export type PublishQueueItem = z.infer<typeof PublishQueueItemSchema>;
export type PublishRequest = z.infer<typeof PublishRequestSchema>;
export type PostizIntegration = z.infer<typeof PostizIntegrationSchema>;
export type OutputConfig = z.infer<typeof OutputConfigSchema>;
export type SessionsConfig = z.infer<typeof SessionsConfigSchema>;
export type JournalConfig = z.infer<typeof JournalConfigSchema>;
export type BlogConfig = z.infer<typeof BlogConfigSchema>;
export type IntakeConfig = z.infer<typeof IntakeConfigSchema>;
export type GhostConfig = z.infer<typeof GhostConfigSchema>;
export type PostizConfig = z.infer<typeof PostizConfigSchema>;
export type RedditConfig = z.infer<typeof RedditConfigSchema>;
export type YouTubeConfig = z.infer<typeof YouTubeConfigSchema>;
export type NotificationsConfig = z.infer<typeof NotificationsConfigSchema>;
export type ProjectConfig = z.infer<typeof ProjectConfigSchema>;
export type DistillConfig = z.infer<typeof DistillConfigSchema>;
export type SourceStatus = z.infer<typeof SourceStatusSchema>;
export type PipelineStatus = z.infer<typeof PipelineStatusSchema>;
export type PipelineRunResponse = z.infer<typeof PipelineRunResponseSchema>;
export type ProjectSummary = z.infer<typeof ProjectSummarySchema>;
export type ProjectDetail = z.infer<typeof ProjectDetailSchema>;
