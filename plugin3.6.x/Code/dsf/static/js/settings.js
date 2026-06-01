// =========================
// Templates
// =========================
const camTemplate = document.getElementById("camera-template");
const grid = document.getElementById("grid");

// =========================
// Globals
// =========================
let cameraItems = [];
let cameraUUID = null;

// Main preview
const camVideoPreview = document.getElementById('videoPreview');
const loadingOverlay = document.getElementById('loadingOverlay');

// Settings
const settingsCameraUUID = document.getElementById('camera_uuid');

const settingsSensitivity =
	document.getElementById('sensitivity');

const settingsSensitivityLabel =
	document.getElementById('sensitivity_val');

const settingsBrightness =
	document.getElementById('brightness');

const settingsBrightnessLabel =
	document.getElementById('brightness_val');

const settingsContrast =
	document.getElementById('contrast');

const settingsContrastLabel =
	document.getElementById('contrast_val');

const settingsFocus =
	document.getElementById('focus');

const settingsFocusLabel =
	document.getElementById('focus_val');

const settingsMajorityVoteThreshold =
	document.getElementById('majority_vote_threshold');

const settingsMajorityVoteThresholdLabel =
	document.getElementById('majority_vote_threshold_val');

const settingsMajorityVoteWindow =
	document.getElementById('majority_vote_window');

const settingsMajorityVoteWindowLabel =
	document.getElementById('majority_vote_window_val');

// Countdown
const settingsCountdownAction =
	document.getElementById('countdown_action');

const settingsCountdownTime =
	document.getElementById('countdown_time');

const settingsCountdownTimeLabel =
	document.getElementById('countdown_time_val');

const settingsCountdownControl =
	document.getElementById('countdown_control');

// Modal
const addCameraModalOverlay =
	document.getElementById('addCameraModalOverlay');

const addCameraModalClose =
	document.getElementById('addCameraModalClose');

const addCameraBtn =
	document.getElementById('addCameraBtn');

const detectionBtn =
	document.getElementById('detectionBtn');

const addFirstCameraBtn =
	document.getElementById('addFirstCameraBtn');

// Camera type selection
const addSerialCameraButton =
	document.getElementById('addSerialCameraButton');

const addRtspCameraButton =
	document.getElementById('addRtspCameraButton');

const cameraTypeSelection =
	document.getElementById('cameraTypeSelection');

const addCameraForm =
	document.getElementById('addCameraForm');

const serialCameraSetup =
	document.getElementById('serialCameraSetup');

const rtspCameraSetup =
	document.getElementById('rtspCameraSetup');

const serialDeviceSelect =
	document.getElementById('serialDevice');

const rtspUrlInput =
	document.getElementById('rtspUrl');

const serialLoading =
	document.getElementById('serialLoading');

const noSerialDeviceMessage =
	document.getElementById('noSerialDeviceMessage');

// Preview
const enablePreview =
	document.getElementById('enablePreview');

const cameraPreviewContainer =
	document.getElementById('cameraPreviewContainer');

const cameraPreviewImage =
	document.getElementById('cameraPreviewImage');

const cameraPreviewLoading =
	document.getElementById('cameraPreviewLoading');

const cameraPreviewError =
	document.getElementById('cameraPreviewError');

let previewUpdateTimeout;
let previewRequestId = 0;

// =========================
// API
// =========================
async function getCameraList() {

	console.warn('Fetching camera list');

	try {

		const res =
			await fetch("/config/get-camera-list");

		if (!res.ok) {
			return {};
		}

		const data = await res.json();
		return data.list || {};

	} catch (err) {

		console.error(
			'Failed to fetch camera list:',
			err
		);

		return {};

	}
}

// =========================
// Create Camera Display
// =========================
function createDisplayItem(
	camId,
	nickname,
	source
) {

	if (!camTemplate || !grid) {
		console.error(
			'Missing template or grid'
		);
		return null;
	}

	const row =
		document.createElement("div");

	row.className = "camera-row";

	const camFrag =
		camTemplate.content.cloneNode(true);

	const card =
		camFrag.firstElementChild;

	if (!card) {
		console.error(
			'Invalid camera template'
		);
		return null;
	}

	row.dataset.cameraId = camId;

	const nicknameEl =
		camFrag.querySelector('.nickname');

	const sourceEl =
		camFrag.querySelector('.source');

	if (nicknameEl) {
		nicknameEl.textContent = nickname;
	}

	if (sourceEl) {
		sourceEl.textContent = source;
	}

	row.appendChild(card);

	grid.appendChild(row);

	return row;
}

