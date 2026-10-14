<!--
Detection page. A camera that is detecting shows its live stream. Otherwise it shows a snapshot taken when the
page was shown (or when detection stopped). While the page is hidden, or a camera's stream is open in a new
tab, the page closes its streams and event connection - see visibility.js.
-->
<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import PgPage from "../components/PgPage.vue";
import { api } from "../api.js";
import { confirm, notify } from "../notify.js";
import { pageUrl, streamPageUrl } from "../pages.js";
import { connectSSE } from "../sse.js";
import { visibility } from "../visibility.js";
import {
	mdiAutorenew, mdiAutorenewOff, mdiBellCheck, mdiBellOff, mdiPause, mdiPlay, mdiStop, mdiTimerSand,
} from "../icons.js";

const DEFAULT_ICON = "/static/images/default_icon.png";
const MAX_CONCURRENT_SNAPSHOTS = 2;
const ACTION_NAMES = { pause_print: "Pause", cancel_print: "Cancel", ignore: "Action" };
const PRINTER_POLL_INTERVAL = 5000; // ms - keeps Pause / Resume in step with the printer

// =========================
// Snapshot queue - at most MAX_CONCURRENT_SNAPSHOTS loading at once
// =========================
let activeSnapshots = 0;
const snapshotQueue = [];

function enqueueSnapshot(task) {
	snapshotQueue.push(task);
	processSnapshotQueue();
}

function processSnapshotQueue() {
	if (activeSnapshots >= MAX_CONCURRENT_SNAPSHOTS || snapshotQueue.length === 0) return;
	const task = snapshotQueue.shift();
	activeSnapshots++;
	task().finally(() => {
		activeSnapshots--;
		processSnapshotQueue();
	});
}

// Load the image off-screen first so the visible one only changes once the new frame is ready
function loadSnapshot(camera) {
	return new Promise((resolve) => {
		const url = `/camera/snapshot/${camera.uuid}?t=${Date.now()}`;
		const img = new Image();
		img.onload = () => {
			camera.snapshot = url;
			resolve();
		};
		img.onerror = () => resolve();
		img.src = url;
	});
}

const cameras = ref([]);
const noCameras = ref(false);
const paused = ref(false);
const countdown = reactive({ active: false, seconds: 0, action: null });
const autostart = reactive({ enabled: false, running: false, waiting: false });
const settingsUrl = pageUrl("/settings");
// Set when a stream is opened in a new tab, until this page is shown or focused again
const suspended = ref(false);
const active = computed(() => visibility.visible && !suspended.value);
let countdownTimer = null;
let closeSSE = null;
let printerTimer = null;

const countdownText = computed(() => ACTION_NAMES[countdown.action] ?? "Action");

const findCamera = (uuid) => cameras.value.find((c) => c.uuid === uuid);
const isDetecting = (camera) => camera.state.live_detection_running === "yes";
// 'paused' - detection stopped because the print was paused, and restarts when it is resumed
const statusChip = (camera) => isDetecting(camera)
	? { text: "Detecting", color: "success" }
	: camera.state.live_detection_running === "paused"
		? { text: "Paused", color: "warning" }
		: { text: "Inactive", color: "error" };
const resultClass = (camera) => !camera.state.last_result
	? "text-medium-emphasis"
	: (camera.state.last_result === "success" ? "text-success" : "text-error");
const lastUpdate = (camera) => camera.state.last_time
	? new Date(camera.state.last_time * 1000).toLocaleTimeString()
	: "-";

// =========================
// Cameras
// =========================
const showStream = (camera) => active.value && isDetecting(camera) && !camera.streamFailed;
const cameraView = (camera) => showStream(camera)
	? `/camera/stream/${camera.uuid}`
	: (camera.snapshot || DEFAULT_ICON);

function refreshSnapshot(camera) {
	enqueueSnapshot(() => loadSnapshot(camera));
}

// A stream that fails falls back to the snapshot until the page is shown again
function onViewError(camera) {
	if (showStream(camera)) {
		camera.streamFailed = true;
		refreshSnapshot(camera);
	}
}

function setState(camera, state) {
	const wasDetecting = isDetecting(camera);
	camera.state = state;
	if (wasDetecting && !isDetecting(camera)) {
		refreshSnapshot(camera); // The stream closes, so show the camera as it is now
	} else if (!wasDetecting && isDetecting(camera)) {
		camera.streamFailed = false;
	}
}

async function refreshState(camera) {
	try {
		const data = await api.postJson("/config/get-camera-state", { camera_uuid: camera.uuid });
		if (data?.state) setState(camera, data.state);
	} catch (err) {
		console.warn(`Error from /config/get-camera-state for camera ${camera.uuid}:`, err);
	}
}

