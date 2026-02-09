import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import type { ProjectDetail } from "../../shared/schemas.js";
import { DateBadge } from "../components/shared/DateBadge.js";
import { MarkdownRenderer } from "../components/shared/MarkdownRenderer.js";
import { TagBadge } from "../components/shared/TagBadge.js";

export default function ProjectDetailPage() {
	const { name } = useParams({ from: "/projects/$name" });
	const { data, isLoading, error } = useQuery<ProjectDetail>({
		queryKey: ["projects", name],
		queryFn: async () => {
			const res = await fetch(`/api/projects/${encodeURIComponent(name)}`);
			if (!res.ok) throw new Error("Project not found");
			return res.json();
		},
	});

	if (isLoading) return <div className="animate-pulse text-zinc-400">Loading...</div>;
	if (error) return <div className="text-red-500">Error: {error.message}</div>;
	if (!data) return null;

	const { summary, journals, blogs, projectNoteContent } = data;

	return (
		<div className="space-y-6">
			<Link
				to="/projects"
				className="text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
			>
				&larr; Projects
			</Link>

			{/* Header */}
			<div>
				<h2 className="text-2xl font-bold">{summary.name}</h2>
				{summary.description && (
					<p className="mt-1 text-zinc-600 dark:text-zinc-400">{summary.description}</p>
				)}
				{summary.url && (
					<a
						href={summary.url}
						target="_blank"
						rel="noopener noreferrer"
						className="mt-1 inline-block text-sm text-indigo-600 hover:underline dark:text-indigo-400"
					>
						{summary.url}
					</a>
				)}
			</div>

			{/* Stats grid */}
			<div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
				<StatCard label="Journal entries" value={summary.journalCount} />
				<StatCard label="Blog posts" value={summary.blogCount} />
				<StatCard label="Sessions" value={summary.totalSessions} />
				<StatCard label="Total time" value={`${Math.round(summary.totalDurationMinutes / 60)}h`} />
			</div>

			{/* Tags */}
			{summary.tags.length > 0 && (
				<div className="flex flex-wrap gap-1">
					{summary.tags.map((t) => (
						<TagBadge key={t} tag={t} />
					))}
				</div>
			)}

			{/* Project note */}
			{projectNoteContent && (
				<section>
					<h3 className="mb-3 text-lg font-semibold">Project Note</h3>
					<div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
						<MarkdownRenderer content={projectNoteContent} />
					</div>
				</section>
			)}

			{/* Journal entries */}
			{journals.length > 0 && (
				<section>
					<h3 className="mb-3 text-lg font-semibold">Journal Entries ({journals.length})</h3>
					<div className="space-y-2">
						{journals.map((entry) => (
							<Link
								key={entry.filename}
								to="/journal/$date"
								params={{ date: entry.date }}
								className="block rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
							>
								<div className="flex items-center justify-between">
									<DateBadge date={entry.date} />
									<span className="text-xs text-zinc-500">
										{entry.sessionsCount} sessions, {entry.durationMinutes}m
									</span>
								</div>
							</Link>
						))}
					</div>
				</section>
			)}

			{/* Blog posts */}
			{blogs.length > 0 && (
				<section>
					<h3 className="mb-3 text-lg font-semibold">Blog Posts ({blogs.length})</h3>
					<div className="space-y-2">
						{blogs.map((post) => (
							<Link
								key={post.slug}
								to="/blog/$slug"
								params={{ slug: post.slug }}
								className="block rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
							>
								<div className="flex items-center justify-between">
									<span className="font-medium">{post.title}</span>
									<DateBadge date={post.date} />
								</div>
								{post.themes.length > 0 && (
									<div className="mt-1 flex flex-wrap gap-1">
										{post.themes.map((t) => (
											<TagBadge key={t} tag={t} />
										))}
									</div>
								)}
							</Link>
						))}
					</div>
				</section>
			)}
		</div>
	);
}

function StatCard({ label, value }: { label: string; value: number | string }) {
	return (
		<div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800" aria-label={`${label}: ${value}`}>
			<div className="text-2xl font-bold">{value}</div>
			<div className="text-sm text-zinc-500">{label}</div>
		</div>
	);
}
