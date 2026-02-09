import { Link } from "@tanstack/react-router";

const navItems = [
	{ to: "/", label: "Dashboard", icon: "~" },
	{ to: "/projects", label: "Projects", icon: "F" },
	{ to: "/journal", label: "Journal", icon: "J" },
	{ to: "/blog", label: "Blog", icon: "B" },
	{ to: "/reading", label: "Reading", icon: "R" },
	{ to: "/publish", label: "Publish", icon: "P" },
	{ to: "/settings", label: "Settings", icon: "S" },
] as const;

export function Sidebar() {
	return (
		<nav className="flex w-56 flex-col border-r border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
			<div className="p-4">
				<h1 className="text-lg font-bold tracking-tight">Distill</h1>
				<p className="text-xs text-zinc-500">Knowledge cockpit</p>
			</div>
			<ul className="flex-1 space-y-0.5 px-2">
				{navItems.map((item) => (
					<li key={item.to}>
						<Link
							to={item.to}
							className="flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800 [&.active]:bg-indigo-50 [&.active]:text-indigo-700 dark:[&.active]:bg-indigo-950 dark:[&.active]:text-indigo-300"
							activeProps={{ className: "active" }}
						>
							<span className="flex h-6 w-6 items-center justify-center rounded bg-zinc-100 text-xs font-mono dark:bg-zinc-800">
								{item.icon}
							</span>
							{item.label}
						</Link>
					</li>
				))}
			</ul>
			<div className="border-t border-zinc-200 p-4 text-xs text-zinc-400 dark:border-zinc-800">
				distill v0.1.0
			</div>
		</nav>
	);
}
