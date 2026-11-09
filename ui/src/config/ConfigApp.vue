<!-- Configuration page, in tabs: General (printer, web interface), Actions (printer commands) and Alerts (macro, ntfy,
     Pushover). Every card's Save saves the settings on all the tabs. -->
<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import PgPage from "../components/PgPage.vue";
import { api } from "../api.js";
import { notify } from "../notify.js";
import { printer, printerSettingsSaved, refreshPrinter } from "../printer.js";
import { mdiContentSave } from "../icons.js";
import { optional, serverText, t, valueText } from "../i18n.js";

// The tabs of the page; each section names its tab
const tabs = ["general", "actions", "alerts"].map((value) => ({ value, title: t(`config.tabs.${value}`) }));
const tab = ref("general");

// Field names are SECTION.KEY, matching /config/get-app-config and /config/save-app-config. A section's title and help,
// and a field's label, hint and placeholder are in the locale file (config.sections.<id>, config.fields.<SECTION>.<KEY>).
// placeholder here: a printer command, the same in every language. systemDefault: a blank ntfy / Pushover title or
// message uses the system text, shown as the placeholder.
const sections = [
	{
		id: "printer",
		tab: "general",
		fields: [
			{ name: "DUET.IP" },
			{ name: "DUET.PORT", type: "number", min: 1, max: 65535 },
			{ name: "DUET.PASSWORD", type: "password" },
		],
	},
	{
		id: "web",
		tab: "general",
		fields: [
			{ name: "UI.IP", readonly: true },
			{ name: "UI.PORT", type: "number", min: 0, max: 65535, restart: true },
			{ name: "UI.OPENBROWSER", type: "switch" },
			{ name: "LOGGING.LEVEL", type: "select" },
		],
	},
	{
		id: "actions",
		tab: "actions",
		fields: [
			{ name: "ACTION.PAUSE", placeholder: "M25" },
			{ name: "ACTION.RESUME", placeholder: "M24" },
			{ name: "ACTION.CANCEL", placeholder: "M2" },
		],
	},
	{
		id: "macro",
		tab: "alerts",
		fields: [
			{ name: "MACRO.MACRO" },
			{ name: "MACRO.MAXTIMES", type: "number", min: 0 },
		],
	},
	{
		id: "ntfy",
		tab: "alerts",
		link: "https://docs.ntfy.sh/publish/#message-priority",
		fields: [
			{ name: "NTFY.TOPIC" },
			{ name: "NTFY.TITLE", systemDefault: "title" },
			{ name: "NTFY.MESSAGE", systemDefault: "message" },
			{ name: "NTFY.PRIORITY", type: "number", min: 1, max: 5 },
			{ name: "NTFY.MAXTIMES", type: "number", min: 0 },
		],
	},
	{
		id: "pushover",
		tab: "alerts",
		fields: [
			{ name: "PUSHOVER.API" },
			{ name: "PUSHOVER.USER" },
			{ name: "PUSHOVER.TITLE", systemDefault: "title" },
			{ name: "PUSHOVER.MESSAGE", systemDefault: "message" },
			{ name: "PUSHOVER.MAXTIMES", type: "number", min: 0 },
		],
	},
];

const sectionTitle = (section) => t(`config.sections.${section.id}.title`);
const sectionHelp = (section) => optional(`config.sections.${section.id}.help`);
const fieldLabel = (name) => t(`config.fields.${name}.label`);
const fieldText = (field, part) => optional(`config.fields.${field.name}.${part}`);

const editableFields = sections.flatMap((s) => s.fields).filter((f) => !f.readonly);
const tabOfField = Object.fromEntries(sections.flatMap((s) => s.fields.map((f) => [f.name, s.tab])));

const values = reactive({});
const placeholders = reactive({});
const errors = reactive({});
const logLevels = ref([]);
const ipInUse = ref("");
const portStatus = ref("");
const status = reactive({ text: "", type: "success" });
const saving = ref(false);


