// =========================
// Configuration page
// =========================
const { reactive, ref, onMounted } = Vue;

// Blank ntfy / Pushover titles and messages use the system text, shown as the placeholder
const SYSTEM_DEFAULT_HINT = 'Leave blank to use the system text shown, which follows the camera and countdown settings.';

// Field names are SECTION.KEY, matching /config/get-app-config and /config/save-app-config
const sections = [
	{
		title: 'Web Interface',
		fields: [
			{ name: 'UI.IP' },
			{
				name: 'UI.PORT', label: 'Port', type: 'number', min: 0, max: 65535, restart: true,
				hint: 'Port for the Detection, Settings and Configuration pages. Must not conflict with DWC or other plugins. Use 0 to pick a free port automatically at startup. If the chosen port is in use, a free port is picked instead.'
			},
			{ name: 'LOGGING.LEVEL', label: 'Logging Level', type: 'select' }
		]
	},
	{
		title: 'Printer Actions',
		help: 'Commands sent to the printer when a defect is detected and nobody intervenes. Leave blank to use the default.',
		fields: [
			{ name: 'ACTION.PAUSE', label: 'Pause Command', placeholder: 'M25' },
			{ name: 'ACTION.RESUME', label: 'Resume Command', placeholder: 'M24' },
			{ name: 'ACTION.CANCEL', label: 'Cancel Command', placeholder: 'M2' }
		]
	},
	{
		title: 'Macro Alert',
		fields: [
			{
				name: 'MACRO.MACRO', label: 'Macro', placeholder: 'e.g. 0:/sys/duetPrintGuard/macros/Notify.g',
				hint: 'Macro called on failure e.g. to send MQTT. Enter just the path used in M98 P"<path>".'
			},
			{ name: 'MACRO.MAXTIMES', label: 'Maximum Times', type: 'number', min: 0 }
		]
	},
	{
		title: 'ntfy Alert',
		link: 'https://docs.ntfy.sh/publish/#message-priority',
		fields: [
			{ name: 'NTFY.TOPIC', label: 'Topic', hint: 'The ntfy topic you subscribe to. Required to send ntfy alerts.' },
			{ name: 'NTFY.TITLE', label: 'Title', systemDefault: 'title', hint: SYSTEM_DEFAULT_HINT },
			{ name: 'NTFY.MESSAGE', label: 'Message', systemDefault: 'message', hint: SYSTEM_DEFAULT_HINT },
			{ name: 'NTFY.PRIORITY', label: 'Priority', type: 'number', min: 1, max: 5 },
			{ name: 'NTFY.MAXTIMES', label: 'Maximum Times', type: 'number', min: 0 }
		]
	},
	{
		title: 'Pushover Alert',
		help: 'Both the API token and user key are required to send Pushover alerts.',
		fields: [
			{ name: 'PUSHOVER.API', label: 'API Token' },
			{ name: 'PUSHOVER.USER', label: 'User / Group Key' },
			{ name: 'PUSHOVER.TITLE', label: 'Title', systemDefault: 'title', hint: SYSTEM_DEFAULT_HINT },
			{ name: 'PUSHOVER.MESSAGE', label: 'Message', systemDefault: 'message', hint: SYSTEM_DEFAULT_HINT },
			{ name: 'PUSHOVER.MAXTIMES', label: 'Maximum Times', type: 'number', min: 0 }
		]
	}
];

const editableFields = sections.flatMap((s) => s.fields).filter((f) => f.label);

PG.mount({
	setup() {
		const values = reactive({});
		const placeholders = reactive({});
		const errors = reactive({});
		const logLevels = ref([]);
		const ipInUse = ref('');
		const portStatus = ref('');
		const status = reactive({ text: '', type: 'success' });
		const saving = ref(false);

		const fieldHint = (field) => (field.name === 'UI.PORT' && portStatus.value)
			? `${portStatus.value}. ${field.hint}`
			: field.hint;

		function setErrors(newErrors = {}) {
			Object.keys(errors).forEach((key) => delete errors[key]);
			Object.assign(errors, newErrors);
		}

		async function load() {
			try {
				const data = await PG.api.get('/config/get-app-config');
				logLevels.value = data.log_levels;

				for (const field of editableFields) {
					const [section, key] = field.name.split('.');
					const setting = data.settings?.[section]?.[key];
					if (!setting) continue;
					values[field.name] = setting.value;
					placeholders[field.name] = field.placeholder
						|| (field.systemDefault && data.default_notification?.[field.systemDefault])
						|| (setting.default !== '' && setting.default !== undefined ? String(setting.default) : '');
				}

				const savedPort = data.settings.UI.PORT.value;
				const portInUse = data.ui_port_in_use;
				ipInUse.value = data.ui_ip_in_use;
				portStatus.value = `Currently connected to port ${portInUse}`;
				if (savedPort === 0) {
					portStatus.value += ' (picked automatically)';
				} else if (portInUse !== savedPort) {
					portStatus.value += ` - ${savedPort} will be used after restart, if it is free`;
				}
			} catch (err) {
				console.error('Failed to load configuration:', err);
				Object.assign(status, { text: 'Failed to load configuration.', type: 'error' });
			}
		}

		async function save() {
			setErrors();
			const data = {};
			for (const field of editableFields) {
				const [section, key] = field.name.split('.');
				data[section] ??= {};
				data[section][key] = values[field.name] ?? '';
			}

			saving.value = true;
			try {
				const result = await PG.api.postJson('/config/save-app-config', data);
				if (result.restart_required.length) {
					Object.assign(status, {
						text: `Saved. Restart the plugin for these changes to take effect: ${result.restart_required.join(', ')}`,
						type: 'warning'
					});
				} else {
					status.text = '';
					PG.notify('Saved.');
				}
				await load();
			} catch (err) {
				if (err.status === 400 && err.data?.errors) {
					setErrors(err.data.errors);
					Object.assign(status, { text: 'Some settings are invalid - nothing was saved.', type: 'error' });
				} else {
					console.error('Failed to save configuration:', err);
					Object.assign(status, { text: `Failed to save configuration: ${err.message}`, type: 'error' });
				}
			} finally {
				saving.value = false;
			}
		}

		onMounted(load);

		return { sections, values, placeholders, errors, logLevels, ipInUse, status, saving, fieldHint, save };
	}
});
