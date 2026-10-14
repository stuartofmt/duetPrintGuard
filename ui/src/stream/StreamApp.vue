<!--
A camera's live stream in its own tab, opened from the Detection page (/stream/<nickname>).

HTTP cameras are shown directly from the camera, at its own frame rate. RTSP cameras (which browsers cannot
play), or a direct stream that fails, are shown through the plugin instead. The stream is closed while the
tab is hidden (see visibility.js).
-->
<script setup>
import { computed, onMounted, ref } from "vue";
import { api } from "../api.js";
import { visibility } from "../visibility.js";

// /stream/<nickname> from the plugin, or ?nickname= under the Vite dev server
const nickname = new URLSearchParams(window.location.search).get("nickname")
	|| decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop() || "");

const info = ref(null);
const error = ref("");
const useDirect = ref(false);

const streamUrl = computed(() => {
	if (!info.value || !visibility.visible) return "";
	return useDirect.value ? info.value.direct_url : `/camera/stream/${encodeURIComponent(info.value.camera_uuid)}`;
});

function onStreamError() {
	if (useDirect.value) {
		console.warn("Direct camera stream failed - using the plugin stream instead");
		useDirect.value = false;
	}
}

onMounted(async () => {
	document.title = `${nickname} - Camera Stream`;
	try {
		info.value = await api.get(`/stream-info/${encodeURIComponent(nickname)}`);
		useDirect.value = Boolean(info.value.direct_url);
	} catch (err) {
		error.value = err.status === 404 ? `There is no camera called "${nickname}".` : `Could not load the stream: ${err.message}`;
	}
});
</script>

<template>
	<v-app>
		<v-main>
			<v-container class="d-flex flex-column align-center ga-4 py-6">
				<h1 class="text-headline-medium">{{ info?.nickname || nickname }}</h1>
				<v-alert v-if="error" type="error" variant="tonal" max-width="960" class="w-100">{{ error }}</v-alert>
				<v-card v-else class="w-100" max-width="960">
					<div class="pg-media">
						<img v-if="streamUrl" :src="streamUrl" :alt="`Live stream for ${nickname}`" @error="onStreamError" />
					</div>
				</v-card>
			</v-container>
		</v-main>
	</v-app>
</template>
