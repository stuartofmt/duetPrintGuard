// Builds the duetPrintGuard web interface into the plugin's static folder.
//
//   npm install      once, to install Vue / Vuetify / Vite
//   npm run build    writes the four pages and assets/ to Code/dsf/static/app
//   npm run dev      live-reload server at http://localhost:5173/static/app/index.html - set PRINTGUARD_URL
//                    to a running duetPrintGuard (default http://localhost:17800) for the API, events and streams
//
// The built files are committed, so the plugin needs no Node.js and no internet access to run.

import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vuetify from "vite-plugin-vuetify";

const printGuardUrl = process.env.PRINTGUARD_URL || "http://localhost:17800";
const page = (name) => fileURLToPath(new URL(`${name}.html`, import.meta.url));

export default defineConfig({
	// duetPrintGuard serves the built pages from /static/app
	base: "/static/app/",
	plugins: [
		vue(),
		// Only the Vuetify components that are used end up in the bundle.
		vuetify({ autoImport: true }),
	],
	build: {
		outDir: fileURLToPath(new URL("../Code/dsf/static/app", import.meta.url)),
		emptyOutDir: true,
		rollupOptions: {
			input: { index: page("index"), settings: page("settings"), config: page("config"), stream: page("stream") },
		},
	},
	server: {
		proxy: {
			// Everything outside /static/app (API, events, snapshots, streams) goes to the running duetPrintGuard.
			"^/(?!static/app/).*": { target: printGuardUrl, changeOrigin: true },
		},
	},
});
