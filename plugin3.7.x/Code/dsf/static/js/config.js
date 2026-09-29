// =========================
// Helper Functions
// =========================
function getPageURL(page) {
	return window.isMobileMode ? `${page}?mobile=true` : page;
}

// =========================
// Elements
// =========================
const configForm = document.getElementById('configForm');
const saveBtn = document.getElementById('saveBtn');
const statusMessage = document.getElementById('statusMessage');
const passwordHelp = document.getElementById('passwordHelp');
const logLevelSelect = document.getElementById('LOGGING.LEVEL');

// =========================
// Status Message
// =========================
function showStatus(message, type) {
	statusMessage.textContent = message;
	statusMessage.className = `status-message ${type}`;
	statusMessage.style.display = 'block';
	statusMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function clearFieldErrors() {
	configForm
		.querySelectorAll('.field-error')
		.forEach(el => el.remove());
	configForm
		.querySelectorAll('.invalid')
		.forEach(el => el.classList.remove('invalid'));
}

function showFieldErrors(errors) {
	for (const [name, message] of Object.entries(errors)) {
		const input = configForm.elements[name];
		if (!input) continue;
		input.classList.add('invalid');
		const error = document.createElement('p');
		error.className = 'field-error';
		error.textContent = message;
		input.closest('.form-group').appendChild(error);
	}
}

// =========================
// Load Configuration
// =========================
async function loadConfig() {
	try {
		const response = await fetch('/config/get-app-config');
		if (!response.ok) {
			throw new Error(response.statusText);
		}
		const data = await response.json();

		logLevelSelect.innerHTML = '';
		data.log_levels.forEach(level => {
			const option = document.createElement('option');
			option.value = level;
			option.textContent = level;
			logLevelSelect.appendChild(option);
		});

		for (const [section, keys] of Object.entries(data.settings)) {
			for (const [key, setting] of Object.entries(keys)) {
				const input = configForm.elements[`${section}.${key}`];
				if (!input) continue;

				if (input.type === 'checkbox') {
					input.checked = Boolean(setting.value);
				} else {
					input.value = setting.value;
				}

				if (!input.placeholder && setting.default !== '') {
					input.placeholder = setting.default;
				}
			}
		}

		const ipInput = configForm.elements['DUET.IP'];
		ipInput.placeholder = `Auto-detect (${data.detected_ip})`;

		const password = data.settings.DUET.PASSWORD;
		passwordHelp.textContent = password.is_set
			? 'A password is set. Leave blank to keep it.'
			: 'Only needed if a password has been set in the DWC configuration. Leave blank to use the default.';

	} catch (err) {
		console.error('Failed to load configuration:', err);
		showStatus('Failed to load configuration.', 'error');
	}
}

// =========================
// Save Configuration
// =========================
configForm.addEventListener('submit', async function(e) {

	e.preventDefault();
	clearFieldErrors();

	const data = {};
	for (const input of configForm.elements) {
		if (!input.name) continue;
		const [section, key] = input.name.split('.');
		data[section] ??= {};
		data[section][key] =
			input.type === 'checkbox' ? input.checked : input.value;
	}

	saveBtn.disabled = true;

	try {
		const response = await fetch('/config/save-app-config', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(data)
		});

		const result = await response.json();

		if (response.status === 400 && result.errors) {
			showFieldErrors(result.errors);
			showStatus('Some settings are invalid - nothing was saved.', 'error');
			return;
		}

		if (!response.ok) {
			throw new Error(result.detail || response.statusText);
		}

		configForm.elements['DUET.PASSWORD'].value = '';

		if (result.restart_required.length) {
			showStatus(
				`Saved. Restart the plugin for these changes to take effect: ${result.restart_required.join(', ')}`,
				'warning'
			);
		} else {
			showStatus('Saved.', 'success');
		}

		await loadConfig();

	} catch (err) {
		console.error('Failed to save configuration:', err);
		showStatus(`Failed to save configuration: ${err.message}`, 'error');
	} finally {
		saveBtn.disabled = false;
	}
});

// =========================
// Navigation
// =========================
document.getElementById('settingsBtn').addEventListener('click', () => {
	window.location.href = getPageURL('/settings');
});

document.getElementById('detectionBtn').addEventListener('click', () => {
	window.location.href = getPageURL('/index');
});

loadConfig();