// =========================
// Main Snapshot
// =========================
if (camVideoPreview) {

	camVideoPreview.onload = () => {

		if (loadingOverlay) {
			loadingOverlay.style.display = 'none';
		}
	};

	camVideoPreview.onerror = () => {

		if (loadingOverlay) {
			loadingOverlay.style.display = 'none';
		}

		console.error(
			'Failed to load camera feed.'
		);
	};
}

function updateCameraSnapshot(cameraUUID) {

	if (!camVideoPreview) {
		return;
	}

	if (loadingOverlay) {
		loadingOverlay.style.display = 'flex';
	}

	camVideoPreview.src =
		`/camera/snapshot/${cameraUUID}?t=${Date.now()}`;
}

// =========================
// Camera Settings
// =========================
function updateSelectedCameraSettings(d) {

	const settingsMap = [
		[
			settingsSensitivity,
			settingsSensitivityLabel,
			d.sensitivity
		],
		[
			settingsBrightness,
			settingsBrightnessLabel,
			d.brightness
		],
		[
			settingsContrast,
			settingsContrastLabel,
			d.contrast
		],
		[
			settingsFocus,
			settingsFocusLabel,
			d.focus
		],
		[
			settingsMajorityVoteThreshold,
			settingsMajorityVoteThresholdLabel,
			d.majority_vote_threshold
		],
		[
			settingsMajorityVoteWindow,
			settingsMajorityVoteWindowLabel,
			d.majority_vote_window
		]
	];

	if (settingsCameraUUID) {
		settingsCameraUUID.value =
			d.camera_uuid;
	}

	settingsMap.forEach(
		([slider, label, value]) => {

			if (!slider) return;

			slider.value = value;

			if (label) {
				label.textContent = value;
			}

			updateSliderFill(slider);

		}
	);
}

// =========================
// Fetch Camera Settings
// =========================
function fetchAndUpdateCameraSettings(
	cameraUUID
) {

	if (!cameraUUID) {
		return;
	}

	fetch('/config/get-camera-setting', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			camera_uuid: cameraUUID
		})
	})
	.then(response => {

		if (!response.ok) {
			throw new Error(
				response.statusText
			);
		}

		return response.json();

	})
	.then(data => {
		const setting = data.setting

		updateSelectedCameraSettings({
			camera_uuid: cameraUUID,
			brightness: setting.brightness,
			contrast: setting.contrast,
			focus: setting.focus,
			sensitivity: setting.sensitivity,
			//majority_vote_threshold:
			//	data.majority_vote_threshold,
			//majority_vote_window:
			//	data.majority_vote_window
		});

	})
	.catch(err => {

		console.error(
			'Failed to fetch settings:',
			err
		);

	});
}

// =========================
// Remove Camera
// =========================
function removeCamera(cameraUUID) {

	if (!cameraUUID) {
		return;
	}

	if (
		!confirm(
			'Are you sure you want to remove this camera?'
		)
	) {
		return;
	}

	fetch('/config/remove-camera', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			camera_uuid: cameraUUID
		})
	})
	.then(response => {

		if (!response.ok) {
			throw new Error(
				response.statusText
			);
		}

		return response.json();

	})
	.then(() => {

		const item =
			document.querySelector(
				`.camera-row[data-camera-id="${cameraUUID}"]`
			);

		if (item) {
			item.remove();
		}

		window.location.reload();

	})
	.catch(err => {

		console.error(
			'Failed to remove camera:',
			err
		);

		alert(
			`Failed to remove camera: ${err.message}`
		);

	});
}

// =========================
// Camera Item Listeners
// =========================
function addListenerToDisplayItem(
	item,
	cameraId
) {

	const card =
		item.querySelector('.camera-item');

	item.addEventListener(
		'click',
		function() {

			document
				.querySelectorAll(
					'.camera-item.selected'
				)
				.forEach(i =>
					i.classList.remove('selected')
				);

			card?.classList.add('selected');

			cameraUUID = cameraId;

			if (settingsCameraUUID) {
				settingsCameraUUID.value =
					cameraId;
			}

			fetchAndUpdateCameraSettings(
				cameraId
			);

			updateCameraSnapshot(cameraId);

		}
	);

	const removeButton =
		item.querySelector(
			'.remove-camera-btn'
		);

	removeButton?.addEventListener(
		'click',
		function(event) {

			event.stopPropagation();

			removeCamera(
				item.dataset.cameraId
			);

		}
	);
}

