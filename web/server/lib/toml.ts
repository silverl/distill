/**
 * TOML read/write helpers for .distill.toml configuration.
 */
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { parse, stringify } from "smol-toml";

const CONFIG_FILENAME = ".distill.toml";

export interface DistillTomlConfig {
	output?: { directory?: string };
	sessions?: { sources?: string[]; include_global?: boolean; since_days?: number };
	journal?: {
		style?: string;
		target_word_count?: number;
		model?: string;
		memory_window_days?: number;
	};
	blog?: {
		target_word_count?: number;
		include_diagrams?: boolean;
		model?: string;
		platforms?: string[];
	};
	intake?: {
		feeds_file?: string;
		opml_file?: string;
		use_defaults?: boolean;
		browser_history?: boolean;
		substack_blogs?: string[];
		rss_feeds?: string[];
		target_word_count?: number;
		model?: string;
		publishers?: string[];
	};
	ghost?: {
		url?: string;
		admin_api_key?: string;
		newsletter_slug?: string;
		auto_publish?: boolean;
	};
	postiz?: {
		url?: string;
		api_key?: string;
		default_type?: string;
		schedule_enabled?: boolean;
	};
	reddit?: { client_id?: string; client_secret?: string; username?: string };
	youtube?: { api_key?: string };
	notifications?: {
		slack_webhook?: string;
		ntfy_url?: string;
		ntfy_topic?: string;
		enabled?: boolean;
	};
	projects?: Array<{ name: string; description: string; url?: string; tags?: string[] }>;
}

export async function readConfig(projectDir: string): Promise<DistillTomlConfig> {
	const configPath = join(projectDir, CONFIG_FILENAME);
	try {
		const content = await readFile(configPath, "utf-8");
		return parse(content) as unknown as DistillTomlConfig;
	} catch {
		return {};
	}
}

export async function writeConfig(projectDir: string, config: DistillTomlConfig): Promise<void> {
	const configPath = join(projectDir, CONFIG_FILENAME);
	const content = stringify(config as Record<string, unknown>);
	await writeFile(configPath, content, "utf-8");
}
