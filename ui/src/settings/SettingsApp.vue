<!-- Settings page: the selected camera's snapshot, the defect countdown, the cameras, and adding a camera -->
<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import PgPage from "../components/PgPage.vue";
import CameraCard from "./CameraCard.vue";
import { api } from "../api.js";
import { confirm, notify } from "../notify.js";
import { visibility } from "../visibility.js";
import { mdiCameraOff, mdiClose, mdiPlus, mdiRefresh } from "../icons.js";

const PREVIEW_DELAY = 1000; // ms after the stream URL stops changing before the preview reloads

const countdownActions = [
	{ title: "Ignore", value: "ignore" },
	{ title: "Cancel Print", value: "cancel_print" },
	{ title: "Pause Print", value: "pause_print" },
];

const countdownControls = [
	{ title: "Any", value: "any_camera" },
	{ title: "All", value: "all_cameras" },
];

const isRtsp = (url) => (url || "").trim().toLowerCase().startsWith("rtsp://");
const normalise = (text) => (text || "").trim().toLowerCase();

const cameras = ref([]);
const selected = ref(null);
const snapshot = reactive({ url: "", loading: false, failed: false });
const countdown = reactive({ countdown_action: "ignore", countdown_time: 0, countdown_control: "any_camera" });
const addForm = ref(null);
const add = reactive({
	show: false, saving: false, error: "", nickname: "", source: "", snapshot: "",
	preview: false, previewUrl: "", previewState: "",
});
let previewTimeout = null;

// =========================
// Cameras
// =========================
async function loadCameras() {
	let list = {};
	try {
		list = (await api.get("/config/get-camera-list"))?.list || {};
	} catch (err) {
		console.error("Failed to fetch camera list:", err);
		notify("Failed to load the camera list.", "error");
	}
	cameras.value = Object.entries(list).map(([uuid, camera]) => ({
		uuid,
		nickname: camera.nickname,
		source: camera.source,
		autostart: Boolean(camera.autostart),
		majority_vote_threshold: camera.majority_vote_threshold ?? 1,
		majority_vote_window: camera.majority_vote_window ?? 1,
		sensitivity: camera.sensitivity ?? 0,
	}));

	const stillSelected = selected.value && cameras.value.find((c) => c.uuid === selected.value.uuid);
	if (stillSelected) {
		selected.value = stillSelected;
	} else if (cameras.value.length) {
		select(cameras.value[0]);
	} else {
		selected.value = null;
		snapshot.url = "";
		openAddCamera();
	}
}

function select(camera) {
	// Clicking the selected camera again only reloads it if the last snapshot failed
	if (selected.value?.uuid === camera.uuid && snapshot.url && !snapshot.failed) return;
	selected.value = camera;
	loadSelectedSnapshot();
}

function loadSelectedSnapshot() {
	if (!selected.value) return;
	Object.assign(snapshot, {
		url: `/camera/snapshot/${selected.value.uuid}?t=${Date.now()}`,
		loading: true,
		failed: false,
	});
}

async function removeCamera(camera) {
	if (!await confirm(`Are you sure you want to remove the camera "${camera.nickname}"?`, { color: "error" })) return;
	try {
		const result = await api.postJson("/config/remove-camera", { camera_uuid: camera.uuid });
		if (result?.success === false) throw new Error("the camera was not found");
		notify(`Removed ${camera.nickname}.`);
	} catch (err) {
		notify(`Failed to remove camera: ${err.message}`, "error");
	}
	await loadCameras();
}

// =========================
// Countdown
// =========================
async function loadCountdown() {
	try {
		const settings = (await api.get("/config/get-countdown-settings"))?.settings;
		if (settings) {
			countdown.countdown_action = settings.countdown_action || "ignore";
			countdown.countdown_time = settings.countdown_time || 0;
			countdown.countdown_control = settings.countdown_control || "any_camera";
		}
	} catch (err) {
		console.error("Countdown settings error:", err);
	}
}

async function saveCountdown() {
	try {
		await api.postForm("/config/update-countdown", { ...countdown });
	} catch (err) {
		notify(`Failed to save countdown settings: ${err.message}`, "error");
	}
}