// =========================
// Slider Fill
// =========================
function updateSliderFill(slider) {

	if (!slider) {
		return;
	}

	const min =
		Number(slider.min || 0);

	const max =
		Number(slider.max || 100);

	const value =
		Number(slider.value);

	const percentage =
		max === min
			? 0
			: ((value - min) / (max - min)) * 100;

	slider.style.setProperty(
		'--value',
		`${percentage}%`
	);

	const valueSpan =
		document.getElementById(
			`${slider.id}_val`
		);

	if (valueSpan) {
		valueSpan.textContent = value;
	}
}

// =========================
// Save Settings
// =========================
function saveSetting(inputElement) {

	if (!inputElement) {
		return;
	}

	if (!inputElement.name) {
		console.warn(
			'Input missing name attribute'
		);
		return;
	}

	const settingsForm =
		inputElement.closest('form');

	if (!settingsForm) {
		return;
	}

	const formData =
		new FormData(settingsForm);

	formData.set(
		inputElement.name,
		inputElement.value
	);

	fetch(settingsForm.action, {
		method: 'POST',
		headers: {
			'Content-Type':
				'application/x-www-form-urlencoded'
		},
		body: new URLSearchParams(formData)
	})
	.then(response => {

		if (!response.ok) {

			console.error(
				`Failed to save ${inputElement.name}`
			);

			return;
		}

		const currentCameraUUID =
			settingsCameraUUID?.value;

		if (currentCameraUUID) {

			fetchAndUpdateCameraSettings(
				currentCameraUUID
			);

			updateCameraSnapshot(
				currentCameraUUID
			);
		}

	})
	.catch(err => {

		console.error(
			'Save setting error:',
			err
		);

	});
}

// =========================
// Preview Helpers
// =========================
function showPreviewLoading() {

	if (
		!cameraPreviewImage ||
		!cameraPreviewError ||
		!cameraPreviewLoading
	) {
		return;
	}

	cameraPreviewImage.style.display =
		'none';

	cameraPreviewError.style.display =
		'none';

	cameraPreviewLoading.style.display =
		'flex';
}

function showPreviewError() {

	if (
		!cameraPreviewImage ||
		!cameraPreviewError ||
		!cameraPreviewLoading
	) {
		return;
	}

	cameraPreviewImage.style.display =
		'none';

	cameraPreviewLoading.style.display =
		'none';

	cameraPreviewError.style.display =
		'flex';
}

function showPreviewImage(src) {

	if (
		!cameraPreviewImage ||
		!cameraPreviewError ||
		!cameraPreviewLoading
	) {
		return;
	}

	cameraPreviewLoading.style.display =
		'none';

	cameraPreviewError.style.display =
		'none';

	cameraPreviewImage.src = src;

	cameraPreviewImage.style.display =
		'block';
}

function hidePreview() {

	cameraPreviewContainer?.style &&
		(cameraPreviewContainer.style.display =
			'none');

	cameraPreviewImage?.style &&
		(cameraPreviewImage.style.display =
			'none');

	cameraPreviewLoading?.style &&
		(cameraPreviewLoading.style.display =
			'none');

	cameraPreviewError?.style &&
		(cameraPreviewError.style.display =
			'none');
}

// =========================
// Update Preview
// =========================
function updatePreview() {

	if (!enablePreview?.checked) {

		hidePreview();

		return;
	}

	if (cameraPreviewContainer) {
		cameraPreviewContainer.style.display =
			'block';
	}

	let source = '';

	if (
		serialCameraSetup &&
		serialCameraSetup.style.display !==
			'none' &&
		serialDeviceSelect?.value
	) {

		source = serialDeviceSelect.value;

	} else if (
		rtspCameraSetup &&
		rtspCameraSetup.style.display !==
			'none' &&
		rtspUrlInput?.value
	) {

		source = rtspUrlInput.value;
	}

	if (!source) {

		showPreviewError();

		return;
	}

	showPreviewLoading();

	const requestId =
		++previewRequestId;

	const previewUrl =
		`/camera/preview?source=${encodeURIComponent(source)}`;

	const img = new Image();

	img.onload = function() {

		if (
			requestId !==
			previewRequestId
		) {
			return;
		}

		showPreviewImage(previewUrl);
	};

	img.onerror = function() {

		if (
			requestId !==
			previewRequestId
		) {
			return;
		}

		showPreviewError();
	};

	img.src = previewUrl;
}

function schedulePreviewUpdate() {

	if (previewUpdateTimeout) {
		clearTimeout(
			previewUpdateTimeout
		);
	}

	previewUpdateTimeout =
		setTimeout(updatePreview, 1000);
}

