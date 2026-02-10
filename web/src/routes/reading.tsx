import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import type { ContentItemsResponse, IntakeDigest, SeedIdea } from "../../shared/schemas.js";
import { ContentItemCard } from "../components/shared/ContentItemCard.js";
import { DateBadge } from "../components/shared/DateBadge.js";
import { SourceFilterPills } from "../components/shared/SourceFilterPills.js";

type Tab = "items" | "digests";

export default function Reading() {
	const queryClient = useQueryClient();
	const [newSeed, setNewSeed] = useState("");
	const [activeTab, setActiveTab] = useState<Tab>("items");
	const [filterSource, setFilterSource] = useState<string | null>(null);

	const { data: digestsData } = useQuery<{ digests: IntakeDigest[] }>({
		queryKey: ["reading"],
		queryFn: async () => {
			const res = await fetch("/api/reading/digests");
			if (!res.ok) throw new Error("Failed to load digests");
			return res.json();
		},
	});

	const { data: seedsData } = useQuery<{ seeds: SeedIdea[] }>({
		queryKey: ["seeds"],
		queryFn: async () => {
			const res = await fetch("/api/seeds");
			if (!res.ok) throw new Error("Failed to load seeds");
			return res.json();
		},
	});

	const digests = digestsData?.digests ?? [];
	const latestDate = digests[0]?.date ?? null;

	const { data: itemsData } = useQuery<ContentItemsResponse>({
		queryKey: ["reading-items", latestDate, filterSource],
		queryFn: async () => {
			const params = new URLSearchParams();
			if (latestDate) params.set("date", latestDate);
			if (filterSource) params.set("source", filterSource);
			const res = await fetch(`/api/reading/items?${params.toString()}`);
			if (!res.ok) throw new Error("Failed to load items");
			return res.json();
		},
		enabled: activeTab === "items" && !!latestDate,
	});

	const addSeed = useMutation({
		mutationFn: async (text: string) => {
			const res = await fetch("/api/seeds", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ text, tags: [] }),
			});
			if (!res.ok) throw new Error("Failed to add seed");
			return res.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["seeds"] });
			setNewSeed("");
		},
	});

	const deleteSeed = useMutation({
		mutationFn: async (id: string) => {
			const res = await fetch(`/api/seeds/${id}`, { method: "DELETE" });
			if (!res.ok) throw new Error("Failed to delete seed");
		},
		onSuccess: () => queryClient.invalidateQueries({ queryKey: ["seeds"] }),
	});

	const seeds = seedsData?.seeds ?? [];
	const items = itemsData?.items ?? [];
	const availableSources = itemsData?.available_sources ?? [];

	return (
		<div className="space-y-8">
			<h2 className="text-2xl font-bold">Reading</h2>

			{/* Seeds section */}
			<section>
				<h3 className="mb-3 text-lg font-semibold">Seed Ideas</h3>
				<form
					className="mb-4 flex gap-2"
					onSubmit={(e) => {
						e.preventDefault();
						if (newSeed.trim()) addSeed.mutate(newSeed.trim());
					}}
				>
					<input
						type="text"
						value={newSeed}
						onChange={(e) => setNewSeed(e.target.value)}
						placeholder="Add a seed idea..."
						className="flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
					/>
					<button
						type="submit"
						disabled={!newSeed.trim() || addSeed.isPending}
						className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
					>
						Add
					</button>
				</form>
				{seeds.length === 0 ? (
					<p className="text-sm text-zinc-500">No seeds yet.</p>
				) : (
					<div className="space-y-2">
						{seeds.map((seed) => (
							<div
								key={seed.id}
								className="flex items-center justify-between rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
							>
								<div>
									<span className={seed.used ? "text-zinc-400 line-through" : ""}>{seed.text}</span>
									{seed.tags.length > 0 && (
										<span className="ml-2 text-xs text-zinc-500">{seed.tags.join(", ")}</span>
									)}
								</div>
								<button
									type="button"
									onClick={() => deleteSeed.mutate(seed.id)}
									className="text-xs text-red-500 hover:text-red-700"
								>
									Delete
								</button>
							</div>
						))}
					</div>
				)}
			</section>

			{/* Tab bar */}
			<div className="border-b border-zinc-200 dark:border-zinc-800">
				<nav className="-mb-px flex gap-4" aria-label="Content tabs">
					<button
						type="button"
						onClick={() => setActiveTab("items")}
						className={`border-b-2 px-1 pb-2 text-sm font-medium transition-colors ${
							activeTab === "items"
								? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
								: "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
						}`}
					>
						Items
					</button>
					<button
						type="button"
						onClick={() => setActiveTab("digests")}
						className={`border-b-2 px-1 pb-2 text-sm font-medium transition-colors ${
							activeTab === "digests"
								? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
								: "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
						}`}
					>
						Digests
					</button>
				</nav>
			</div>

			{/* Items tab */}
			{activeTab === "items" && (
				<section>
					<SourceFilterPills
						sources={availableSources}
						filterSource={filterSource}
						onFilterChange={setFilterSource}
					/>
					{items.length === 0 ? (
						<p className="mt-4 text-sm text-zinc-500">
							No content items yet. Run <code>distill intake</code> to ingest content.
						</p>
					) : (
						<div className="mt-4 space-y-3">
							{items.map((item) => (
								<ContentItemCard key={item.id} item={item} />
							))}
						</div>
					)}
				</section>
			)}

			{/* Digests tab */}
			{activeTab === "digests" && (
				<section>
					{digests.length === 0 ? (
						<p className="text-sm text-zinc-500">
							No intake digests yet. Run <code>distill intake</code> to generate some.
						</p>
					) : (
						<div className="space-y-2">
							{digests.map((d) => (
								<Link
									key={d.filename}
									to="/reading/$date"
									params={{ date: d.date }}
									className="block rounded-lg border border-zinc-200 p-4 transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
								>
									<div className="flex items-center justify-between">
										<DateBadge date={d.date} />
										<span className="text-xs text-zinc-500">
											{d.itemCount} items from {d.sources.length} sources
										</span>
									</div>
								</Link>
							))}
						</div>
					)}
				</section>
			)}
		</div>
	);
}