async function toggleDetection(camera) {
	const start = !isDetecting(camera);
	camera.busy = true;
	try {
		const result = await api.postJson(`/detect/live/${start ? "start" : "stop"}`, { camera_uuid: camera.uuid });
		if (result?.success === false) {
			notify(result.message || `Failed to ${start ? "start" : "stop"} detection`, "error");
		}
	} catch (err) {
		notify(`Failed to ${start ? "start" : "stop"} detection: ${err.message}`, "error");
	} finally {
		camera.busy = false;
		refreshState(camera);
	}
}

// Open the stream in a new tab and close this page's connections until it is shown again
function openStream(camera) {
	const tab = window.open(streamPageUrl(camera.nickname), "_blank");
	if (!tab) {
		notify("The browser blocked the new tab - allow pop-ups for this page.", "error");
		return;
	}
	suspended.value = true;
}

// =========================
// Print actions and countdown
// =========================
async function runAction(action) {
	try {
		await api.postJson("/countdown/action", { action });
		return true;
	} catch (err) {
		notify(`Failed to run ${action}: ${err.message}`, "error");
		return false;
	}
}

// The printer can be paused by the countdown, from DWC or from another browser, so Pause / Resume
// follows the printer's status rather than this page's clicks
async function refreshPrinterStatus() {
	try {
		const status = (await api.get("/printer/get-status"))?.status;
		if (status) paused.value = status === "paused" || status === "pausing";
	} catch (err) {
		console.warn("Error from /printer/get-status", err);
	}
}

async function togglePause() {
	if (paused.value) {
		if (await confirm("Are you sure you want to Resume the print?")) await runAction("resume_print");
	} else if (await confirm("Are you sure you want to Pause the print?", { color: "warning" })) {
		await runAction("pause_print");
	}
	refreshPrinterStatus();
}

async function cancelPrint() {
	if (await confirm("Are you sure you want to Cancel the print?", { color: "error" })) {
		await runAction("cancel_print");
		refreshPrinterStatus();
	}
}

function stopCountdown() {
	clearInterval(countdownTimer);
	countdownTimer = null;
	countdown.active = false;
	countdown.seconds = 0;
}

// Started once per alert; a countdown_time of 0 or less stops it
function onCountdown(data) {
	const seconds = typeof data === "number" ? data : (data?.countdown_time || 0);
	if (seconds <= 0) {
		stopCountdown();
		return;
	}
	if (countdownTimer) return;

	const endTime = Date.now() + seconds * 1000;
	countdown.action = typeof data === "object" ? data.countdown_action : null;
	const tick = () => {
		countdown.seconds = Math.max(0, Math.ceil((endTime - Date.now()) / 1000));
		countdown.active = countdown.seconds > 0;
		if (!countdown.active) stopCountdown();
	};
	countdownTimer = setInterval(tick, 1000);
	tick();
}

// =========================
// Autostart and notifications
// =========================
async function toggleAutostart() {
	try {
		if (autostart.running) {
			autostart.waiting = true;
			await api.get("/printer/disableautostart");
		} else {
			await api.get("/printer/enableautostart");
		}
	} catch (err) {
		autostart.waiting = false;
		notify(`Failed to change autostart: ${err.message}`, "error");
	}
}

async function resetNotifications() {
	try {
		await api.get("/printer/resetnotifications");
		notify("Notifications reset.");
	} catch (err) {
		notify(`Failed to reset notifications: ${err.message}`, "error");
	}
}

// =========================
// Connections - open only while the page is active
// =========================
const sseHandlers = {
	countdown_time: onCountdown,
	camera_updated: (data) => {
		const camera = findCamera(data?.camera_uuid);
		if (camera && data.state) setState(camera, data.state);
	},
	autostart_updated: (data) => {
		autostart.enabled = Boolean(data?.state);
	},
	autostart_running: (data) => {
		autostart.running = Boolean(data?.state);
		autostart.waiting = false;
	},
};

function connect() {
	if (closeSSE) return;
	closeSSE = connectSSE(sseHandlers); // Sends the current countdown on connect
	refreshPrinterStatus();
	printerTimer = setInterval(refreshPrinterStatus, PRINTER_POLL_INTERVAL);
	for (const camera of cameras.value) {
		camera.streamFailed = false;
		refreshState(camera);
		refreshSnapshot(camera);
	}
}

function disconnect() {
	closeSSE?.();
	closeSSE = null;
	clearInterval(printerTimer);
	printerTimer = null;
}

watch(() => visibility.visible, (visible) => {
	if (visible) suspended.value = false;
});
const onFocus = () => { suspended.value = false; };

