<!--
One camera on the Settings page: auto-start, detection sensitivity and majority vote. Changes are saved
straight away. A click anywhere on the card (including its controls) selects the camera; no ripple, so
dragging a slider doesn't flash the card.
-->
<script setup>
import { api } from "../api.js";
import { notify } from "../notify.js";
import { errorText, t } from "../i18n.js";
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
		notify(t("camera.autostartFailed", { error: errorText(err) }), "error");
	}
}

// Majority vote: the window (how many recent frames are looked at) is set first, and the threshold (how many of
// them must show a failure) is a share of it - its slider runs from 1 to the window, so its bar shows how strict
// the vote is. A smaller window brings the threshold down with it.
const MAX_WINDOW = 100;

function windowChanged() {
	const camera = props.camera;
	if (camera.majority_vote_threshold > camera.majority_vote_window) {
		camera.majority_vote_threshold = camera.majority_vote_window;
	}
}

// The threshold slider starts at 0, so its bar is exactly threshold / window - but 0 is not allowed
function thresholdChanged() {
	if (props.camera.majority_vote_threshold < 1) {
		props.camera.majority_vote_threshold = 1;
	}
}

const thresholdText = (camera) => t("camera.voteOf", {
	n: camera.majority_vote_threshold,
	window: camera.majority_vote_window,
	percent: Math.round((100 * camera.majority_vote_threshold) / camera.majority_vote_window),
});

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
		notify(t("camera.saveFailed", { error: errorText(err) }), "error");
	}
}

const sensitivityText = (value) => value === 0 ? t("camera.normal")
	: value < 0 ? t("camera.less", { n: value }) : t("camera.more", { n: value });

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
			<v-btn :icon="mdiDelete" variant="text" size="small" color="error" :title="t('camera.remove')"
				   @click.stop="$emit('remove')"></v-btn>
		</v-card-title>
		<v-card-subtitle class="text-wrap text-break">{{ camera.source }}</v-card-subtitle>
		<v-card-text>
			<v-switch v-model="camera.autostart" :label="t('camera.autostart')" color="primary" density="compact"
					  hide-details @update:model-value="saveAutostart"></v-switch>
			<!-- Sensitivity: the middle is normal; log scale, so the ends are effectively fail nothing / fail everything -->
			<div class="d-flex align-center mt-3">
				<span>{{ t("camera.sensitivity") }}</span>
				<v-spacer></v-spacer>
				<v-btn v-if="camera.sensitivity !== 0" variant="text" size="x-small" class="mr-1"
					   @click.stop="resetSensitivity">{{ t("common.reset") }}</v-btn>
				<span class="text-no-wrap">{{ sensitivityText(camera.sensitivity) }}</span>
			</div>
			<v-slider v-model="camera.sensitivity" :min="-SENSITIVITY_STEPS" :max="SENSITIVITY_STEPS" :step="1"
					  :ticks="{ 0: '' }" show-ticks="always" color="primary" track-fill-color="transparent" hide-details
					  @end="saveCameraSettings"></v-slider>
			<div class="d-flex text-body-small text-medium-emphasis mt-n1">
				<span>{{ t("camera.lessSensitive") }}</span>
				<v-spacer></v-spacer>
				<span>{{ t("camera.moreSensitive") }}</span>
			</div>
			<p class="text-body-small text-medium-emphasis mt-1 mb-2">
				{{ t("camera.sensitivityHelp") }}
			</p>
			<!-- Majority vote: the label and value above each slider, so both bars line up -->
			<div class="d-flex align-center mt-3">
				<span>{{ t("camera.voteWindow") }}</span>
				<v-spacer></v-spacer>
				<span class="text-no-wrap">{{ t("camera.voteFrames", { n: camera.majority_vote_window }) }}</span>
			</div>
			<v-slider v-model="camera.majority_vote_window" :min="1" :max="MAX_WINDOW" :step="1" color="primary"
					  thumb-label hide-details @update:model-value="windowChanged" @end="saveCameraSettings"></v-slider>
			<div class="d-flex align-center mt-1">
				<span>{{ t("camera.voteThreshold") }}</span>
				<v-spacer></v-spacer>
				<span class="text-no-wrap">{{ thresholdText(camera) }}</span>
			</div>
			<!-- 0 (not allowed - see thresholdChanged) to the window: the bar is the share of the window's frames
				 that must show a failure -->
			<v-slider v-model="camera.majority_vote_threshold" :min="0" :max="camera.majority_vote_window" :step="1"
					  color="primary" thumb-label hide-details @update:model-value="thresholdChanged"
					  @end="saveCameraSettings"></v-slider>
			<p class="text-body-small text-medium-emphasis mt-2">
				{{ t("camera.voteHelp") }}
			</p>
		</v-card-text>
	</v-card>
</template>
