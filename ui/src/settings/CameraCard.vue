<!--
One camera on the Settings page: auto-start, detection sensitivity and majority vote. Changes are saved
straight away. A click anywhere on the card (including its controls) selects the camera; no ripple, so
dragging a slider doesn't flash the card.
-->
<script setup>
import { api } from "../api.js";
import { notify } from "../notify.js";
import { mdiDelete } from "../icons.js";

const SENSITIVITY_STEPS = 10; // Slider positions -10..10, 0 = normal (see utils/detector.py sensitivity_factor)

const props = defineProps({
	camera: { type: Object, required: true },   // reactive - the card edits its fields
	selected: { type: Boolean, default: false },
});
defineEmits(["select", "remove"]);

async function saveAutostart() {
	const camera = props.camera;
	try {
		await api.postJson("/settings/update_autostart", { camera_uuid: camera.uuid, autostart: camera.autostart });
	} catch (err) {
		camera.autostart = !camera.autostart;
		notify(`Failed to update autostart: ${err.message}`, "error");
	}
}

// The window must be at least the threshold, so moving one slider past the other drags it along
function keepWindowAboveThreshold(moved) {
	const camera = props.camera;
	if (camera.majority_vote_window >= camera.majority_vote_threshold) return;
	if (moved === "threshold") {
		camera.majority_vote_window = camera.majority_vote_threshold;
	} else {
		camera.majority_vote_threshold = camera.majority_vote_window;
	}
}

async function saveCameraSettings() {
	const camera = props.camera;
	try {
		await api.postForm("/settings/save-settings", {
			camera_uuid: camera.uuid,
			majority_vote_threshold: camera.majority_vote_threshold,
			majority_vote_window: camera.majority_vote_window,
			sensitivity: camera.sensitivity,
		});
	} catch (err) {
		notify(`Failed to save camera settings: ${err.message}`, "error");
	}
}

const sensitivityText = (value) => value === 0 ? "Normal"
	: value < 0 ? `Less (${value})` : `More (+${value})`;

function resetSensitivity() {
	props.camera.sensitivity = 0;
	saveCameraSettings();
}
</script>

<template>
	<v-card class="mb-4 pg-clickable" :ripple="false" :class="{ 'pg-selected': selected }" @click="$emit('select')">
		<v-card-title class="d-flex align-center">
			<span class="text-truncate">{{ camera.nickname }}</span>
			<v-spacer></v-spacer>
			<v-btn :icon="mdiDelete" variant="text" size="small" color="error" title="Remove camera"
				   @click.stop="$emit('remove')"></v-btn>
		</v-card-title>
		<v-card-subtitle class="text-wrap text-break">{{ camera.source }}</v-card-subtitle>
		<v-card-text>
			<v-switch v-model="camera.autostart" label="Auto-start" color="primary" density="compact"
					  hide-details @update:model-value="saveAutostart"></v-switch>
			<!-- Sensitivity: the middle is normal; log scale, so the ends are effectively fail nothing / fail everything -->
			<div class="d-flex align-center mt-3">
				<span>Detection Sensitivity</span>
				<v-spacer></v-spacer>
				<v-btn v-if="camera.sensitivity !== 0" variant="text" size="x-small" class="mr-1"
					   @click.stop="resetSensitivity">Reset</v-btn>
				<span class="text-no-wrap">{{ sensitivityText(camera.sensitivity) }}</span>
			</div>
			<v-slider v-model="camera.sensitivity" :min="-SENSITIVITY_STEPS" :max="SENSITIVITY_STEPS" :step="1"
					  :ticks="{ 0: '' }" show-ticks="always" color="primary" track-fill-color="transparent" hide-details
					  @end="saveCameraSettings"></v-slider>
			<div class="d-flex text-body-small text-medium-emphasis mt-n1">
				<span>Less sensitive</span>
				<v-spacer></v-spacer>
				<span>More sensitive</span>
			</div>
			<p class="text-body-small text-medium-emphasis mt-1 mb-2">
				Left: fewer frames count as failures (far left, almost none). Right: more frames count as failures
				(far right, almost all).
			</p>
			<v-slider v-model="camera.majority_vote_threshold" :min="1" :max="20" :step="1" color="primary"
					  thumb-label hide-details class="mt-2" @update:model-value="keepWindowAboveThreshold('threshold')"
					  @end="saveCameraSettings">
				<template #prepend>
					<span class="text-no-wrap">Vote Threshold</span>
				</template>
				<template #append>
					<span>{{ camera.majority_vote_threshold }}</span>
				</template>
			</v-slider>
			<v-slider v-model="camera.majority_vote_window" :min="1" :max="100" :step="1" color="primary"
					  thumb-label hide-details class="mt-2" @update:model-value="keepWindowAboveThreshold('window')"
					  @end="saveCameraSettings">
				<template #prepend>
					<span class="text-no-wrap">Vote Window</span>
				</template>
				<template #append>
					<span>{{ camera.majority_vote_window }}</span>
				</template>
			</v-slider>
			<p class="text-body-small text-medium-emphasis mt-2">
				A defect is raised when at least the threshold number of the last window frames show a failure,
				so the window is never smaller than the threshold.
			</p>
		</v-card-text>
	</v-card>
</template>
