import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { DashboardResponse } from "../../shared/schemas.js";
import RunPipelineButton from "../components/shared/RunPipelineButton.js";

export default function Dashboard() {
	const { data, isLoading, error } = useQuery<DashboardResponse>({
		queryKey: ["dashboard"],
		queryFn: async () => {
			const res = await fetch("/api/dashboard");
			if (!res.ok) throw new Error("Failed to load dashboard");
			return res.json();
		},
	});

	if (isLoading) return <div className="animate-pulse text-zinc-400">Loading dashboard...</div>;
	if (error) return <div className="text-red-500">Error: {error.message}</div>;
	if (!data) return null;

	return (
		<div className="space-y-6">
			<h2 className="text-2xl font-bold">Dashboard</h2>

			{/* Quick stats */}
			<div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
				<StatCard label="Journal entries" value={data.journalCount} to="/journal" />
				<StatCard label="Blog posts" value={data.blogCount} to="/blog" />
				<StatCard label="Projects" value={data.projectCount} to="/projects" />
				<StatCard label="Intake digests" value={data.intakeCount} to="/reading" />
				<StatCard label="Ready to publish" value={data.pendingPublish} to="/publish" />
			</div>

			{/* Active projects */}
			{data.activeProjects.length > 0 && (
				<section>
					<h3 className="mb-3 text-lg font-semibold">Active Projects</h3>
					<div className="flex flex-wrap gap-3">
						{data.activeProjects.map((p) => (
							<Link
								key={p.name}
								to="/projects/$name"
								params={{ name: p.name }}
								className="rounded-lg border border-zinc-200 px-4 py-3 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
							>
								<span className="font-medium">{p.name}</span>
								<div className="mt-1 text-xs text-zinc-500">
									{p.journalCount} entries, last {p.lastSeen}
								</div>
							</Link>
						))}
					</div>
				</section>
			)}

			{/* Recent journals */}
			{data.recentJournals.length > 0 && (
				<section>
					<h3 className="mb-3 text-lg font-semibold">Recent Journal Entries</h3>
					<div className="space-y-2">
						{data.recentJournals.map((j) => (
							<Link
								key={j.date}
								to="/journal/$date"
								params={{ date: j.date }}
								className="block rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
							>
								<div className="flex items-center justify-between">
									<span className="font-medium">{j.date}</span>
									<span className="text-xs text-zinc-500">
										{j.sessionsCount} sessions, {j.durationMinutes}m
									</span>
								</div>
								{j.projects.length > 0 && (
									<div className="mt-1 flex gap-1">
										{j.projects.map((p) => (
											<span
												key={p}
												className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs dark:bg-zinc-800"
											>
												{p}
											</span>
										))}
									</div>
								)}
							</Link>
						))}
					</div>
				</section>
			)}

			{/* Active threads */}
			{data.activeThreads.length > 0 && (
				<section>
					<h3 className="mb-3 text-lg font-semibold">Active Threads</h3>
					<div className="space-y-2">
						{data.activeThreads.map((t) => (
							<div
								key={t.name}
								className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
							>
								<div className="flex items-center justify-between">
									<span className="font-medium">{t.name}</span>
									<span className="text-xs text-zinc-500">
										{t.mention_count}x since {t.first_seen}
									</span>
								</div>
								<p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t.summary}</p>
							</div>
						))}
					</div>
				</section>
			)}

			{/* Run pipeline */}
			<section>
				<h3 className="mb-3 text-lg font-semibold">Pipeline</h3>
				<RunPipelineButton />
			</section>

			{/* Quick actions */}
			<div className="flex gap-3">
				{data.seedCount > 0 && (
					<Link
						to="/reading"
						className="rounded-lg bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200"
					>
						{data.seedCount} pending seeds
					</Link>
				)}
				{data.activeNoteCount > 0 && (
					<Link
						to="/settings"
						className="rounded-lg bg-purple-50 px-4 py-2 text-sm text-purple-800 dark:bg-purple-950 dark:text-purple-200"
					>
						{data.activeNoteCount} active editorial notes
					</Link>
				)}
			</div>
		</div>
	);
}

function StatCard({ label, value, to }: { label: string; value: number; to: string }) {
	return (
		<Link
			to={to}
			className="rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
		>
			<div className="text-2xl font-bold">{value}</div>
			<div className="text-sm text-zinc-500">{label}</div>
		</Link>
	);
}
