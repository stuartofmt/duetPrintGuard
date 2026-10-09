/**
 * Locate and read the plugin's plugin.json, so the release scripts need no per-plugin changes.
 *
 * Search order (the same as the release workflow and scripts/release.sh):
 *   1. MANIFEST, if set (path relative to the repository root; the release workflow sets it)
 *   2. plugin.json at the repository root
 *   3. the shallowest plugin.json in a subfolder (alphabetical within a depth), skipping .git,
 *      node_modules and venv
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

export const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

const SKIP = new Set([".git", "node_modules", "venv"]);

function findManifests(directory, depth = 0, found = []) {
	for (const entry of readdirSync(directory, { withFileTypes: true })) {
		const full = join(directory, entry.name);
		if (entry.isDirectory() && !SKIP.has(entry.name)) findManifests(full, depth + 1, found);
		else if (entry.isFile() && entry.name === "plugin.json") found.push({ path: full, depth });
	}
	return found;
}

/** Path of plugin.json relative to the repository root, e.g. "plugin.json" or "Code/plugin.json". */
export function manifestPath() {
	if (process.env.MANIFEST) return process.env.MANIFEST;
	if (existsSync(join(repoRoot, "plugin.json"))) return "plugin.json";
	const found = findManifests(repoRoot)
		.sort((a, b) => a.depth - b.depth || a.path.localeCompare(b.path));
	if (found.length === 0) throw new Error(`No plugin.json found in ${repoRoot}`);
	return relative(repoRoot, found[0].path);
}

/** The parsed plugin.json. */
export function readManifest() {
	return JSON.parse(readFileSync(join(repoRoot, manifestPath()), "utf8"));
}

/**
 * This branch's release channel, from scripts/release-channel.txt (default "latest"):
 *   latest      - the main line. Tags are v<version> and its Releases are marked Latest.
 *   maintenance - a line built for an older DWC. Tags are v<version>-dwc<dwcVersion>, so they never
 *                 clash with another branch's tags, and its Releases are never marked Latest.
 */
export function releaseChannel() {
	const file = join(repoRoot, "scripts", "release-channel.txt");
	const channel = existsSync(file)
		? readFileSync(file, "utf8").split("\n").map((l) => l.replace(/#.*/, "").trim()).find(Boolean)
		: undefined;
	if (channel && !["latest", "maintenance"].includes(channel)) {
		throw new Error(`scripts/release-channel.txt must say "latest" or "maintenance", not "${channel}".`);
	}
	return channel || "latest";
}

/** The suffix after v<version> in this branch's release tags: "" or "-dwc<dwcVersion>". */
export function tagSuffix(manifest = readManifest()) {
	return releaseChannel() === "maintenance" ? `-dwc${manifest.dwcVersion}` : "";
}
