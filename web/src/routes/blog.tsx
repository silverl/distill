import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import type { BlogPost } from "../../shared/schemas.js";
import { DateBadge } from "../components/shared/DateBadge.js";
import { ProjectFilterPills } from "../components/shared/ProjectFilterPills.js";
import { TagBadge } from "../components/shared/TagBadge.js";

export default function BlogList() {
	const [filterProject, setFilterProject] = useState<string | null>(null);
	const { data, isLoading } = useQuery<{ posts: BlogPost[] }>({
		queryKey: ["blog"],
		queryFn: async () => {
			const res = await fetch("/api/blog/posts");
			if (!res.ok) throw new Error("Failed to load blog posts");
			return res.json();
		},
	});

	if (isLoading) return <div className="animate-pulse text-zinc-400">Loading blog posts...</div>;

	const allPosts = data?.posts ?? [];

	// Extract unique project names
	const projectNames = [...new Set(allPosts.flatMap((p) => p.projects))].sort();

	const posts = filterProject
		? allPosts.filter((p) => p.projects.includes(filterProject))
		: allPosts;

	return (
		<div className="space-y-6">
			<h2 className="text-2xl font-bold">Blog</h2>

			<ProjectFilterPills
				projectNames={projectNames}
				filterProject={filterProject}
				onFilterChange={setFilterProject}
			/>

			{posts.length === 0 ? (
				<p className="text-zinc-500">
					{filterProject
						? `No blog posts for project "${filterProject}".`
						: "No blog posts yet. Run `distill blog` to generate some."}
				</p>
			) : (
				<div className="space-y-2">
					{posts.map((post) => (
						<Link
							key={post.slug}
							to="/blog/$slug"
							params={{ slug: post.slug }}
							className="block rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
						>
							<div className="flex items-center justify-between">
								<div className="flex items-center gap-2">
									<span className="font-medium">{post.title}</span>
									<span
										className={`rounded-full px-2 py-0.5 text-xs font-medium ${
											post.postType === "weekly"
												? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
												: "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
										}`}
									>
										{post.postType}
									</span>
								</div>
								<DateBadge date={post.date} />
							</div>
							<div className="mt-2 flex flex-wrap gap-1">
								{post.themes.map((t) => (
									<TagBadge key={t} tag={t} />
								))}
							</div>
							{post.platformsPublished.length > 0 && (
								<div className="mt-2 flex gap-1">
									{post.platformsPublished.map((p) => (
										<span
											key={p}
											className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-800 dark:bg-green-900 dark:text-green-200"
										>
											{p}
										</span>
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
