<!-- Shown on every page while the printer is not connected: why, and the printer settings to change it (address, port, password) -->
<script setup>
import { computed, reactive, ref, watch } from "vue";
import { api } from "../api.js";
import { notify } from "../notify.js";
import { printer, refreshPrinter } from "../printer.js";
import { mdiEye, mdiEyeOff, mdiRefresh } from "../icons.js";

const p = computed(() => printer.value);
// Shown once a try to connect has failed (not while connecting at startup), until the printer is connected
const shown = ref(false);
watch(p, (value) => {
	shown.value = Boolean(value && !value.connected && (value.error || shown.value));
}, { immediate: true });

const refused = computed(() => p.value?.retrying === false); // e.g. wrong password - no more tries
const title = computed(() => {
	if (p.value?.error) return p.value.error;
	return `Connecting to the printer at ${p.value?.address}`;
});

const form = reactive({ ip: "", port: "", password: "" });
const errors = ref({});
const busy = ref(false);
const showPassword = ref(false);

// Filled in each time the printer is lost - not while it is being edited
watch(shown, (value) => {
	if (value) {
		form.ip = p.value.ip || "";
		form.port = String(p.value.port ?? "");
		form.password = "";
		errors.value = {};
	}
}, { immediate: true });

async function connect() {
	busy.value = true;
	errors.value = {};
	try {
		const reply = await api.postJson("/printer/connect", { ...form });
		notify(reply.message, "success");
		form.password = "";
		await refreshPrinter();
	} catch (err) {
		const errs = err.data?.errors || {};
		errors.value = { ip: errs["DUET.IP"], port: errs["DUET.PORT"], password: errs["DUET.PASSWORD"] };
		notify(err.data?.message || err.message, "error", 6000);
		await refreshPrinter();
	} finally {
		busy.value = false;
	}
}
</script>

<template>
	<v-alert v-if="shown" :type="refused ? 'error' : 'warning'" variant="tonal" class="mb-4">
		<div class="mb-1"><strong>{{ title }}</strong></div>
		<div class="text-body-2 mb-3">
			{{ refused ? "duetPrintGuard will not try again until the printer settings are changed."
				: "duetPrintGuard keeps trying. Check the printer is on, or change its address and port." }}
			Detection still runs, but it cannot pause or cancel the print. The settings are saved.
		</div>
		<v-form class="d-flex flex-wrap ga-3 align-start" @submit.prevent="connect">
			<v-text-field v-if="!p.plugin" v-model="form.ip" label="Printer address" hint="Blank = this computer" persistent-hint
						  density="compact" variant="outlined" style="min-width: 200px; flex: 2 1 200px"
						  :error-messages="errors.ip"></v-text-field>
			<v-text-field v-model="form.port" label="Port" hint="Blank = 80" persistent-hint type="number"
						  density="compact" variant="outlined" style="min-width: 100px; flex: 1 1 100px"
						  :error-messages="errors.port"></v-text-field>
			<v-text-field v-model="form.password" label="Password" hint="Blank = keep the current one" persistent-hint
						  :type="showPassword ? 'text' : 'password'" :append-inner-icon="showPassword ? mdiEyeOff : mdiEye"
						  autocomplete="off" density="compact" variant="outlined" style="min-width: 180px; flex: 2 1 180px"
						  :error-messages="errors.password" @click:append-inner="showPassword = !showPassword"></v-text-field>
			<v-btn type="submit" color="primary" variant="flat" :prepend-icon="mdiRefresh" :loading="busy">Save and connect</v-btn>
		</v-form>
	</v-alert>
</template>
