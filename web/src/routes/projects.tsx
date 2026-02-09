import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { ProjectSummary } from "../../shared/schemas.js";
import { TagBadge } from "../components/shared/TagBadge.js";

export default function ProjectList() {
	const { data, isLoading } = useQuery<{ projects: ProjectSummary[] }>({
		queryKey: ["projects"],
		queryFn: async () => {
			const res = await fetch("/api/projects");
			if (!res.ok) throw new Error("Failed to load projects");
			return res.json();
		},
	});

	if (isLoading) return <div className="animate-pulse text-zinc-400">Loading projects...</div>;

	const projects = data?.projects ?? [];

	return (
		<div className="space-y-6">
			<h2 className="text-2xl font-bold">Projects</h2>
			{projects.length === 0 ? (
				<p className="text-zinc-500">
					No projects found. Add <code>[[projects]]</code> to your <code>.distill.toml</code> or run
					sessions with project context.
				</p>
			) : (
				<div className="grid gap-4 sm:grid-cols-2">
					{projects.map((project) => (
						<Link
							key={project.name}
							to="/projects/$name"
							params={{ name: project.name }}
							className="block rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
						>
							<div className="flex items-center justify-between">
								<span className="text-lg font-semibold">{project.name}</span>
								{project.lastSeen && (
									<span className="text-xs text-zinc-500">Last active: {project.lastSeen}</span>
								)}
							</div>
							{project.description && (
								<p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
									{project.description}
								</p>
							)}
							<div className="mt-3 flex items-center gap-4 text-xs text-zinc-500">
								<span>{project.journalCount} journals</span>
								<span>{project.blogCount} blogs</span>
								<span>{project.totalSessions} sessions</span>
								{project.totalDurationMinutes > 0 && (
									<span>{Math.round(project.totalDurationMinutes / 60)}h total</span>
								)}
							</div>
							{project.tags.length > 0 && (
								<div className="mt-2 flex flex-wrap gap-1">
									{project.tags.map((t) => (
										<TagBadge key={t} tag={t} />
									))}
								</div>
							)}
						</Link>
					))}
				</div>
			)}
		</div>
	);
}