// =========================
// Add camera
// =========================
const rules = {
	required: (v) => Boolean((v || "").trim()) || "Required",
	uniqueNickname: (v) => !cameras.value.some((c) => normalise(c.nickname) === normalise(v))
		|| "A camera with this nickname already exists",
	uniqueSource: (v) => !cameras.value.some((c) => normalise(c.source) === normalise(v))
		|| "A camera with this source already exists",
	// HTTP cameras need a snapshot URL (used for detection and snapshots) - RTSP cameras do not
	snapshot: (v) => isRtsp(add.source) || Boolean((v || "").trim()) || "Required for HTTP cameras",
};

function openAddCamera() {
	Object.assign(add, {
		show: true, saving: false, error: "", nickname: "", source: "", snapshot: "",
		preview: false, previewUrl: "", previewState: "",
	});
}

function closeAddCamera() {
	clearTimeout(previewTimeout);
	add.show = false;
	add.previewUrl = ""; // stops the preview stream
}

function updatePreview() {
	clearTimeout(previewTimeout);
	const source = add.source.trim();
	if (!visibility.visible) {
		add.previewUrl = ""; // Reopened when the page is shown again
		return;
	}
	if (!add.preview || !source) {
		add.previewUrl = "";
		add.previewState = add.preview ? "error" : "";
		return;
	}
	add.previewState = "loading";
	add.previewUrl = `/camera/preview?source=${encodeURIComponent(source)}`;
}

function schedulePreview() {
	clearTimeout(previewTimeout);
	if (add.preview) previewTimeout = setTimeout(updatePreview, PREVIEW_DELAY);
}

async function addCamera() {
	const { valid } = await addForm.value.validate();
	if (!valid) return;

	const data = { nickname: add.nickname.trim(), source: add.source.trim() };
	if (add.snapshot.trim()) data.snapshot = add.snapshot.trim();

	add.saving = true;
	add.error = "";
	try {
		// The server checks that the stream and snapshot URLs work before adding the camera
		await api.postJson("/config/add-camera", data);
		notify(`Added ${data.nickname}.`);
		closeAddCamera();
		await loadCameras();
	} catch (err) {
		console.error("Failed adding camera:", err);
		add.error = err.message || "Failed to add camera";
	} finally {
		add.saving = false;
	}
}

// The preview stream is closed while the page is hidden (see visibility.js)
watch(() => visibility.visible, (visible) => {
	if (!visible) {
		clearTimeout(previewTimeout);
		add.previewUrl = "";
		return;
	}
	if (add.show && add.preview) updatePreview();
	loadSelectedSnapshot();
});

onMounted(() => {
	loadCameras();
	loadCountdown();
});
</script>

