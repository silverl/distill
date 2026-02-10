import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";
import type { ContentItemsResponse, IntakeDetail } from "../../shared/schemas.js";
import { ContentItemCard } from "../components/shared/ContentItemCard.js";
import { DateBadge } from "../components/shared/DateBadge.js";
import { EditToggle } from "../components/shared/EditToggle.js";
import { MarkdownEditor } from "../components/shared/MarkdownEditor.js";
import { MarkdownRenderer } from "../components/shared/MarkdownRenderer.js";
import { SourceFilterPills } from "../components/shared/SourceFilterPills.js";
import { useMarkdownSave } from "../lib/useMarkdownSave.js";

export default function ReadingDetailPage() {
	const { date } = useParams({ from: "/reading/$date" });
	const [isEditing, setIsEditing] = useState(false);
	const [filterSource, setFilterSource] = useState<string | null>(null);

	const { data, isLoading, error } = useQuery<IntakeDetail>({
		queryKey: ["reading", date],
		queryFn: async () => {
			const res = await fetch(`/api/reading/digests/${date}`);
			if (!res.ok) throw new Error("Digest not found");
			return res.json();
		},
	});

	const { data: itemsData } = useQuery<ContentItemsResponse>({
		queryKey: ["reading-items", date, filterSource],
		queryFn: async () => {
			const params = new URLSearchParams({ date });
			if (filterSource) params.set("source", filterSource);
			const res = await fetch(`/api/reading/items?${params.toString()}`);
			if (!res.ok) throw new Error("Failed to load items");
			return res.json();
		},
	});

	const { editedContent, setEditedContent, isDirty, save, isSaving, saveSuccess } = useMarkdownSave(
		{
			endpoint: `/api/reading/digests/${date}`,
			queryKey: ["reading", date],
			originalContent: data?.content ?? "",
		},
	);

	if (isLoading) return <div className="animate-pulse text-zinc-400">Loading...</div>;
	if (error) return <div className="text-red-500">Error: {error.message}</div>;
	if (!data) return null;

	const items = itemsData?.items ?? [];
	const availableSources = itemsData?.available_sources ?? [];

	return (
		<div className="space-y-4">
			<div className="flex items-center justify-between">
				<Link
					to="/reading"
					className="text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
				>
					&larr; Reading
				</Link>
				<EditToggle
					isEditing={isEditing}
					onToggle={() => setIsEditing(!isEditing)}
					onSave={save}
					isSaving={isSaving}
					isDirty={isDirty}
					saveSuccess={saveSuccess}
				/>
			</div>

			<div className="flex items-center gap-3">
				<DateBadge date={data.meta.date} />
				<span className="text-sm text-zinc-500">
					{data.meta.itemCount} items from {data.meta.sources.length} sources
				</span>
			</div>

			{isEditing ? (
				<MarkdownEditor value={editedContent} onChange={setEditedContent} onSave={save} />
			) : (
				<MarkdownRenderer content={data.content} />
			)}

			{/* Content Items section */}
			<div className="border-t border-zinc-200 pt-6 dark:border-zinc-800">
				<h3 className="mb-3 text-lg font-semibold">Content Items ({items.length})</h3>
				<SourceFilterPills
					sources={availableSources}
					filterSource={filterSource}
					onFilterChange={setFilterSource}
				/>
				{items.length === 0 ? (
					<p className="mt-4 text-sm text-zinc-500">No content items for this date.</p>
				) : (
					<div className="mt-4 space-y-3">
						{items.map((item) => (
							<ContentItemCard key={item.id} item={item} />
						))}
					</div>
				)}
			</div>
		</div>
	);
}
