// The printer's connection and status (from /printer/get-status), shared by the pages and the printer banner.
// It is polled while the page is shown - see visibility.js - and refreshPrinter() asks again at once.
import { ref, watch } from "vue";
import { api } from "./api.js";
import { visibility } from "./visibility.js";

const POLL_INTERVAL = 5000; // ms - keeps Pause / Resume and the banner in step with the printer

export const printer = ref(null); // {connected, status, address, mode, plugin, error, retrying, ip, port}
// Counts saves of the printer settings from the banner, so a page showing them can load them again
export const printerSettingsSaved = ref(0);

export async function refreshPrinter() {
	try {
		printer.value = await api.get("/printer/get-status");
	} catch (err) {
		console.warn("Error from /printer/get-status", err);
	}
}

let timer = null;
let started = false;

// Called by the page layout: polls while the page is shown
export function startPrinterPolling() {
	if (started) return;
	started = true;
	watch(() => visibility.visible, (visible) => {
		clearInterval(timer);
		timer = null;
		if (visible) {
			refreshPrinter();
			timer = setInterval(refreshPrinter, POLL_INTERVAL);
		}
	}, { immediate: true });
}
