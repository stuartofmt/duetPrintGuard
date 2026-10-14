// Navigation between the pages, keeping ?mobile / ?theme (added by the DWC plugin) in the address.
import { mdiCctv, mdiCog, mdiEye } from "./icons.js";

export const query = new URLSearchParams(window.location.search);
export const embedded = window.parent !== window;

export const pages = [
	{ title: "Detection", path: "/index", icon: mdiEye },
	{ title: "Settings", path: "/settings", icon: mdiCctv },
	{ title: "Configuration", path: "/config", icon: mdiCog },
];

// The Vite dev server serves the pages as /static/app/<page>.html; the plugin serves them as /<page>
const DEV_PAGES = { "/index": "index", "/settings": "settings", "/config": "config" };

export function pageUrl(path) {
	if (import.meta.env.DEV && DEV_PAGES[path]) {
		return `${import.meta.env.BASE_URL}${DEV_PAGES[path]}.html${window.location.search}`;
	}
	return path + window.location.search;
}

export function streamPageUrl(nickname) {
	if (import.meta.env.DEV) {
		const params = new URLSearchParams(window.location.search);
		params.set("nickname", nickname);
		return `${import.meta.env.BASE_URL}stream.html?${params}`;
	}
	return pageUrl(`/stream/${encodeURIComponent(nickname)}`);
}

// The page being shown - the plugin's path (e.g. /settings) or, under the dev server, the .html name
export function currentPage() {
	const path = window.location.pathname;
	return pages.find((p) => path.startsWith(p.path) || path.endsWith(`/${DEV_PAGES[p.path]}.html`))?.path ?? "";
}