// =========================
// Camera Type Buttons
// =========================
addSerialCameraButton?.addEventListener(
	'click',
	async () => {

		cameraTypeSelection?.style &&
			(cameraTypeSelection.style.display =
				'none');

		addCameraForm?.style &&
			(addCameraForm.style.display =
				'block');

		serialCameraSetup?.style &&
			(serialCameraSetup.style.display =
				'block');

		rtspCameraSetup?.style &&
			(rtspCameraSetup.style.display =
				'none');

		if (rtspUrlInput) {
			rtspUrlInput.required =
				false;
		}

		if (serialDeviceSelect) {
			serialDeviceSelect.required =
				true;
		}

		if (serialLoading) {
			serialLoading.style.display =
				'block';
		}

		try {

			const response =
				await fetch(
					'/camera/serial_devices'
				);

			if (!response.ok) {
				throw new Error(
					`HTTP ${response.status}`
				);
			}

			const devices =
				await response.json();

			if (!serialDeviceSelect) {
				return;
			}

			serialDeviceSelect.innerHTML =
				'';

			if (devices.length > 0) {

				const defaultOption =
					document.createElement(
						'option'
					);

				defaultOption.value =
					'';

				defaultOption.textContent =
					'Select a serial device';

				defaultOption.disabled =
					true;

				defaultOption.selected =
					true;

				serialDeviceSelect.appendChild(
					defaultOption
				);

				devices.forEach(device => {

					const option =
						document.createElement(
							'option'
						);

					option.value =
						device;

					option.textContent =
						device;

					serialDeviceSelect.appendChild(
						option
					);

				});

				serialDeviceSelect.style.display =
					'block';

			} else {

				if (
					noSerialDeviceMessage
				) {

					noSerialDeviceMessage.style.display =
						'block';
				}
			}

		} catch (err) {

			console.error(
				'Failed loading serial devices:',
				err
			);

		} finally {

			if (serialLoading) {
				serialLoading.style.display =
					'none';
			}
		}
	}
);

addRtspCameraButton?.addEventListener(
	'click',
	() => {

		cameraTypeSelection?.style &&
			(cameraTypeSelection.style.display =
				'none');

		addCameraForm?.style &&
			(addCameraForm.style.display =
				'block');

		serialCameraSetup?.style &&
			(serialCameraSetup.style.display =
				'none');

		rtspCameraSetup?.style &&
			(rtspCameraSetup.style.display =
				'block');

		if (serialDeviceSelect) {
			serialDeviceSelect.required =
				false;
		}

		if (rtspUrlInput) {
			rtspUrlInput.required =
				true;
		}
	}
);

// =========================
// Preview Events
// =========================
enablePreview?.addEventListener(
	'change',
	updatePreview
);

serialDeviceSelect?.addEventListener(
	'change',
	updatePreview
);

rtspUrlInput?.addEventListener(
	'input',
	schedulePreviewUpdate
);

// =========================
// Add Camera Form
// =========================
addCameraForm?.addEventListener(
	'submit',
	async function(e) {

		e.preventDefault();

		const formData =
			new FormData(addCameraForm);

		const data = {};

		formData.forEach(
			(value, key) => {

				if (value) {
					data[key] = value;
				}
			}
		);

		try {

			const response =
				await fetch(
					'/config/add-camera',
					{
						method: 'POST',
						headers: {
							'Content-Type':
								'application/json'
						},
						body: JSON.stringify(
							data
						)
					}
				);

			if (!response.ok) {

				const errorData =
					await response.json();

				throw new Error(
					errorData.detail ||
					'Failed to add camera'
				);
			}

			window.location.reload();

		} catch (err) {

			console.error(
				'Failed adding camera:',
				err
			);

			alert(err.message);

		}
	}
);

// =========================
// Modal Events
// =========================
addCameraBtn?.addEventListener(
	'click',
	function(e) {

		e.preventDefault();

		if (addCameraModalOverlay) {
			addCameraModalOverlay.style.display =
				'flex';
		}
	}
);

const detectionButton = document.getElementById('detectionBtn');

detectionButton?.addEventListener(
	'click',
	function(e) {

		e.preventDefault();
		window.location.href = '/index';
	}
);

addFirstCameraBtn?.addEventListener(
	'click',
	function(e) {

		e.preventDefault();

		if (addCameraModalOverlay) {
			addCameraModalOverlay.style.display =
				'flex';
		}
	}
);

addCameraModalClose?.addEventListener(
	'click',
	closeAddCameraModal
);

