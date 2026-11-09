<!-- Shown on every page while the printer is not connected: why, and the printer settings to change it (address, port, password) -->
<script setup>
import { computed, reactive, ref, watch } from "vue";
import { api } from "../api.js";
import { notify } from "../notify.js";
import { errorText, serverText, t } from "../i18n.js";
import { printer, printerSettingsSaved, refreshPrinter } from "../printer.js";
import { mdiEye, mdiEyeOff, mdiRefresh } from "../icons.js";

const p = computed(() => printer.value);
// Shown once a try to connect has failed (not while connecting at startup), until the printer is connected
const shown = ref(false);
watch(p, (value) => {
	shown.value = Boolean(value && !value.connected && (value.error || shown.value));
}, { immediate: true });

const refused = computed(() => p.value?.retrying === false); // e.g. wrong password - no more tries
const title = computed(() => {
	if (p.value?.error) return serverText(p.value.error, p.value.errorCode);
	return t("printer.connecting", { printer: p.value?.address });
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
		notify(serverText(reply.message, reply.code), "success");
		form.password = "";
		printerSettingsSaved.value++;
		await refreshPrinter();
	} catch (err) {
		const errs = err.data?.errors || {};
		const codes = err.data?.errorCodes || {};
		const fieldError = (name) => errs[name] && serverText(errs[name], codes[name]);
		errors.value = { ip: fieldError("DUET.IP"), port: fieldError("DUET.PORT"), password: fieldError("DUET.PASSWORD") };
		notify(errorText(err), "error", 6000);
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
			{{ refused ? t("printer.refused") : t("printer.retrying") }}
			{{ t("printer.detectionRuns") }}
		</div>
		<v-form class="d-flex flex-wrap ga-3 align-start" @submit.prevent="connect">
			<v-text-field v-if="!p.plugin" v-model="form.ip" :label="t('printer.address')" :hint="t('printer.addressHint')" persistent-hint
						  density="compact" variant="outlined" style="min-width: 200px; flex: 2 1 200px"
						  :error-messages="errors.ip"></v-text-field>
			<v-text-field v-model="form.port" :label="t('printer.port')" :hint="t('printer.portHint')" persistent-hint type="number"
						  density="compact" variant="outlined" style="min-width: 100px; flex: 1 1 100px"
						  :error-messages="errors.port"></v-text-field>
			<v-text-field v-model="form.password" :label="t('printer.password')" :hint="t('printer.passwordHint')" persistent-hint
						  :type="showPassword ? 'text' : 'password'" :append-inner-icon="showPassword ? mdiEyeOff : mdiEye"
						  autocomplete="off" density="compact" variant="outlined" style="min-width: 180px; flex: 2 1 180px"
						  :error-messages="errors.password" @click:append-inner="showPassword = !showPassword"></v-text-field>
			<v-btn type="submit" color="primary" variant="flat" :prepend-icon="mdiRefresh" :loading="busy">{{ t("printer.saveConnect") }}</v-btn>
		</v-form>
	</v-alert>
</template>