<template>
	<PgPage>
		<v-row>
			<!-- Selected camera snapshot and countdown settings -->
			<v-col cols="12" md="7">
				<v-card class="mb-4">
					<v-card-title class="d-flex align-center">
						{{ selected ? selected.nickname : 'Camera Preview' }}
						<v-spacer></v-spacer>
						<v-btn v-if="selected" :icon="mdiRefresh" variant="text" size="small" title="Refresh snapshot"
							   @click="loadSelectedSnapshot"></v-btn>
					</v-card-title>
					<div class="pg-media">
						<img v-if="snapshot.url && !snapshot.failed" :src="snapshot.url" alt="Camera preview"
							 @load="snapshot.loading = false" @error="snapshot.loading = false; snapshot.failed = true" />
						<div v-if="snapshot.loading" class="pg-media-overlay">
							<v-progress-circular indeterminate></v-progress-circular>
							<span>Loading camera feed...</span>
						</div>
						<div v-else-if="snapshot.failed || !selected" class="pg-media-overlay">
							<v-icon :icon="mdiCameraOff" size="large"></v-icon>
							<span>{{ selected ? 'Unable to load camera feed' : 'No camera selected' }}</span>
						</div>
					</div>
				</v-card>

				<v-card>
					<v-card-title>Countdown</v-card-title>
					<v-card-subtitle class="text-wrap">What happens when a defect is detected and nobody intervenes.</v-card-subtitle>
					<v-card-text>
						<v-select v-model="countdown.countdown_action" label="Countdown Action" :items="countdownActions"
								  variant="outlined" density="comfortable" @update:model-value="saveCountdown"></v-select>
						<v-slider v-model="countdown.countdown_time" :min="0" :max="300" :step="5" color="primary"
								  thumb-label @end="saveCountdown">
							<template #prepend>
								<span class="text-no-wrap">Countdown Time</span>
							</template>
							<template #append>
								<span class="text-no-wrap">{{ countdown.countdown_time }} s</span>
							</template>
						</v-slider>
						<v-select v-model="countdown.countdown_control" label="Which Cameras" :items="countdownControls"
								  variant="outlined" density="comfortable" @update:model-value="saveCountdown"></v-select>
					</v-card-text>
				</v-card>
			</v-col>

			<!-- Cameras -->
			<v-col cols="12" md="5">
				<CameraCard v-for="camera in cameras" :key="camera.uuid" :camera="camera"
							:selected="selected?.uuid === camera.uuid"
							@select="select(camera)" @remove="removeCamera(camera)" />

				<v-btn block color="primary" :prepend-icon="mdiPlus" @click="openAddCamera">Add a Camera</v-btn>
			</v-col>
		</v-row>

		<!-- Add camera -->
		<v-dialog v-model="add.show" max-width="560" persistent>
			<v-card>
				<v-card-title class="d-flex align-center">
					Add HTTP or RTSP Camera
					<v-spacer></v-spacer>
					<v-btn :icon="mdiClose" variant="text" size="small" @click="closeAddCamera"></v-btn>
				</v-card-title>
				<v-form ref="addForm" @submit.prevent="addCamera">
					<v-card-text>
						<v-alert v-if="add.error" type="error" variant="tonal" density="compact" class="mb-4"
								 closable :text="add.error" @click:close="add.error = ''"></v-alert>
						<v-text-field v-model="add.nickname" label="Camera Nickname" :rules="[rules.required, rules.uniqueNickname]"
									  variant="outlined" density="comfortable" class="mb-2"></v-text-field>
						<v-text-field v-model="add.source" label="HTTP or RTSP Stream URL" type="url"
									  placeholder="e.g. http://IP_ADDRESS:PORT/stream" persistent-placeholder
									  :rules="[rules.required, rules.uniqueSource]"
									  variant="outlined" density="comfortable" class="mb-2"
									  @update:model-value="schedulePreview"></v-text-field>
						<v-text-field v-model="add.snapshot" label="HTTP Snapshot URL" type="url"
									  placeholder="e.g. http://IP_ADDRESS:PORT/snapshot" persistent-placeholder
									  hint="Not needed for RTSP cameras" persistent-hint :rules="[rules.snapshot]"
									  variant="outlined" density="comfortable" class="mb-2"></v-text-field>
						<v-switch v-model="add.preview" label="Show camera preview" color="primary" density="compact"
								  hide-details @update:model-value="updatePreview"></v-switch>
						<div v-if="add.preview" class="pg-media mt-2">
							<img v-if="add.previewUrl" :src="add.previewUrl" alt="Camera preview"
								 @load="add.previewState = 'ok'" @error="add.previewState = 'error'" />
							<div v-if="add.previewState === 'loading'" class="pg-media-overlay">
								<v-progress-circular indeterminate></v-progress-circular>
								<span>Loading camera preview...</span>
							</div>
							<div v-else-if="add.previewState === 'error'" class="pg-media-overlay">
								<v-icon :icon="mdiCameraOff" size="large" color="error"></v-icon>
								<span>Unable to load camera preview</span>
							</div>
						</div>
					</v-card-text>
					<v-card-actions>
						<v-spacer></v-spacer>
						<v-btn @click="closeAddCamera">Cancel</v-btn>
						<v-btn type="submit" color="primary" variant="flat" :loading="add.saving">Add Camera</v-btn>
					</v-card-actions>
				</v-form>
			</v-card>
		</v-dialog>
	</PgPage>
</template>