addCameraModalOverlay?.addEventListener(
	'click',
	function(e) {

		if (
			e.target ===
			addCameraModalOverlay
		) {
			closeAddCameraModal();
		}
	}
);

function closeAddCameraModal() {

	if (addCameraModalOverlay) {
		addCameraModalOverlay.style.display =
			'none';
	}

	addCameraForm?.reset();

	addCameraForm?.style &&
		(addCameraForm.style.display =
			'none');

	cameraTypeSelection?.style &&
		(cameraTypeSelection.style.display =
			'flex');

	serialCameraSetup?.style &&
		(serialCameraSetup.style.display =
			'none');

	rtspCameraSetup?.style &&
		(rtspCameraSetup.style.display =
			'none');

	if (serialDeviceSelect) {

		serialDeviceSelect.required =
			false;

		serialDeviceSelect.innerHTML =
			'';

		serialDeviceSelect.style.display =
			'none';
	}

	if (rtspUrlInput) {
		rtspUrlInput.required =
			false;
	}

	if (noSerialDeviceMessage) {
		noSerialDeviceMessage.style.display =
			'none';
	}

	if (serialLoading) {
		serialLoading.style.display =
			'none';
	}

	if (enablePreview) {
		enablePreview.checked = false;
	}

	hidePreview();

	if (previewUpdateTimeout) {
		clearTimeout(
			previewUpdateTimeout
		);
	}
}

// =========================
// Slider Events
// =========================
document
	.querySelectorAll(
		'.settings-form input[type="range"]'
	)
	.forEach(slider => {

		updateSliderFill(slider);

		slider.addEventListener(
			'input',
			() => {

				updateSliderFill(
					slider
				);

			}
		);

		slider.addEventListener(
			'change',
			function(e) {

				e.preventDefault();

				saveSetting(slider);

			}
		);
	});

document
	.querySelectorAll(
		'.control-form input[type="range"]'
	)
	.forEach(slider => {

		updateSliderFill(slider);

		slider.addEventListener(
			'input',
			() => {

				updateSliderFill(
					slider
				);

			}
		);

		slider.addEventListener(
			'change',
			function(e) {

				e.preventDefault();

				saveSetting(slider);

			}
		);
	});

document
	.querySelectorAll(
		'.control-form select'
	)
	.forEach(control => {

		control.addEventListener(
			'change',
			function(e) {

				e.preventDefault();

				saveSetting(control);

			}
		);
	});

// =========================
// Init
// =========================
(async function init() {

	console.warn('Initializing');

	try {

		const cameras =
			await getCameraList();

		if (
			Object.keys(cameras).length === 0
		) {

			const noCamera =
				document.getElementById(
					'noCamera'
				);

			if (noCamera) {
				noCamera.style.display =
					'block';
			}
		}

		Object.keys(cameras).forEach(
			camera_uuid => {

				const item =
					createDisplayItem(
						camera_uuid,
						cameras[camera_uuid]
							.nickname,
						cameras[camera_uuid]
							.source
					);

				if (item) {

					addListenerToDisplayItem(
						item,
						camera_uuid
					);
				}
			}
		);

		// Countdown settings
		try {

			const response =
				await fetch(
					'/config/get-countdown-settings'
				);

			if (response.ok) {

				const data =
					await response.json();

				const settings =
					data.settings;

				if (settings) {

					if (
						settingsCountdownAction
					) {
						console.warn(
							'Applying countdown settings:',
							settings.countdown_action
						);
						settingsCountdownAction.value =
							settings.countdown_action ||
							'none';
					}

					if (
						settingsCountdownTime
					) {

						settingsCountdownTime.value =
							settings.countdown_time ||
							0;

						updateSliderFill(
							settingsCountdownTime
						);
					}

					if (
						settingsCountdownControl
					) {

						settingsCountdownControl.value =
							settings.countdown_control ||
							'none';
					}
				}
			}

		} catch (err) {

			console.error(
				'Countdown settings error:',
				err
			);

		}

		cameraItems =
			document.querySelectorAll(
				'.camera-row'
			);

		if (
			cameraItems.length > 0
		) {

			const firstCameraId =
				cameraItems[0].dataset
					.cameraId;

			if (firstCameraId) {
				cameraItems[0].click();
			}

		} else {

			if (
				addCameraModalOverlay
			) {

				addCameraModalOverlay.style.display =
					'flex';
			}
		}

	} catch (err) {

		console.error(
			'Initialization failed:',
			err
		);

	}
})();