const printerStatus = computed(() => {
	if (!printer.value) return "";
	const p = printer.value;
	if (p.connected) {
		return t("config.printerConnected", {
			printer: p.address, mode: valueText("mode", p.mode), status: valueText("printerStatus", p.status),
		});
	}
	return p.error ? serverText(p.error, p.errorCode) : t("config.printerConnecting", { printer: p.address });
});

const fieldHint = (field) => {
	const hint = field.systemDefault ? t("config.systemDefaultHint") : fieldText(field, "hint");
	if (field.name === "UI.PORT" && portStatus.value) return `${portStatus.value}. ${hint}`;
	if (field.name === "DUET.IP" && printerStatus.value) return `${printerStatus.value}. ${hint}`;
	return hint;
};

function setErrors(newErrors = {}) {
	Object.keys(errors).forEach((key) => delete errors[key]);
	Object.assign(errors, newErrors);
}

// Tabs holding a setting that was refused - marked, so an error on another tab is not missed
const tabsWithErrors = computed(() => new Set(Object.keys(errors).filter((name) => errors[name]?.length)
	.map((name) => tabOfField[name])));

// Loads the saved settings into the page. With a section (e.g. "DUET"), only that section's fields - the rest keep
// any changes not saved yet
async function load(section = "") {
	try {
		const data = await api.get("/config/get-app-config");
		logLevels.value = data.log_levels;

		for (const field of editableFields) {
			if (section && !field.name.startsWith(`${section}.`)) continue;
			const [group, key] = field.name.split(".");
			const setting = data.settings?.[group]?.[key];
			if (!setting) continue;
			values[field.name] = setting.value;
			placeholders[field.name] = field.placeholder || fieldText(field, "placeholder")
				|| (field.systemDefault && data.default_notification?.[field.systemDefault])
				|| (setting.default !== "" && setting.default !== undefined ? String(setting.default) : "");
		}

		const savedPort = data.settings.UI.PORT.value;
		const portInUse = data.ui_port_in_use;
		ipInUse.value = data.ui_ip_in_use;
		portStatus.value = t("config.portInUse", { port: portInUse });
		if (savedPort === 0) {
			portStatus.value = t("config.portAuto", { status: portStatus.value });
		} else if (portInUse !== savedPort) {
			portStatus.value = t("config.portNext", { status: portStatus.value, port: savedPort });
		}
	} catch (err) {
		console.error("Failed to load configuration:", err);
		Object.assign(status, { text: t("config.loadFailed"), type: "error" });
	}
}

// The printer banner saved new printer settings: show them, so Save here does not put the old ones back
watch(printerSettingsSaved, () => {
	["DUET.IP", "DUET.PORT", "DUET.PASSWORD"].forEach((name) => delete errors[name]);
	load("DUET");
});

async function save() {
	setErrors();
	const data = {};
	for (const field of editableFields) {
		const [section, key] = field.name.split(".");
		data[section] ??= {};
		data[section][key] = values[field.name] ?? "";
	}

	saving.value = true;
	try {
		const result = await api.postJson("/config/save-app-config", data);
		// The alert is at the top of the page, so the snackbar also reports the result when
		// Save is pressed further down
		if (result.restart_required.length) {
			Object.assign(status, {
				text: t("config.savedRestart", { settings: result.restart_required.map(fieldLabel).join(", ") }),
				type: "warning",
			});
			notify(t("config.savedRestartShort"), "warning", 6000);
		} else {
			status.text = "";
			notify(t("config.saved"));
		}
		await load();
		refreshPrinter();
	} catch (err) {
		if (err.status === 400 && err.data?.errors) {
			const codes = err.data.errorCodes || {};
			setErrors(Object.fromEntries(Object.entries(err.data.errors).map(([name, text]) => [name, serverText(text, codes[name])])));
			// Show the first tab with a refused setting, unless this one has one
			if (!tabsWithErrors.value.has(tab.value)) {
				tab.value = tabs.find((t) => tabsWithErrors.value.has(t.value))?.value ?? tab.value;
			}
			Object.assign(status, { text: t("config.invalid"), type: "error" });
			notify(t("config.invalidShort"), "error", 6000);
		} else {
			console.error("Failed to save configuration:", err);
			const text = t("config.saveFailed", { error: serverText(err.message, err.data?.code) });
			Object.assign(status, { text, type: "error" });
			notify(text, "error", 6000);
		}
	} finally {
		saving.value = false;
	}
}

