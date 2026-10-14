<!-- Configuration page: web interface, printer commands and notifications. Every card's Save saves the whole page. -->
<script setup>
import { onMounted, reactive, ref } from "vue";
import PgPage from "../components/PgPage.vue";
import { api } from "../api.js";
import { notify } from "../notify.js";
import { mdiContentSave } from "../icons.js";

// Blank ntfy / Pushover titles and messages use the system text, shown as the placeholder
const SYSTEM_DEFAULT_HINT = "Leave blank to use the system text shown, which follows the camera and countdown settings.";

// Field names are SECTION.KEY, matching /config/get-app-config and /config/save-app-config
const sections = [
	{
		title: "Web Interface",
		fields: [
			{ name: "UI.IP" },
			{
				name: "UI.PORT", label: "Port", type: "number", min: 0, max: 65535, restart: true,
				hint: "Port for the Detection, Settings and Configuration pages. Must not conflict with DWC or other plugins. Use 0 to pick a free port automatically at startup. If the chosen port is in use, a free port is picked instead.",
			},
			{ name: "LOGGING.LEVEL", label: "Logging Level", type: "select" },
		],
	},
	{
		title: "Printer Actions",
		help: "Commands sent to the printer when a defect is detected and nobody intervenes. Leave blank to use the default.",
		fields: [
			{ name: "ACTION.PAUSE", label: "Pause Command", placeholder: "M25" },
			{ name: "ACTION.RESUME", label: "Resume Command", placeholder: "M24" },
			{ name: "ACTION.CANCEL", label: "Cancel Command", placeholder: "M2" },
		],
	},
	{
		title: "Macro Alert",
		fields: [
			{
				name: "MACRO.MACRO", label: "Macro", placeholder: "e.g. 0:/sys/duetPrintGuard/macros/Notify.g",
				hint: 'Macro called on failure e.g. to send MQTT. Enter just the path used in M98 P"<path>".',
			},
			{ name: "MACRO.MAXTIMES", label: "Maximum Times", type: "number", min: 0 },
		],
	},
	{
		title: "ntfy Alert",
		link: "https://docs.ntfy.sh/publish/#message-priority",
		fields: [
			{ name: "NTFY.TOPIC", label: "Topic", hint: "The ntfy topic you subscribe to. Required to send ntfy alerts." },
			{ name: "NTFY.TITLE", label: "Title", systemDefault: "title", hint: SYSTEM_DEFAULT_HINT },
			{ name: "NTFY.MESSAGE", label: "Message", systemDefault: "message", hint: SYSTEM_DEFAULT_HINT },
			{ name: "NTFY.PRIORITY", label: "Priority", type: "number", min: 1, max: 5 },
			{ name: "NTFY.MAXTIMES", label: "Maximum Times", type: "number", min: 0 },
		],
	},
	{
		title: "Pushover Alert",
		help: "Both the API token and user key are required to send Pushover alerts.",
		fields: [
			{ name: "PUSHOVER.API", label: "API Token" },
			{ name: "PUSHOVER.USER", label: "User / Group Key" },
			{ name: "PUSHOVER.TITLE", label: "Title", systemDefault: "title", hint: SYSTEM_DEFAULT_HINT },
			{ name: "PUSHOVER.MESSAGE", label: "Message", systemDefault: "message", hint: SYSTEM_DEFAULT_HINT },
			{ name: "PUSHOVER.MAXTIMES", label: "Maximum Times", type: "number", min: 0 },
		],
	},
];

const editableFields = sections.flatMap((s) => s.fields).filter((f) => f.label);

const values = reactive({});
const placeholders = reactive({});
const errors = reactive({});
const logLevels = ref([]);
const ipInUse = ref("");
const portStatus = ref("");
const status = reactive({ text: "", type: "success" });
const saving = ref(false);

const fieldHint = (field) => (field.name === "UI.PORT" && portStatus.value)
	? `${portStatus.value}. ${field.hint}`
	: field.hint;

function setErrors(newErrors = {}) {
	Object.keys(errors).forEach((key) => delete errors[key]);
	Object.assign(errors, newErrors);
}

