import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type {
	DistillConfig,
	EditorialNote,
	PostizIntegration,
	SourceStatus,
} from "../../shared/schemas.js";

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

const TABS = ["Sources", "Publishing", "Pipeline", "Editorial"] as const;
type Tab = (typeof TABS)[number];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const inputClass =
	"w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1";
const sectionClass = "rounded-lg border border-zinc-200 p-4 dark:border-zinc-800 space-y-4";
const saveButtonClass =
	"rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50";

function StatusDot({ ok }: { ok: boolean }) {
	return (
		<span
			className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-green-500" : "bg-zinc-300 dark:bg-zinc-600"}`}
		/>
	);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Settings() {
	const [activeTab, setActiveTab] = useState<Tab>("Sources");

	return (
		<div className="space-y-6">
			<h2 className="text-2xl font-bold">Settings</h2>

			{/* Tab bar */}
			<div className="flex border-b border-zinc-200 dark:border-zinc-700">
				{TABS.map((tab) => (
					<button
						key={tab}
						type="button"
						onClick={() => setActiveTab(tab)}
						className={`px-4 py-2 text-sm font-medium ${activeTab === tab ? "border-b-2 border-indigo-600 text-indigo-600" : "text-zinc-500 hover:text-zinc-700"}`}
					>
						{tab}
					</button>
				))}
			</div>

			{/* Tab content */}
			{activeTab === "Sources" && <SourcesTab />}
			{activeTab === "Publishing" && <PublishingTab />}
			{activeTab === "Pipeline" && <PipelineTab />}
			{activeTab === "Editorial" && <EditorialTab />}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tab 1: Sources
// ---------------------------------------------------------------------------

function SourcesTab() {
	const queryClient = useQueryClient();

	const { data: config } = useQuery<DistillConfig>({
		queryKey: ["config"],
		queryFn: async () => {
			const res = await fetch("/api/config");
			if (!res.ok) throw new Error("Failed to load config");
			return res.json();
		},
	});

	const { data: sourcesData } = useQuery<{ sources: SourceStatus[] }>({
		queryKey: ["config-sources"],
		queryFn: async () => {
			const res = await fetch("/api/config/sources");
			if (!res.ok) throw new Error("Failed to load sources");
			return res.json();
		},
	});

	const [vermas, setVermas] = useState(false);
	const [rssEnabled, setRssEnabled] = useState(true);
	const [useDefaults, setUseDefaults] = useState(true);
	const [customFeeds, setCustomFeeds] = useState("");
	const [browserHistory, setBrowserHistory] = useState(false);
	const [substackEnabled, setSubstackEnabled] = useState(false);
	const [substackUrls, setSubstackUrls] = useState("");

	// Sync from fetched config
	useEffect(() => {
		if (!config) return;
		const sources = config.sessions?.sources ?? [];
		setVermas(sources.includes("vermas"));
		setUseDefaults(config.intake?.use_defaults ?? true);
		setCustomFeeds((config.intake?.rss_feeds ?? []).join("\n"));
		setBrowserHistory(config.intake?.browser_history ?? false);
		const blogs = config.intake?.substack_blogs ?? [];
		setSubstackEnabled(blogs.length > 0);
		setSubstackUrls(blogs.join("\n"));
	}, [config]);

	const saveMutation = useMutation({
		mutationFn: async (updates: Record<string, unknown>) => {
			const res = await fetch("/api/config", {
				method: "PUT",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(updates),
			});
			if (!res.ok) throw new Error("Failed to save config");
			return res.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["config"] });
			queryClient.invalidateQueries({ queryKey: ["config-sources"] });
		},
	});

	function handleSave() {
		const sessionSources = ["claude", "codex"];
		if (vermas) sessionSources.push("vermas");

		const substackBlogs = substackEnabled
			? substackUrls
					.split("\n")
					.map((u) => u.trim())
					.filter(Boolean)
			: [];

		const rssFeeds = customFeeds
			.split("\n")
			.map((u) => u.trim())
			.filter(Boolean);

		saveMutation.mutate({
			sessions: { sources: sessionSources },
			intake: {
				use_defaults: useDefaults,
				browser_history: browserHistory,
				substack_blogs: substackBlogs,
				rss_feeds: rssFeeds,
			},
		});
	}

	const comingSoonSources = (sourcesData?.sources ?? []).filter(
		(s) => s.availability === "coming_soon",
	);

	return (
		<div className="space-y-6">
			{/* Sessions */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Sessions</h3>
				<p className="text-sm text-zinc-500">
					Claude and Codex sessions are auto-detected from local directories.
				</p>
				<div className="flex items-center gap-2">
					<StatusDot ok />
					<span className="text-sm">Claude</span>
					<span className="text-xs text-zinc-400">(auto-detected)</span>
				</div>
				<div className="flex items-center gap-2">
					<StatusDot ok />
					<span className="text-sm">Codex</span>
					<span className="text-xs text-zinc-400">(auto-detected)</span>
				</div>
				<label className="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						checked={vermas}
						onChange={(e) => setVermas(e.target.checked)}
						className="rounded border-zinc-300"
					/>
					VerMAS session parsing
				</label>
			</div>

			{/* RSS */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">RSS Feeds</h3>
				<label className="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						checked={rssEnabled}
						onChange={(e) => setRssEnabled(e.target.checked)}
						className="rounded border-zinc-300"
					/>
					Enable RSS ingestion
				</label>
				{rssEnabled && (
					<>
						<label className="flex items-center gap-2 text-sm">
							<input
								type="checkbox"
								checked={useDefaults}
								onChange={(e) => setUseDefaults(e.target.checked)}
								className="rounded border-zinc-300"
							/>
							Use default feeds (90+ curated tech blogs)
						</label>
						<label className={labelClass}>
							Custom feed URLs (one per line)
							<textarea
								value={customFeeds}
								onChange={(e) => setCustomFeeds(e.target.value)}
								rows={4}
								placeholder="https://blog.example.com/feed"
								className={inputClass}
							/>
						</label>
						<p className="text-xs text-zinc-400">
							Custom feeds are used alongside defaults when both are enabled.
						</p>
					</>
				)}
			</div>

			{/* Browser History */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Browser History</h3>
				<label className="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						checked={browserHistory}
						onChange={(e) => setBrowserHistory(e.target.checked)}
						className="rounded border-zinc-300"
					/>
					Ingest recent browser history (Chrome / Safari)
				</label>
			</div>

			{/* Substack */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Substack</h3>
				<label className="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						checked={substackEnabled}
						onChange={(e) => setSubstackEnabled(e.target.checked)}
						className="rounded border-zinc-300"
					/>
					Enable Substack ingestion
				</label>
				{substackEnabled && (
					<label className={labelClass}>
						Blog URLs (one per line)
						<textarea
							value={substackUrls}
							onChange={(e) => setSubstackUrls(e.target.value)}
							rows={3}
							placeholder="https://example.substack.com"
							className={inputClass}
						/>
					</label>
				)}
			</div>

			{/* Coming Soon sources */}
			{comingSoonSources.length > 0 && (
				<div className={sectionClass}>
					<h3 className="text-base font-semibold">Coming Soon</h3>
					<p className="text-sm text-zinc-500">
						These sources are planned for future releases.
					</p>
					<div className="space-y-2">
						{comingSoonSources.map((s) => (
							<div key={s.source} className="flex items-center gap-2 text-sm">
								<span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-300">
									Soon
								</span>
								<span>{s.label}</span>
								<span className="text-xs text-zinc-400">{s.description}</span>
							</div>
						))}
					</div>
				</div>
			)}

			<button
				type="button"
				onClick={handleSave}
				disabled={saveMutation.isPending}
				className={saveButtonClass}
			>
				{saveMutation.isPending ? "Saving..." : "Save Sources"}
			</button>
			{saveMutation.isSuccess && <span className="ml-3 text-sm text-green-600">Saved</span>}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tab 2: Publishing
// ---------------------------------------------------------------------------

function PublishingTab() {
	const queryClient = useQueryClient();

	const { data: config } = useQuery<DistillConfig>({
		queryKey: ["config"],
		queryFn: async () => {
			const res = await fetch("/api/config");
			if (!res.ok) throw new Error("Failed to load config");
			return res.json();
		},
	});

	const { data: integrationsData } = useQuery<{
		integrations: PostizIntegration[];
		configured: boolean;
	}>({
		queryKey: ["integrations"],
		queryFn: async () => {
			const res = await fetch("/api/publish/integrations");
			if (!res.ok) throw new Error("Failed");
			return res.json();
		},
	});

	const [ghostUrl, setGhostUrl] = useState("");
	const [ghostApiKey, setGhostApiKey] = useState("");
	const [ghostNewsletter, setGhostNewsletter] = useState("");
	const [platforms, setPlatforms] = useState<string[]>(["obsidian"]);

	useEffect(() => {
		if (!config) return;
		setGhostUrl(config.ghost?.url ?? "");
		setGhostApiKey(config.ghost?.admin_api_key ?? "");
		setGhostNewsletter(config.ghost?.newsletter_slug ?? "");
		setPlatforms(config.blog?.platforms ?? ["obsidian"]);
	}, [config]);

	const saveMutation = useMutation({
		mutationFn: async (updates: Record<string, unknown>) => {
			const res = await fetch("/api/config", {
				method: "PUT",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(updates),
			});
			if (!res.ok) throw new Error("Failed to save config");
			return res.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["config"] });
		},
	});

	const allPlatforms = ["obsidian", "ghost", "markdown", "twitter", "linkedin", "reddit"];

	function togglePlatform(p: string) {
		setPlatforms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
	}

	function handleSave() {
		saveMutation.mutate({
			ghost: {
				url: ghostUrl,
				admin_api_key: ghostApiKey,
				newsletter_slug: ghostNewsletter,
			},
			blog: { platforms },
		});
	}

	return (
		<div className="space-y-6">
			{/* Obsidian */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Obsidian</h3>
				<div className="flex items-center gap-2 text-sm">
					<StatusDot ok />
					<span>Always enabled (default output format)</span>
				</div>
			</div>

			{/* Ghost */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Ghost CMS</h3>
				<label className={labelClass}>
					Ghost URL
					<input
						type="url"
						value={ghostUrl}
						onChange={(e) => setGhostUrl(e.target.value)}
						placeholder="https://your-ghost-site.com"
						className={inputClass}
					/>
				</label>
				<label className={labelClass}>
					Admin API Key
					<input
						type="password"
						value={ghostApiKey}
						onChange={(e) => setGhostApiKey(e.target.value)}
						placeholder="xxxxxxxxxxxxxxxxxxxxxxxx:yyyyyyyy..."
						className={inputClass}
					/>
				</label>
				<label className={labelClass}>
					Newsletter Slug
					<input
						type="text"
						value={ghostNewsletter}
						onChange={(e) => setGhostNewsletter(e.target.value)}
						placeholder="default-newsletter"
						className={inputClass}
					/>
				</label>
			</div>

			{/* Postiz */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Postiz</h3>
				{integrationsData?.configured ? (
					<div>
						<div className="flex items-center gap-2 text-sm">
							<StatusDot ok />
							<span className="text-green-600">Connected</span>
						</div>
						{(integrationsData.integrations ?? []).length > 0 && (
							<div className="mt-2 space-y-1">
								{integrationsData.integrations.map((i) => (
									<div key={i.id} className="text-sm text-zinc-600 dark:text-zinc-400">
										{i.name} ({i.provider})
									</div>
								))}
							</div>
						)}
					</div>
				) : (
					<div className="flex items-center gap-2 text-sm">
						<StatusDot ok={false} />
						<span className="text-zinc-500">
							Not configured. Set <code className="text-xs">POSTIZ_URL</code> and{" "}
							<code className="text-xs">POSTIZ_API_KEY</code> environment variables.
						</span>
					</div>
				)}
			</div>

			{/* Platforms */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Blog Output Platforms</h3>
				<p className="text-sm text-zinc-500">
					Select which platforms blog posts are generated for.
				</p>
				<div className="flex flex-wrap gap-4">
					{allPlatforms.map((p) => (
						<label key={p} className="flex items-center gap-2 text-sm">
							<input
								type="checkbox"
								checked={platforms.includes(p)}
								onChange={() => togglePlatform(p)}
								disabled={p === "obsidian"}
								className="rounded border-zinc-300"
							/>
							{p}
						</label>
					))}
				</div>
			</div>

			<button
				type="button"
				onClick={handleSave}
				disabled={saveMutation.isPending}
				className={saveButtonClass}
			>
				{saveMutation.isPending ? "Saving..." : "Save Publishing"}
			</button>
			{saveMutation.isSuccess && <span className="ml-3 text-sm text-green-600">Saved</span>}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tab 3: Pipeline
// ---------------------------------------------------------------------------

function PipelineTab() {
	const queryClient = useQueryClient();

	const { data: config } = useQuery<DistillConfig>({
		queryKey: ["config"],
		queryFn: async () => {
			const res = await fetch("/api/config");
			if (!res.ok) throw new Error("Failed to load config");
			return res.json();
		},
	});

	const [model, setModel] = useState("");
	const [sessionSources, setSessionSources] = useState<string[]>(["claude", "codex"]);
	const [journalWords, setJournalWords] = useState(600);
	const [blogWords, setBlogWords] = useState(1200);
	const [intakeWords, setIntakeWords] = useState(800);

	useEffect(() => {
		if (!config) return;
		setModel(config.journal?.model ?? "");
		setSessionSources(config.sessions?.sources ?? ["claude", "codex"]);
		setJournalWords(config.journal?.target_word_count ?? 600);
		setBlogWords(config.blog?.target_word_count ?? 1200);
		setIntakeWords(config.intake?.target_word_count ?? 800);
	}, [config]);

	const saveMutation = useMutation({
		mutationFn: async (updates: Record<string, unknown>) => {
			const res = await fetch("/api/config", {
				method: "PUT",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(updates),
			});
			if (!res.ok) throw new Error("Failed to save config");
			return res.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["config"] });
		},
	});

	const allSessionSources = ["claude", "codex", "vermas"];

	function toggleSource(s: string) {
		setSessionSources((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
	}

	function handleSave() {
		saveMutation.mutate({
			sessions: { sources: sessionSources },
			journal: {
				target_word_count: journalWords,
				model: model || null,
			},
			blog: { target_word_count: blogWords },
			intake: { target_word_count: intakeWords },
		});
	}

	return (
		<div className="space-y-6">
			{/* Model */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">LLM Model</h3>
				<label className={labelClass}>
					Model override
					<input
						type="text"
						value={model}
						onChange={(e) => setModel(e.target.value)}
						placeholder="Leave empty for default"
						className={inputClass}
					/>
				</label>
				<p className="mt-1 text-xs text-zinc-400">
					Overrides the model used for journal, blog, and intake synthesis.
				</p>
			</div>

			{/* Session sources */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Session Sources</h3>
				<div className="flex flex-wrap gap-4">
					{allSessionSources.map((s) => (
						<label key={s} className="flex items-center gap-2 text-sm">
							<input
								type="checkbox"
								checked={sessionSources.includes(s)}
								onChange={() => toggleSource(s)}
								className="rounded border-zinc-300"
							/>
							{s}
						</label>
					))}
				</div>
			</div>

			{/* Word count targets */}
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Word Count Targets</h3>
				<div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
					<label className={labelClass}>
						Journal
						<input
							type="number"
							value={journalWords}
							onChange={(e) => setJournalWords(Number(e.target.value))}
							min={100}
							max={5000}
							className={inputClass}
						/>
					</label>
					<label className={labelClass}>
						Blog
						<input
							type="number"
							value={blogWords}
							onChange={(e) => setBlogWords(Number(e.target.value))}
							min={100}
							max={5000}
							className={inputClass}
						/>
					</label>
					<label className={labelClass}>
						Intake
						<input
							type="number"
							value={intakeWords}
							onChange={(e) => setIntakeWords(Number(e.target.value))}
							min={100}
							max={5000}
							className={inputClass}
						/>
					</label>
				</div>
			</div>

			<button
				type="button"
				onClick={handleSave}
				disabled={saveMutation.isPending}
				className={saveButtonClass}
			>
				{saveMutation.isPending ? "Saving..." : "Save Pipeline"}
			</button>
			{saveMutation.isSuccess && <span className="ml-3 text-sm text-green-600">Saved</span>}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tab 4: Editorial
// ---------------------------------------------------------------------------

function EditorialTab() {
	const queryClient = useQueryClient();
	const [newNote, setNewNote] = useState("");
	const [newTarget, setNewTarget] = useState("");

	const { data: notesData } = useQuery<{ notes: EditorialNote[] }>({
		queryKey: ["notes"],
		queryFn: async () => {
			const res = await fetch("/api/notes");
			if (!res.ok) throw new Error("Failed to load notes");
			return res.json();
		},
	});

	const addNote = useMutation({
		mutationFn: async ({ text, target }: { text: string; target: string }) => {
			const res = await fetch("/api/notes", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ text, target }),
			});
			if (!res.ok) throw new Error("Failed to add note");
			return res.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["notes"] });
			setNewNote("");
			setNewTarget("");
		},
	});

	const deleteNote = useMutation({
		mutationFn: async (id: string) => {
			const res = await fetch(`/api/notes/${id}`, { method: "DELETE" });
			if (!res.ok) throw new Error("Failed to delete note");
		},
		onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notes"] }),
	});

	const notes = notesData?.notes ?? [];

	return (
		<div className="space-y-6">
			<div className={sectionClass}>
				<h3 className="text-base font-semibold">Editorial Notes</h3>
				<p className="text-sm text-zinc-500">
					Steer blog content by adding editorial direction. Notes can be scoped to a specific week
					or topic.
				</p>
				<form
					className="space-y-2"
					onSubmit={(e) => {
						e.preventDefault();
						if (newNote.trim()) addNote.mutate({ text: newNote.trim(), target: newTarget });
					}}
				>
					<input
						type="text"
						value={newNote}
						onChange={(e) => setNewNote(e.target.value)}
						placeholder="Add editorial direction..."
						className={inputClass}
					/>
					<div className="flex gap-2">
						<input
							type="text"
							value={newTarget}
							onChange={(e) => setNewTarget(e.target.value)}
							placeholder="Target (e.g., week:2026-W06)"
							className={`flex-1 ${inputClass}`}
						/>
						<button
							type="submit"
							disabled={!newNote.trim() || addNote.isPending}
							className={saveButtonClass}
						>
							Add Note
						</button>
					</div>
				</form>
			</div>

			{notes.length === 0 ? (
				<p className="text-sm text-zinc-500">No editorial notes.</p>
			) : (
				<div className="space-y-2">
					{notes.map((note) => (
						<div
							key={note.id}
							className="flex items-start justify-between rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
						>
							<div>
								<span className={note.used ? "text-zinc-400 line-through" : ""}>{note.text}</span>
								{note.target && (
									<span className="ml-2 rounded bg-purple-50 px-1.5 py-0.5 text-xs text-purple-700 dark:bg-purple-950 dark:text-purple-300">
										{note.target}
									</span>
								)}
							</div>
							<button
								type="button"
								onClick={() => deleteNote.mutate(note.id)}
								className="ml-2 text-xs text-red-500 hover:text-red-700"
							>
								Delete
							</button>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