onMounted(() => {
	load();
});
</script>

<template>
	<PgPage>
		<v-row justify="center">
			<v-col cols="12" md="10" lg="8">
				<v-alert v-if="status.text" :type="status.type" variant="tonal" closable class="mb-4"
						 @click:close="status.text = ''">
					{{ status.text }}
				</v-alert>

				<v-tabs v-model="tab" color="primary" grow class="mb-4">
					<v-tab v-for="t in tabs" :key="t.value" :value="t.value"
						   :class="{ 'text-error': tabsWithErrors.has(t.value) }">{{ t.title }}</v-tab>
				</v-tabs>

				<v-form @submit.prevent="save">
					<v-card v-for="section in sections.filter((s) => s.tab === tab)" :key="section.id" class="mb-4">
						<v-card-title>{{ sectionTitle(section) }}</v-card-title>
						<v-card-subtitle v-if="sectionHelp(section)" class="text-wrap">{{ sectionHelp(section) }}</v-card-subtitle>
						<v-card-text>
							<template v-for="field in section.fields" :key="field.name">
								<v-text-field v-if="field.readonly" :label="fieldLabel(field.name)" :model-value="ipInUse"
											  readonly variant="outlined" density="comfortable" class="mb-3"
											  :hint="fieldText(field, 'hint')" persistent-hint></v-text-field>

								<v-switch v-else-if="field.type === 'switch'" v-model="values[field.name]" :label="fieldLabel(field.name)"
										  :hint="fieldHint(field)" persistent-hint :error-messages="errors[field.name]"
										  color="primary" density="comfortable" inset class="mb-3"></v-switch>

								<v-select v-else-if="field.type === 'select'" v-model="values[field.name]"
										  :label="fieldLabel(field.name)" :items="logLevels" :error-messages="errors[field.name]"
										  variant="outlined" density="comfortable" class="mb-3"></v-select>

								<v-text-field v-else v-model="values[field.name]" :label="fieldLabel(field.name)"
											  :type="field.type || 'text'" :min="field.min" :max="field.max"
											  :placeholder="placeholders[field.name]" persistent-placeholder
											  :error-messages="errors[field.name]" :hint="fieldHint(field)" persistent-hint
											  variant="outlined" density="comfortable" class="mb-3">
									<template v-if="field.restart" #append-inner>
										<v-chip size="x-small" color="warning" variant="tonal">{{ t("config.restart") }}</v-chip>
									</template>
								</v-text-field>
							</template>
							<p v-if="section.link" class="text-body-small text-medium-emphasis">
								{{ t("config.priority") }}
								<a :href="section.link" target="_blank" rel="noopener">{{ t("config.priorityLink") }}</a>.
							</p>
						</v-card-text>
						<!-- Every card's Save button saves the whole page, so there is no need to scroll to the bottom -->
						<v-card-actions class="px-4 pb-4 pt-0">
							<v-spacer></v-spacer>
							<v-btn type="submit" color="primary" variant="flat" :prepend-icon="mdiContentSave" :loading="saving">{{ t("common.save") }}</v-btn>
						</v-card-actions>
					</v-card>

					<p class="text-body-small text-medium-emphasis mb-4">
						{{ t("config.footerBefore") }} <v-chip size="x-small" color="warning" variant="tonal">{{ t("config.restart") }}</v-chip>
						{{ t("config.footerAfter") }}
					</p>
				</v-form>
			</v-col>
		</v-row>
	</PgPage>
</template>