async function load() {
	try {
		const data = await api.get("/config/get-app-config");
		logLevels.value = data.log_levels;

		for (const field of editableFields) {
			const [section, key] = field.name.split(".");
			const setting = data.settings?.[section]?.[key];
			if (!setting) continue;
			values[field.name] = setting.value;
			placeholders[field.name] = field.placeholder
				|| (field.systemDefault && data.default_notification?.[field.systemDefault])
				|| (setting.default !== "" && setting.default !== undefined ? String(setting.default) : "");
		}

		const savedPort = data.settings.UI.PORT.value;
		const portInUse = data.ui_port_in_use;
		ipInUse.value = data.ui_ip_in_use;
		portStatus.value = `Currently connected to port ${portInUse}`;
		if (savedPort === 0) {
			portStatus.value += " (picked automatically)";
		} else if (portInUse !== savedPort) {
			portStatus.value += ` - ${savedPort} will be used after restart, if it is free`;
		}
	} catch (err) {
		console.error("Failed to load configuration:", err);
		Object.assign(status, { text: "Failed to load configuration.", type: "error" });
	}
}

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
				text: `Saved. Restart the plugin for these changes to take effect: ${result.restart_required.join(", ")}`,
				type: "warning",
			});
			notify("Saved - restart the plugin for some changes to take effect.", "warning", 6000);
		} else {
			status.text = "";
			notify("Saved.");
		}
		await load();
	} catch (err) {
		if (err.status === 400 && err.data?.errors) {
			setErrors(err.data.errors);
			Object.assign(status, { text: "Some settings are invalid - nothing was saved.", type: "error" });
			notify("Some settings are invalid (marked in red) - nothing was saved.", "error", 6000);
		} else {
			console.error("Failed to save configuration:", err);
			Object.assign(status, { text: `Failed to save configuration: ${err.message}`, type: "error" });
			notify(`Failed to save configuration: ${err.message}`, "error", 6000);
		}
	} finally {
		saving.value = false;
	}
}

onMounted(load);
</script>

<template>
	<PgPage>
		<v-row justify="center">
			<v-col cols="12" md="10" lg="8">
				<v-alert v-if="status.text" :type="status.type" variant="tonal" closable class="mb-4"
						 @click:close="status.text = ''">
					{{ status.text }}
				</v-alert>

				<v-form @submit.prevent="save">
					<v-card v-for="section in sections" :key="section.title" class="mb-4">
						<v-card-title>{{ section.title }}</v-card-title>
						<v-card-subtitle v-if="section.help" class="text-wrap">{{ section.help }}</v-card-subtitle>
						<v-card-text>
							<template v-for="field in section.fields" :key="field.name">
								<v-text-field v-if="field.name === 'UI.IP'" label="IP Address" :model-value="ipInUse"
											  readonly variant="outlined" density="comfortable" class="mb-3"
											  hint="IP address of this machine, detected automatically at startup."
											  persistent-hint></v-text-field>

								<v-select v-else-if="field.type === 'select'" v-model="values[field.name]"
										  :label="field.label" :items="logLevels" :error-messages="errors[field.name]"
										  variant="outlined" density="comfortable" class="mb-3"></v-select>

								<v-text-field v-else v-model="values[field.name]" :label="field.label"
											  :type="field.type || 'text'" :min="field.min" :max="field.max"
											  :placeholder="placeholders[field.name]" persistent-placeholder
											  :error-messages="errors[field.name]" :hint="fieldHint(field)" persistent-hint
											  variant="outlined" density="comfortable" class="mb-3">
									<template v-if="field.restart" #append-inner>
										<v-chip size="x-small" color="warning" variant="tonal">restart</v-chip>
									</template>
								</v-text-field>
							</template>
							<p v-if="section.link" class="text-body-small text-medium-emphasis">
								Priority 1 to 5 - see
								<a :href="section.link" target="_blank" rel="noopener">ntfy message priority</a>.
							</p>
						</v-card-text>
						<!-- Every card's Save button saves the whole page, so there is no need to scroll to the bottom -->
						<v-card-actions class="px-4 pb-4 pt-0">
							<v-spacer></v-spacer>
							<v-btn type="submit" color="primary" variant="flat" :prepend-icon="mdiContentSave" :loading="saving">Save</v-btn>
						</v-card-actions>
					</v-card>

					<p class="text-body-small text-medium-emphasis mb-4">
						Settings marked <v-chip size="x-small" color="warning" variant="tonal">restart</v-chip>
						take effect after the plugin is restarted. Other settings apply immediately.
						Each Save button saves all the settings on this page.
					</p>
				</v-form>
			</v-col>
		</v-row>
	</PgPage>
</template>
