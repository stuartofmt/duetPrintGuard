<!-- Log page: the log file - its end, then new lines as they are written (checked every few seconds).
     Follow keeps the newest line in view. The same as duetLapse3's Log tab. -->
<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import PgPage from "../components/PgPage.vue";
import { api } from "../api.js";
import { errorText, t } from "../i18n.js";
import { mdiDownload, mdiMagnify, mdiRefresh } from "../icons.js";

const MAX_LINES = 10000; // Older lines are dropped from the page - the log file keeps them
const CHECK_SECONDS = 3;

const lines = ref([]);
const log = reactive({ loaded: false, file: "", error: "", truncated: false });
const filter = ref("");
const follow = ref(true);
const loading = ref(false);
const box = ref(null);
let offset = -1;
let timer = null;

async function load() {
	if (loading.value) return;
	loading.value = true;
	try {
		const data = await api.get(`/log/text?offset=${offset}`);
		Object.assign(log, { loaded: true, file: data.file ?? "", error: data.error ?? "" });
		if (!data.error) {
			const added = data.text ? data.text.replace(/\n$/, "").split("\n") : [];
			const all = data.reset ? added : [...lines.value, ...added];
			log.truncated = data.reset ? data.truncated : log.truncated || all.length > MAX_LINES;
			lines.value = all.slice(-MAX_LINES);
			offset = data.offset;
		}
	} catch (err) {
		Object.assign(log, { loaded: true, error: errorText(err) });
	} finally {
		loading.value = false;
	}
}

// From the end of the log file again
function reload() {
	offset = -1;
	load();
}

const text = computed(() => {
	const wanted = filter.value.trim().toLowerCase();
	return (wanted ? lines.value.filter((line) => line.toLowerCase().includes(wanted)) : lines.value).join("\n");
});

function toEnd() {
	if (box.value) {
		box.value.scrollTop = box.value.scrollHeight;
	}
}

// Scrolling up to read stops following, and scrolling back to the end starts it again
function scrolled() {
	const b = box.value;
	follow.value = b.scrollHeight - b.scrollTop - b.clientHeight < 20;
}

watch(text, async () => {
	if (follow.value) {
		await nextTick();
		toEnd();
	}
});
watch(follow, (on) => on && toEnd());

onMounted(() => {
	load();
	// New lines - not while the page is hidden (another browser tab in front)
	timer = setInterval(() => document.hidden || load(), CHECK_SECONDS * 1000);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
	<PgPage>
		<v-card>
			<div class="d-flex flex-wrap align-center ga-2 pa-3">
				<v-text-field v-model="filter" :prepend-inner-icon="mdiMagnify" :placeholder="t('log.filter')" clearable
							  variant="outlined" density="compact" hide-details style="min-width: 180px; max-width: 320px"
							  @update:model-value="filter = $event ?? ''"></v-text-field>
				<v-spacer></v-spacer>
				<v-switch v-model="follow" :label="t('log.follow')" color="primary" density="compact" inset hide-details
						  class="flex-grow-0 me-2"></v-switch>
				<v-btn :icon="mdiRefresh" variant="text" size="small" :loading="loading" :title="t('log.reload')" @click="reload"></v-btn>
				<v-btn :icon="mdiDownload" variant="text" size="small" :disabled="!log.file" href="/log/download"
					   :title="t('log.download')"></v-btn>
			</div>
			<v-divider></v-divider>
			<v-alert v-if="log.error" type="error" variant="tonal" class="ma-3">{{ t("log.couldNotRead", { error: log.error }) }}</v-alert>
			<v-alert v-else-if="log.loaded && !log.file" type="info" variant="tonal" class="ma-3">{{ t("log.noFile") }}</v-alert>
			<template v-else>
				<div v-if="log.truncated" class="text-caption text-medium-emphasis px-3 pt-2">{{ t("log.truncated") }}</div>
				<pre ref="box" class="pg-log pa-3" @scroll.passive="scrolled">{{ text }}</pre>
				<div v-if="log.loaded && !text" class="text-center text-medium-emphasis pa-4">
					{{ filter ? t("log.noMatch", { filter }) : t("log.empty") }}
				</div>
				<div v-if="log.file" class="text-caption text-medium-emphasis px-3 pb-2 pg-break">{{ log.file }}</div>
			</template>
		</v-card>
	</PgPage>
</template>

<style scoped>
.pg-log {
	height: calc(100vh - 230px);
	min-height: 300px;
	overflow: auto;
	margin: 0;
	font-family: ui-monospace, Consolas, "DejaVu Sans Mono", monospace;
	font-size: 12px;
	line-height: 1.45;
	white-space: pre;
}

.pg-break {
	overflow-wrap: anywhere;
}
</style>
