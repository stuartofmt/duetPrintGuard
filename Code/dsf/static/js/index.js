// =========================
// Detection page
// =========================
// A camera that is detecting shows its live stream. Otherwise it shows a snapshot taken when the page
// was shown (or when detection stopped). While the page is hidden, or a camera's stream is open in a
// new tab, the page closes its streams and event connection - see PG.visibility in common.js.
const { computed, onBeforeUnmount, onMounted, reactive, ref, watch } = Vue;

const DEFAULT_ICON = '/static/images/default_icon.png';
const MAX_CONCURRENT_SNAPSHOTS = 2;

const ACTION_NAMES = { pause_print: 'Pause', cancel_print: 'Cancel', ignore: 'Action' };

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

PG.mount({
	setup() {
		const cameras = ref([]);
		const noCameras = ref(false);
		const paused = ref(false);
		const countdown = reactive({ active: false, seconds: 0, action: null });
		const autostart = reactive({ enabled: false, running: false, waiting: false });
		const settingsUrl = PG.pageUrl('/settings');
		// Set when a stream is opened in a new tab, until this page is shown or focused again
		const suspended = ref(false);
		const active = computed(() => PG.visibility.visible && !suspended.value);
		let countdownTimer = null;
		let closeSSE = null;

		const countdownText = computed(() => ACTION_NAMES[countdown.action] ?? 'Action');

		const findCamera = (uuid) => cameras.value.find((c) => c.uuid === uuid);
		const isDetecting = (camera) => camera.state.live_detection_running === 'yes';
		const resultClass = (camera) => !camera.state.last_result
			? 'text-medium-emphasis'
			: (camera.state.last_result === 'success' ? 'text-success' : 'text-error');
		const lastUpdate = (camera) => camera.state.last_time
			? new Date(camera.state.last_time * 1000).toLocaleTimeString()
			: '-';

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
				const data = await PG.api.postJson('/config/get-camera-state', { camera_uuid: camera.uuid });
				if (data?.state) setState(camera, data.state);
			} catch (err) {
				console.warn(`Error from /config/get-camera-state for camera ${camera.uuid}:`, err);
			}
		}

		async function toggleDetection(camera) {
			const start = !isDetecting(camera);
			camera.busy = true;
			try {
				const result = await PG.api.postJson(`/detect/live/${start ? 'start' : 'stop'}`, { camera_uuid: camera.uuid });
				if (result?.success === false) {
					PG.notify(result.message || `Failed to ${start ? 'start' : 'stop'} detection`, 'error');
				}
			} catch (err) {
				PG.notify(`Failed to ${start ? 'start' : 'stop'} detection: ${err.message}`, 'error');
			} finally {
				camera.busy = false;
				refreshState(camera);
			}
		}

		// Open the stream in a new tab and close this page's connections until it is shown again
		function openStream(camera) {
			const tab = window.open(PG.pageUrl(`/stream/${encodeURIComponent(camera.nickname)}`), '_blank');
			if (!tab) {
				PG.notify('The browser blocked the new tab - allow pop-ups for this page.', 'error');
				return;
			}
			suspended.value = true;
		}

		// =========================
		// Print actions and countdown
		// =========================
		async function runAction(action) {
			try {
				await PG.api.postJson('/countdown/action', { action });
				return true;
			} catch (err) {
				PG.notify(`Failed to run ${action}: ${err.message}`, 'error');
				return false;
			}
		}

		async function togglePause() {
			if (paused.value) {
				if (await PG.confirm('Are you sure you want to Resume the print?') && await runAction('resume_print')) {
					paused.value = false;
				}
			} else if (await PG.confirm('Are you sure you want to Pause the print?', { color: 'warning' }) && await runAction('pause_print')) {
				paused.value = true;
			}
		}

		async function cancelPrint() {
			if (await PG.confirm('Are you sure you want to Cancel the print?', { color: 'error' })) {
				runAction('cancel_print');
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
			const seconds = typeof data === 'number' ? data : (data?.countdown_time || 0);
			if (seconds <= 0) {
				stopCountdown();
				return;
			}
			if (countdownTimer) {
				return;
			}

			const endTime = Date.now() + seconds * 1000;
			countdown.action = typeof data === 'object' ? data.countdown_action : null;
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
					await PG.api.get('/printer/disableautostart');
				} else {
					await PG.api.get('/printer/enableautostart');
				}
			} catch (err) {
				autostart.waiting = false;
				PG.notify(`Failed to change autostart: ${err.message}`, 'error');
			}
		}

		async function resetNotifications() {
			try {
				await PG.api.get('/printer/resetnotifications');
				PG.notify('Notifications reset.');
			} catch (err) {
				PG.notify(`Failed to reset notifications: ${err.message}`, 'error');
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
			}
		};

		function connect() {
			if (closeSSE) return;
			closeSSE = PG.connectSSE(sseHandlers); // Sends the current countdown on connect
			for (const camera of cameras.value) {
				camera.streamFailed = false;
				refreshState(camera);
				refreshSnapshot(camera);
			}
		}

		function disconnect() {
			closeSSE?.();
			closeSSE = null;
		}

		watch(() => PG.visibility.visible, (visible) => {
			if (visible) suspended.value = false;
		});
		const onFocus = () => { suspended.value = false; };

		// =========================
		// Init
		// =========================
		onMounted(async () => {
			window.addEventListener('focus', onFocus);

			let list = {};
			try {
				list = (await PG.api.get('/config/get-camera-list'))?.list || {};
			} catch (err) {
				console.warn('Error from /config/get-camera-list', err);
			}

			cameras.value = Object.entries(list).map(([uuid, camera]) => ({
				uuid,
				nickname: camera.nickname,
				state: {},
				snapshot: '',
				streamFailed: false,
				busy: false
			}));
			autostart.enabled = Object.values(list).some((camera) => camera.autostart);
			noCameras.value = cameras.value.length === 0;

			watch(active, (on) => (on ? connect() : disconnect()), { immediate: true });
		});

		onBeforeUnmount(() => {
			window.removeEventListener('focus', onFocus);
			disconnect();
			stopCountdown();
		});

		return {
			cameras, noCameras, paused, countdown, countdownText, autostart, settingsUrl,
			isDetecting, resultClass, lastUpdate, cameraView, onViewError, toggleDetection, openStream,
			runAction, togglePause, cancelPrint, toggleAutostart, resetNotifications
		};
	}
});
