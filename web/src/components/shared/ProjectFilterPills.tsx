interface Props {
	projectNames: string[];
	filterProject: string | null;
	onFilterChange: (project: string | null) => void;
}

export function ProjectFilterPills({ projectNames, filterProject, onFilterChange }: Props) {
	if (projectNames.length === 0) return null;

	return (
		<div className="flex flex-wrap gap-2" role="group" aria-label="Filter by project">
			<button
				type="button"
				aria-pressed={filterProject === null}
				onClick={() => onFilterChange(null)}
				className={`rounded-full px-3 py-1 text-sm transition-colors ${
					filterProject === null
						? "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200"
						: "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
				}`}
			>
				All
			</button>
			{projectNames.map((p) => (
				<button
					key={p}
					type="button"
					aria-pressed={filterProject === p}
					onClick={() => onFilterChange(filterProject === p ? null : p)}
					className={`rounded-full px-3 py-1 text-sm transition-colors ${
						filterProject === p
							? "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200"
							: "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
					}`}
				>
					{p}
				</button>
			))}
		</div>
	);
}
