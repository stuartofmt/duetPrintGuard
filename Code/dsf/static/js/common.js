// =========================
// Shared setup for the duetPrintGuard pages
// =========================
// Every page loads Vue and Vuetify from static/vendor (the same versions DWC 3.7 uses), then calls
// PG.mount({ setup() { ... } }) with its own state. The page markup lives in the page's template
// (templates/<page>.html) as #page-template. No build step is needed - edit and reload.
//
// Theme: ?theme=dark|light (added by the DWC plugin) picks the starting theme, otherwise the browser's
// light/dark preference is used. When the page is shown inside DWC, DWC also posts its current theme
// colours to the page so it follows DWC's theme, including later changes.

(function () {
	'use strict';

	const { createApp, reactive } = Vue;

	const query = new URLSearchParams(window.location.search);
	const embedded = window.parent !== window;

	// =========================
	// Navigation
	// =========================
	// Keep ?mobile / ?theme when moving between pages
	function pageUrl(path) {
		return path + window.location.search;
	}

	const pages = [
		{ title: 'Detection', path: '/index', icon: 'mdi-eye' },
		{ title: 'Settings', path: '/settings', icon: 'mdi-cctv' },
		{ title: 'Configuration', path: '/config', icon: 'mdi-cog' }
	];

	// =========================
	// API
	// =========================
	async function request(url, options) {
		const response = await fetch(url, options);
		let data = null;
		try {
			data = await response.json();
		} catch {
			// Some endpoints redirect to an HTML page or return nothing
		}
		if (!response.ok) {
			const error = new Error(data?.detail || response.statusText || `HTTP ${response.status}`);
			error.status = response.status;
			error.data = data;
			throw error;
		}
		return data;
	}

	const api = {
		get: (url) => request(url),
		postJson: (url, body) => request(url, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		}),
		// For endpoints that take Form(...) fields
		postForm: (url, fields) => request(url, {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams(fields)
		})
	};

	// =========================
	// Snackbar and confirm dialog
	// =========================
	const snackbar = reactive({ show: false, text: '', color: 'success', timeout: 4000 });

	function notify(text, color = 'success', timeout = 4000) {
		Object.assign(snackbar, { show: true, text, color, timeout });
	}

	const confirmState = reactive({ show: false, title: '', text: '', color: 'primary', resolve: null });

	// Resolves true when the user confirms
	function confirm(text, { title = 'Please confirm', color = 'primary' } = {}) {
		confirmState.resolve?.(false);
		return new Promise((resolve) => {
			Object.assign(confirmState, { show: true, title, text, color, resolve });
		});
	}

	function closeConfirm(result) {
		confirmState.show = false;
		confirmState.resolve?.(result);
		confirmState.resolve = null;
	}

	// =========================
	// Shared components
	// =========================
	// Page layout: navigation tabs, the page content, then the snackbar and confirm dialog
	const PgPage = {
		props: { title: String },
		setup() {
			const current = pages.find((p) => window.location.pathname.startsWith(p.path))?.path ?? '';
			return { pages, current, pageUrl, snackbar, confirmState, closeConfirm };
		},
		template: `
			<v-app>
				<v-main>
					<v-tabs :model-value="current" color="primary" density="compact" show-arrows>
						<v-tab v-for="page in pages" :key="page.path" :value="page.path"
							   :href="pageUrl(page.path)" :prepend-icon="page.icon">{{ page.title }}</v-tab>
					</v-tabs>
					<v-divider></v-divider>
					<v-container fluid class="pa-2 pa-sm-4">
						<slot></slot>
					</v-container>
				</v-main>

				<v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="snackbar.timeout">
					{{ snackbar.text }}
					<template #actions>
						<v-btn variant="text" icon="mdi-close" @click="snackbar.show = false"></v-btn>
					</template>
				</v-snackbar>

				<v-dialog :model-value="confirmState.show" max-width="420" @update:model-value="closeConfirm(false)">
					<v-card>
						<v-card-title>{{ confirmState.title }}</v-card-title>
						<v-card-text>{{ confirmState.text }}</v-card-text>
						<v-card-actions>
							<v-spacer></v-spacer>
							<v-btn @click="closeConfirm(false)">Cancel</v-btn>
							<v-btn :color="confirmState.color" variant="flat" @click="closeConfirm(true)">OK</v-btn>
						</v-card-actions>
					</v-card>
				</v-dialog>
			</v-app>
		`
	};

	// =========================
	// Vuetify (same theme tokens and defaults as DWC 3.7)
	// =========================
	function prefersDark() {
		return window.matchMedia?.('(prefers-color-scheme: dark)').matches === true;
	}

	function createPgVuetify() {
		const requested = query.get('theme');
		return Vuetify.createVuetify({
			theme: {
				defaultTheme: requested === 'dark' || requested === 'light' ? requested : (prefersDark() ? 'dark' : 'light'),
				themes: {
					light: { colors: { 'card-actions': '#1E88E5', 'card-title': '#383838' } },
					dark: { colors: { 'card-actions': '#1E88E5', 'card-title': '#EEEEEE' } }
				}
			},
			defaults: {
				VCardTitle: { class: 'font-weight-bold text-card-title' },
				VCardActions: { VBtn: { color: 'card-actions' } }
			}
		});
	}

	// Follow DWC's theme: { source: 'duetPrintGuard', type: 'theme', dark: bool, colors: {...} }
	function followParentTheme(vuetify) {
		if (embedded) {
			window.addEventListener('message', (event) => {
				const msg = event.data;
				if (event.source !== window.parent || msg?.source !== 'duetPrintGuard' || msg.type !== 'theme') {
					return;
				}
				const name = msg.dark ? 'dark' : 'light';
				const theme = vuetify.theme.themes.value[name];
				if (theme && msg.colors && typeof msg.colors === 'object') {
					theme.colors = { ...theme.colors, ...msg.colors };
				}
				vuetify.theme.change(name);
			});
			// Ask DWC for its theme in case the page loaded after DWC sent it
			window.parent.postMessage({ source: 'duetPrintGuard', type: 'theme-request' }, '*');
		} else if (!query.get('theme')) {
			window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
				vuetify.theme.change(e.matches ? 'dark' : 'light');
			});
		}
	}

	// =========================
	// Mount
	// =========================
	function mount(options) {
		const app = createApp({ ...options, template: '#page-template' });
		const vuetify = createPgVuetify();
		app.use(vuetify);
		app.component('pg-page', PgPage);
		app.mount('#app');
		followParentTheme(vuetify);
		return app;
	}

	window.PG = { api, confirm, embedded, mount, notify, pageUrl, pages };
})();