// =========================
// Init
// =========================
onMounted(async () => {
	window.addEventListener("focus", onFocus);

	let list = {};
	try {
		list = (await api.get("/config/get-camera-list"))?.list || {};
	} catch (err) {
		console.warn("Error from /config/get-camera-list", err);
	}

	cameras.value = Object.entries(list).map(([uuid, camera]) => ({
		uuid,
		nickname: camera.nickname,
		state: {},
		snapshot: "",
		streamFailed: false,
		busy: false,
	}));
	autostart.enabled = Object.values(list).some((camera) => camera.autostart);
	noCameras.value = cameras.value.length === 0;

	watch(active, (on) => (on ? connect() : disconnect()), { immediate: true });
});

onBeforeUnmount(() => {
	window.removeEventListener("focus", onFocus);
	disconnect();
	stopCountdown();
});
</script>

<template>
	<PgPage>
		<!-- Print controls and the defect countdown -->
		<v-card class="mb-4">
			<v-card-text class="d-flex flex-wrap align-center ga-2">
				<v-btn :color="paused ? 'success' : 'warning'" :prepend-icon="paused ? mdiPlay : mdiPause"
					   :class="{ 'pg-pulse': countdown.active && countdown.action === 'pause_print' }"
					   @click="togglePause">
					{{ paused ? 'Resume' : 'Pause' }}
				</v-btn>
				<v-btn color="error" :prepend-icon="mdiStop"
					   :class="{ 'pg-pulse': countdown.active && countdown.action === 'cancel_print' }"
					   @click="cancelPrint">
					Cancel
				</v-btn>
				<v-btn v-if="countdown.active" color="secondary" :prepend-icon="mdiBellOff"
					   :class="{ 'pg-pulse': countdown.action !== 'pause_print' && countdown.action !== 'cancel_print' }"
					   @click="runAction('ignore')">
					Ignore
				</v-btn>
				<v-chip v-if="countdown.active" color="error" variant="flat" :prepend-icon="mdiTimerSand" label>
					{{ countdownText }} in {{ countdown.seconds }} sec
				</v-chip>
			</v-card-text>
		</v-card>

		<!-- One row per camera: status card and snapshot -->
		<v-row>
			<template v-for="camera in cameras" :key="camera.uuid">
				<v-col cols="12" sm="5" md="4">
					<v-card class="h-100 d-flex flex-column">
						<v-card-title class="d-flex align-center">
							<span class="text-truncate">{{ camera.nickname }}</span>
							<v-spacer></v-spacer>
							<v-chip :color="statusChip(camera).color" size="small" variant="tonal">
								{{ statusChip(camera).text }}
							</v-chip>
						</v-card-title>
						<v-list density="compact" class="bg-transparent">
							<v-list-item title="Detection">
								<template #append>
									<span :class="resultClass(camera)">{{ camera.state.last_result ?? 'Unknown' }}</span>
								</template>
							</v-list-item>
							<v-list-item title="Last Update">
								<template #append>
									<span>{{ lastUpdate(camera) }}</span>
								</template>
							</v-list-item>
						</v-list>
						<v-spacer></v-spacer>
						<v-card-actions>
							<v-btn block variant="flat" :color="isDetecting(camera) ? 'error' : 'success'"
								   :prepend-icon="isDetecting(camera) ? mdiStop : mdiPlay"
								   :loading="camera.busy" @click="toggleDetection(camera)">
								{{ isDetecting(camera) ? 'Stop Detection' : 'Start Detection' }}
							</v-btn>
						</v-card-actions>
					</v-card>
				</v-col>
				<v-col cols="12" sm="7" md="8">
					<div class="pg-media pg-media--compact pg-clickable" title="Open the live stream in a new tab" @click="openStream(camera)">
						<img :src="cameraView(camera)" :alt="camera.nickname" @error="onViewError(camera)" />
					</div>
				</v-col>
			</template>
		</v-row>

		<!-- Bottom controls -->
		<div class="d-flex flex-wrap ga-2 mt-4">
			<v-btn :prepend-icon="mdiBellCheck" @click="resetNotifications">Reset Notification</v-btn>
			<v-btn v-if="autostart.enabled" :color="autostart.waiting ? 'warning' : (autostart.running ? 'error' : 'success')"
				   :loading="autostart.waiting" :prepend-icon="autostart.running ? mdiAutorenewOff : mdiAutorenew"
				   @click="toggleAutostart">
				{{ autostart.running ? 'Disable Autostart' : 'Enable Autostart' }}
			</v-btn>
		</div>

		<!-- No cameras configured -->
		<v-dialog v-model="noCameras" max-width="420">
			<v-card>
				<v-card-title>No Cameras Configured</v-card-title>
				<v-card-text>Add a camera on the Settings page.</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn @click="noCameras = false">Close</v-btn>
					<v-btn color="primary" variant="flat" :href="settingsUrl">Settings</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	</PgPage>
</template>
