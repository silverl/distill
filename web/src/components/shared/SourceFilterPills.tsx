const SOURCE_LABELS: Record<string, string> = {
	browser: "Browser",
	rss: "RSS",
	substack: "Substack",
	gmail: "Gmail",
	linkedin: "LinkedIn",
	reddit: "Reddit",
	youtube: "YouTube",
	twitter: "Twitter",
	session: "Session",
	seeds: "Seeds",
	manual: "Manual",
};

const SOURCE_COLORS: Record<string, string> = {
	browser: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
	rss: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200",
	substack: "bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-200",
	gmail: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
	linkedin: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
	reddit: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200",
	youtube: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
	twitter: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
};

const INACTIVE =
	"bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700";

interface Props {
	sources: string[];
	filterSource: string | null;
	onFilterChange: (source: string | null) => void;
}

export function SourceFilterPills({ sources, filterSource, onFilterChange }: Props) {
	if (sources.length === 0) return null;

	return (
		<div className="flex flex-wrap gap-2" role="group" aria-label="Filter by source">
			<button
				type="button"
				aria-pressed={filterSource === null}
				onClick={() => onFilterChange(null)}
				className={`rounded-full px-3 py-1 text-sm transition-colors ${
					filterSource === null
						? "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200"
						: INACTIVE
				}`}
			>
				All
			</button>
			{sources.map((s) => (
				<button
					key={s}
					type="button"
					aria-pressed={filterSource === s}
					onClick={() => onFilterChange(filterSource === s ? null : s)}
					className={`rounded-full px-3 py-1 text-sm transition-colors ${
						filterSource === s
							? (SOURCE_COLORS[s] ??
								"bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200")
							: INACTIVE
					}`}
				>
					{SOURCE_LABELS[s] ?? s}
				</button>
			))}
		</div>
	);
}
