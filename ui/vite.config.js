// Builds the duetPrintGuard web interface into the plugin's static folder.
//
//   npm install      once, to install Vue / Vuetify / Vite
//   npm run build    writes the five pages and assets/ to Code/dsf/static/app
//   npm run dev      live-reload server at http://localhost:5173/static/app/index.html - set PRINTGUARD_URL
//                    to a running duetPrintGuard (default http://localhost:17800) for the API, events and streams
//
// The built files are committed, so the plugin needs no Node.js and no internet access to run.

import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vuetify from "vite-plugin-vuetify";

const printGuardUrl = process.env.PRINTGUARD_URL || "http://localhost:17800";
const page = (name) => fileURLToPath(new URL(`${name}.html`, import.meta.url));
const outDir = fileURLToPath(new URL("../Code/dsf/static/app", import.meta.url));

// duetPrintGuard sends the alerts itself (see Code/dsf/alert_text.py), so each language's "alerts" texts are also
// written to locales/<code>.json in the built folder
const alertLocales = {
	name: "alert-locales",
	apply: "build",
	closeBundle() {
		const source = fileURLToPath(new URL("src/locales/", import.meta.url));
		mkdirSync(`${outDir}/locales`, { recursive: true });
		for (const file of readdirSync(source).filter((f) => f.endsWith(".json"))) {
			const { alerts } = JSON.parse(readFileSync(source + file, "utf-8"));
			writeFileSync(`${outDir}/locales/${file}`, `${JSON.stringify({ alerts }, null, "\t")}\n`);
		}
	},
};

export default defineConfig({
	// duetPrintGuard serves the built pages from /static/app
	base: "/static/app/",
	plugins: [
		vue(),
		// Only the Vuetify components that are used end up in the bundle.
		vuetify({ autoImport: true }),
		alertLocales,
	],
	build: {
		outDir,
		emptyOutDir: true,
		rollupOptions: {
			input: { index: page("index"), settings: page("settings"), config: page("config"), log: page("log"), stream: page("stream") },
		},
	},
	server: {
		proxy: {
			// Everything outside /static/app (API, events, snapshots, streams) goes to the running duetPrintGuard.
			"^/(?!static/app/).*": { target: printGuardUrl, changeOrigin: true },
		},
	},
});
