// =========================
// Templates
// =========================
const camTemplate = document.getElementById("camera-template");
//const vidTemplate = document.getElementById("video-template");
//const btnTemplate = document.getElementById("button-template");
const grid = document.getElementById("grid");

// =========================
// Globals
// =========================
let cameraItems;
let cameraUUID;


const camVideoPreview = document.getElementById('videoPreview');
const loadingOverlay = document.getElementById('loadingOverlay');
//const cameraItems = document.querySelectorAll('.camera-items');

const settingsCameraUUID = document.getElementById('camera_uuid');
const settingsSensitivity = document.getElementById('sensitivity');
const settingsSensitivityLabel = document.getElementById('sensitivity_val');
const settingsBrightness = document.getElementById('brightness');
const settingsBrightnessLabel = document.getElementById('brightness_val');
const settingsContrast = document.getElementById('contrast');
const settingsContrastLabel = document.getElementById('contrast_val');
const settingsFocus = document.getElementById('focus');
const settingsFocusLabel = document.getElementById('focus_val');
const settingsMajorityVoteThreshold = document.getElementById('majority_vote_threshold');
const settingsMajorityVoteThresholdLabel = document.getElementById('majority_vote_threshold_val');
const settingsMajorityVoteWindow = document.getElementById('majority_vote_window');
const settingsMajorityVoteWindowLabel = document.getElementById('majority_vote_window_val');

//COUNDOWN ELEMENTS
const settingsCountdownAction = document.getElementById('countdown_action');
const settingsCountdownTime = document.getElementById('countdown_time');
const settingsCountdownTimeLabel = document.getElementById('countdown_time_val');
const settingsCountdownControl = document.getElementById('countdown_control');


const addCameraModalOverlay = document.getElementById('addCameraModalOverlay');
const addCameraModalClose = document.getElementById('addCameraModalClose');
const addCameraBtn = document.getElementById('addCameraBtn');
const addFirstCameraBtn = document.getElementById('addFirstCameraBtn');




// =========================
// API
// =========================
async function getCameraList() {
console.warn('Fetching camera list');
  try {
	const res = await fetch("/config/get-camera-list");
	if (!res.ok) return [];
	const data = await res.json();
	console.warn('Camera list response:', data.camera_list);
	return data.camera_list || {}; // Expecting an object with camera UUIDs as keys and their details as values
  } catch {
	return {};
  }
}


function createDisplayItem(camId, nickname, source) {
  console.warn('Creating display item for camera:', camId);

  const row = document.createElement("div");
  row.className = "camera-row";

  // Clone template
  const camFrag = camTemplate.content.cloneNode(true);
  const card = camFrag.firstElementChild;

  // Attach camera id
  card.dataset.cameraId = camId;

  // 🔑 Update template content
  const nicknameEl = camFrag.querySelector('.nickname');
  const sourceEl = camFrag.querySelector('.source');

  if (nicknameEl) nicknameEl.textContent = nickname;
  if (sourceEl) sourceEl.textContent = source;

  // Append to row
  row.appendChild(card);

  // Append to grid
  const newRow = document.getElementById("grid").appendChild(row);

  return newRow;

  //SRS update item display

  /*
  // Button
  const button = card.querySelector("button");
  button.addEventListener("click", () => {
	//alert(`Camera ${camId} says ${btnState}`);
	const btnState = button.textContent;
	let isStart = false;
	if (btnState === BTNSTART){
	  isStart = true;
	}
	sendDetectionRequest(isStart,card,camId);
	*/
}


// =========================
// Init
// =========================
(async function init() {
  console.warn('Initializing');

  const cameras = await getCameraList();

	/*
  if (cameras.length === 0) {
	document.getElementById("noCamera").style.display = "block";
  }
	*/


	//create a row for each camera
	Object.keys(cameras).forEach(camera_uuid => {
  		console.log(camera_uuid, cameras[camera_uuid]);
		const item = createDisplayItem(camera_uuid, cameras[camera_uuid].nickname, cameras[camera_uuid].source);
		addListenerToDisplayItem(item, camera_uuid);
		});


	//Get a list of all camera rows
	cameraItems = document.querySelectorAll('.camera-items');
	console.warn('Num of camera items ', cameraItems.length)

	; // uses cameraItems

	if (cameraItems.length > 0) {
		const cameraId = cameraItems[0].dataset.cameraId;
		if (cameraId) {
			console.warn('clicked ', cameraId)
			cameraItems[0].click();
		}
	}else {
			if (addCameraModalOverlay) {
				addCameraModalOverlay.style.display = 'flex';
			}
	}

	//update_cameras();  // uses cameraItems

})();


// Update each camera item with the latest data
function xupdate_cameras () {
	cameraItems.forEach(item => {
		const camId = item.dataset.cameraId;
		fetchAndUpdateCameraSettings(camId);
	});
}


camVideoPreview.onload = () => {
	loadingOverlay.style.display = 'none';
};

camVideoPreview.onerror = () => {
	loadingOverlay.style.display = 'none';
	console.error("Failed to load camera feed.");
};



function changeLiveCameraFeed(cameraUUID) {
	loadingOverlay.style.display = 'flex';
	camVideoPreview.src = `/camera/snapshot/${cameraUUID}`;
	//SRS
	//camVideoPreview.src = `/camera/feed/${cameraUUID}`;
}

function initializeCountdownSettings(d) {
	console.warn('initialize coundown settings')
	settingsCountdownAction.value = d.countdown_action;
	console.warn('Countdown Action Value:', d.countdown_action);

	settingsCountdownTimeLabel.textContent = d.countdown_time;
	settingsCountdownTime.value = d.countdown_time;
	console.warn('Countdown Time Value:', d.countdown_time);
	updateSliderFill(settingsCountdownTime);

	settingsCountdownControl.value = d.countdown_control;
	console.warn('Countdown Control Value:', d.countdown_control);

}

function updateSelectedCameraSettings(d) {
	console.warn('updateSelectedCameraSettings: ==>', d.camera_uuid);

	settingsCameraUUID.value = d.camera_uuid;
	settingsSensitivityLabel.textContent = d.sensitivity;
	settingsSensitivity.value = d.sensitivity;
	updateSliderFill(settingsSensitivity);
	settingsBrightnessLabel.textContent = d.brightness;
	settingsBrightness.value = d.brightness;
	updateSliderFill(settingsBrightness);
	settingsContrastLabel.textContent = d.contrast;
	settingsContrast.value = d.contrast;
	updateSliderFill(settingsContrast);
	settingsFocusLabel.textContent = d.focus;
	settingsFocus.value = d.focus;
	updateSliderFill(settingsFocus);
	settingsMajorityVoteThresholdLabel.textContent = d.majority_vote_threshold;
	settingsMajorityVoteThreshold.value = d.majority_vote_threshold;
	updateSliderFill(settingsMajorityVoteThreshold);
	settingsMajorityVoteWindowLabel.textContent = d.majority_vote_window;
	settingsMajorityVoteWindow.value = d.majority_vote_window;
	updateSliderFill(settingsMajorityVoteWindow);
}


function removeCamera(cameraUUID) {
	if (!cameraUUID) {
		console.warn('Cannot remove camera: invalid camera UUID provided.');
		return;
	}
	if (!confirm('Are you sure you want to remove this camera?')) {
		return;
	}
	fetch('/config/remove-camera', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ camera_uuid: cameraUUID })
	})
	.then(response => {
		if (!response.ok) {
			return response.json().then(errData => {
				throw new Error(`Failed to remove camera ${cameraUUID}: ${errData.detail || response.statusText}`);
			});
		}
		return response.json();
	})
	.then(() => {
		const cameraItem = document.querySelector(`.camera-items[data-camera-id="${cameraUUID}"]`);
		if (cameraItem) {
			cameraItem.remove();
		}
		// If deleted camera is current camera
		if (window.cameraUUID === cameraUUID) {
			const firstCamera = document.querySelector('.camera-items');
			if (firstCamera) {
				firstCamera.click();
			} else {
				window.location.reload();
			}
		}
		const remainingCameras = document.querySelectorAll('.camera-items');
		if (remainingCameras.length === 0) {
			if (addCameraModalOverlay) {
				addCameraModalOverlay.style.display = 'flex';
			}
		}
	})
	.catch(error => {
		console.error(`Error removing camera ${cameraUUID}:`, error.message);
		alert(`Failed to remove camera: ${error.message}`);
	});
}


function fetchAndUpdateCameraSettings(cameraUUID) {
	console.warn('Fetching metrics for camera:', cameraUUID);
	if (!cameraUUID) {
		console.warn('Cannot fetch metrics: invalid camera UUID provided:', cameraUUID);
		return;
	}
	fetch(`/config/get-camera-setting`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ camera_uuid: cameraUUID })
	})
	.then(response => {
		if (!response.ok) {
			return response.json().then(errData => {
				throw new Error(`Failed to fetch camera state for camera ${cameraUUID}: ${errData.detail || response.statusText}`);
			}).catch(() => {
				throw new Error(`Failed to fetch camera state for camera ${cameraUUID}: ${response.statusText}`);
			});
		}
		return response.json();
	})
	.then(data => {
		console.warn('control ==>', data.countdown_control);
		console.warn(data);
		const metricsData = {
			camera_uuid: cameraUUID,
			brightness: data.brightness,
			contrast: data.contrast,
			focus: data.focus,
			sensitivity: data.sensitivity,
			majority_vote_threshold: data.majority_vote_threshold,
			majority_vote_window: data.majority_vote_window,
		};
		updateSelectedCameraSettings(metricsData);
	})
	.catch(error => {
		console.error(`Error fetching metrics for camera ${cameraUUID}:`, error.message);
	});
}

function xgetCameraState(cameraUUID) {
	console.warn('Fetching metrics for camera:', cameraUUID);
	if (!cameraUUID) {
		console.warn('Cannot fetch metrics: invalid camera UUID provided:', cameraUUID);
		return;
	}
	fetch(`/config/get-camera-state`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ camera_uuid: cameraUUID })
	})
	.then(response => {
		if (!response.ok) {
			return response.json().then(errData => {
				throw new Error(`Failed to fetch camera state for camera ${cameraUUID}: ${errData.detail || response.statusText}`);
			}).catch(() => {
				throw new Error(`Failed to fetch camera state for camera ${cameraUUID}: ${response.statusText}`);
			});
		}
		return response.json();
	})
	.then(data => {
		console.warn('control ==>', data.countdown_control);
		console.warn(data);
		const metricsData = {
			camera_uuid: cameraUUID,
			start_time: data.start_time,
			last_result: data.last_result,
			last_time: data.last_time,
			total_detections: data.detection_times ? data.detection_times.length : 0,
			frame_rate: data.frame_rate,
			live_detection_running: data.live_detection_running,
			brightness: data.brightness,
			contrast: data.contrast,
			focus: data.focus,
			sensitivity: data.sensitivity,
			majority_vote_threshold: data.majority_vote_threshold,
			majority_vote_window: data.majority_vote_window,
			printer_id: data.printer_id,
			printer_config: data.printer_config,
			countdown_action: data.countdown_action,
			countdown_time: data.countdown_time,
			countdown_control: data.countdown_control
		};
		updateSelectedCameraSettings(metricsData);
	})
	.catch(error => {
		console.error(`Error fetching metrics for camera ${cameraUUID}:`, error.message);
		const emptyMetrics = {
			camera_uuid: cameraUUID,
			start_time: null,
			last_result: '-',
			last_time: null,
			total_detections: 0,
			frame_rate: null,
			live_detection_running: false
		};
		//updateSelectedCameraSettings(emptyMetrics);
	});
}

function addListenerToDisplayItem(item, cameraId) {
	item.addEventListener('click', function() {
		//toggle the selection
		cameraItems.forEach(i => i.classList.remove('selected'));
		this.classList.add('selected');

		//now update the display
		cameraUUID = cameraId; // Global identifier for currently selected camera

		settingsCameraUUID.value = cameraId; // set the form uuid to report the current camera
		fetchAndUpdateCameraSettings(cameraId);
		//SRS
		//const nickname = this.querySelector('.camera-header span:first-child').textContent;
		//changeLiveCameraFeed(nickname);
		changeLiveCameraFeed(cameraId);
	});
	
	const removeButton = item.querySelector('.remove-camera-btn');
	removeButton.addEventListener('click', function(event) {
		event.stopPropagation();
		const cameraId = item.dataset.cameraId;
		removeCamera(cameraId);
	});

}


document.addEventListener('DOMContentLoaded', function() {
	/*
	console.warn('DOM' , cameraItems.length);
	
	if (cameraItems.length > 0) {
		const cameraId = cameraItems[0].dataset.cameraId;
		if (cameraId) {
			console.warn('clicked ', cameraID)
			cameraItems[0].click();
		}
	}else {
			if (addCameraModalOverlay) {
				addCameraModalOverlay.style.display = 'flex';
			}
		}
	*/
});

addCameraBtn?.addEventListener('click', function(e) {
	e.preventDefault();
	addCameraModalOverlay.style.display = 'flex';
});

addFirstCameraBtn?.addEventListener('click', function(e) {
	e.preventDefault();
	addCameraModalOverlay.style.display = 'flex';
});


function updateSliderFill(slider) {
	const min = slider.min || 0;
	const max = slider.max || 100;
	const value = slider.value;
	const percentage = ((value - min) / (max - min)) * 100;
	slider.style.setProperty('--value', `${percentage}%`);
	const valueSpan = document.getElementById(`${slider.id}_val`);
	if (valueSpan) {
		valueSpan.textContent = value;
	}
}


function saveSetting(slider) {
	const settingsForm = slider.closest('form');
	console.warn('form action is ', settingsForm ? settingsForm.action : 'N/A');
	if (!settingsForm) return;
	const formData = new FormData(settingsForm);

	// 🔥 Ensure current field is always included
	formData.set(slider.name, slider.value);

	const setting = slider.name;
	const value = slider.value;
	console.warn(`Saving setting ${setting} with value ${value}`);
	for (let [key, value] of formData.entries()) {
	console.log(key, value);
	}

	fetch(settingsForm.action, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/x-www-form-urlencoded',
		},
		body: new URLSearchParams(formData)
	})
	.then(response => {
		if (response.ok) {
			const valueSpan = document.getElementById(`${slider.id}_val`);
			if (valueSpan) {
				valueSpan.textContent = value;
			}
		} else {
			console.error(`Failed to update setting ${setting}`);
		}
	})
	.catch(error => {
		console.error(`Error saving setting ${setting}:`, error);
	});
}

document.querySelectorAll('.settings-form input[type="range"]').forEach(slider => {
	console.warn('adding slider', slider);
	updateSliderFill(slider);
	slider.addEventListener('input', () => {
		updateSliderFill(slider);
	});
	slider.addEventListener('change', (e) => {
		console.warn('settings event');
		e.preventDefault();
		updateSliderFill(slider);
		saveSetting(slider);
	});
});

document.querySelectorAll('.control-form input[type="range"').forEach(slider => {
	console.warn('adding slider for control', slider);
	updateSliderFill(slider);
	slider.addEventListener('input', () => {
		updateSliderFill(slider);
	});
	slider.addEventListener('change', (e) => {
		console.warn('settings event');
		e.preventDefault();
		updateSliderFill(slider);
		saveSetting(slider);
	});
});

document.querySelectorAll('.control-form select').forEach(control => {
	console.warn('adding control', control);
	control.addEventListener('input', (e) => {
		console.warn('input event');
		saveSetting(control);
	});
	control.addEventListener('change', (e) => {
		console.warn('control event');
		e.preventDefault();
		saveSetting(control);
	});
});

function submitControlForm (){
	console.warn('submitting form');
	document.querySelector('.control-form select')
	.dispatchEvent(new Event('change', { bubbles: true }));
}


/*
document.querySelector('.settings-form')?.addEventListener('submit', (e) => {
	e.preventDefault();
});
*/
/*
document.querySelector('.countrol-form')?.addEventListener('submit', (e) => {
	e.preventDefault();
	console.warn('form event');
});
*/

function updateFeedSliderFill(slider) {
	const min = slider.min || 0;
	const max = slider.max || 100;
	const value = slider.value;
	const percentage = ((value - min) / (max - min)) * 100;
	slider.style.setProperty('--value', `${percentage}%`);
	const valueSpan = document.getElementById(`${slider.id}_val`);
	if (valueSpan) {
		valueSpan.textContent = value;
	}
}

/*SRS - Keep feed settings for now - not convinced of utility*/

function saveFeedSetting(slider) {
	const setting = slider.name;
	const value = parseInt(slider.value);
	const valueSpan = document.getElementById(`${slider.id}_val`);
	if (valueSpan) {
		valueSpan.textContent = value;
	}
	if (setting === 'detectionInterval') {
		const detectionsPerSecond = Math.round(1000 / value);
		const dpsSlider = document.getElementById('detectionsPerSecond');
		const dpsSpan = document.getElementById('detectionsPerSecond_val');
		if (dpsSlider && dpsSpan) {
			dpsSlider.value = detectionsPerSecond;
			dpsSpan.textContent = detectionsPerSecond;
			updateFeedSliderFill(dpsSlider);
		}
	} else if (setting === 'detectionsPerSecond') {
		const detectionInterval = Math.round(1000 / value);
		const diSlider = document.getElementById('detectionInterval');
		const diSpan = document.getElementById('detectionInterval_val');
		if (diSlider && diSpan) {
			diSlider.value = detectionInterval;
			diSpan.textContent = detectionInterval;
			updateFeedSliderFill(diSlider);
		}
	}
	//saveFeedSettings();
}

function saveFeedSettings() {
	console.warn('Save Feed Settings');
	const settings = {
		stream_max_fps: parseInt(document.getElementById('streamMaxFps').value),
		stream_tunnel_fps: parseInt(document.getElementById('streamTunnelFps').value),
		stream_jpeg_quality: parseInt(document.getElementById('streamJpegQuality').value),
		stream_max_width: parseInt(document.getElementById('streamMaxWidth').value),
		detections_per_second: parseInt(document.getElementById('detectionsPerSecond').value),
		detection_interval_ms: parseInt(document.getElementById('detectionInterval').value),
		printer_stat_polling_rate_ms: parseInt(document.getElementById('printerStatPollingRate').value),
		min_sse_dispatch_delay_ms: parseInt(document.getElementById('minSseDispatchDelay').value)
	};
	fetch('/save-feed-settings', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
		},
		body: JSON.stringify(settings)
	})
	.then(response => {
		if (!response.ok) {
			return response.json().then(errData => {
				throw new Error(errData.detail || 'Failed to save feed settings');
			});
		}
		return response.json();
	})
	.then(data => {
		console.log('Feed settings saved successfully:', data);
	})
	.catch(error => {
		console.error('Error saving feed settings:', error);
	});
}

function initializeFeedSettings() {
	loadFeedSettings().then(() => {
		document.querySelectorAll('.feed-setting-item input[type="range"]').forEach(slider => {
			updateFeedSliderFill(slider);
			slider.addEventListener('input', () => {
				updateFeedSliderFill(slider);
			});
			slider.addEventListener('change', (e) => {
				e.preventDefault();
				updateFeedSliderFill(slider);
				saveFeedSetting(slider);
			});
		});
	});
}

function loadFeedSettings() {
	return fetch('/get-feed-settings', {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
		}
	})
	.then(response => {
		if (!response.ok) {
			return response.json().then(errData => {
				throw new Error(errData.detail || 'Failed to load feed settings');
			});
		}
		return response.json();
	})
	.then(data => {
		if (data.success && data.settings) {
			const settings = data.settings;
			updateSliderValue('streamMaxFps', settings.stream_max_fps);
			updateSliderValue('streamTunnelFps', settings.stream_tunnel_fps);
			updateSliderValue('streamJpegQuality', settings.stream_jpeg_quality);
			updateSliderValue('streamMaxWidth', settings.stream_max_width);
			updateSliderValue('detectionsPerSecond', settings.detections_per_second);
			updateSliderValue('detectionInterval', settings.detection_interval_ms);
			updateSliderValue('printerStatPollingRate', settings.printer_stat_polling_rate_ms);
			updateSliderValue('minSseDispatchDelay', settings.min_sse_dispatch_delay_ms);
		}
	})
	.catch(error => {
		console.error('Error loading feed settings:', error);
	});
}

function updateSliderValue(sliderId, value) {
	const slider = document.getElementById(sliderId);
	const valueSpan = document.getElementById(`${sliderId}_val`);
	if (slider && valueSpan) {
		slider.value = value;
		valueSpan.textContent = value;
		updateFeedSliderFill(slider);
	}
}


setupModalClose?.addEventListener('click', function() {
	setupModalOverlay.style.display = 'none';
	document.body.style.overflow = '';
});


addCameraModalClose?.addEventListener('click', function() {
	if (addCameraModalOverlay) {
		addCameraModalOverlay.style.display = 'none';
	}
});

addCameraModalOverlay?.addEventListener('click', function(e) {
	if (e.target === addCameraModalOverlay) {
		addCameraModalOverlay.style.display = 'none';
	}
});

const addSerialCameraButton = document.getElementById('addSerialCameraButton');
const addRtspCameraButton = document.getElementById('addRtspCameraButton');
const cameraTypeSelection = document.getElementById('cameraTypeSelection');
const addCameraForm = document.getElementById('addCameraForm');
const serialCameraSetup = document.getElementById('serialCameraSetup');
const rtspCameraSetup = document.getElementById('rtspCameraSetup');
const serialDeviceSelect = document.getElementById('serialDevice');
const rtspUrlInput = document.getElementById('rtspUrl');
const serialLoading = document.getElementById('serialLoading');
const noSerialDeviceMessage = document.getElementById('noSerialDeviceMessage');

const enablePreview = document.getElementById('enablePreview');
const cameraPreviewContainer = document.getElementById('cameraPreviewContainer');
const cameraPreviewImage = document.getElementById('cameraPreviewImage');
const cameraPreviewLoading = document.getElementById('cameraPreviewLoading');
const cameraPreviewError = document.getElementById('cameraPreviewError');

let previewUpdateTimeout;

function showPreviewLoading() {
	cameraPreviewImage.style.display = 'none';
	cameraPreviewError.style.display = 'none';
	cameraPreviewLoading.style.display = 'flex';
}

function showPreviewError() {
	cameraPreviewImage.style.display = 'none';
	cameraPreviewLoading.style.display = 'none';
	cameraPreviewError.style.display = 'flex';
}

function showPreviewImage(src) {
	cameraPreviewLoading.style.display = 'none';
	cameraPreviewError.style.display = 'none';
	cameraPreviewImage.src = src;
	cameraPreviewImage.style.display = 'block';
}

function hidePreview() {
	cameraPreviewContainer.style.display = 'none';
	cameraPreviewImage.style.display = 'none';
	cameraPreviewLoading.style.display = 'none';
	cameraPreviewError.style.display = 'none';
}

function updatePreview() {
	if (!enablePreview.checked) {
		hidePreview();
		return;
	}
	
	cameraPreviewContainer.style.display = 'block';
	let source = '';
	if (serialCameraSetup.style.display !== 'none' && serialDeviceSelect.value) {
		source = serialDeviceSelect.value;
	} else if (rtspCameraSetup.style.display !== 'none' && rtspUrlInput.value) {
		source = rtspUrlInput.value;
	}
	if (!source) {
		showPreviewError();
		return;
	}
	showPreviewLoading();
	const previewUrl = `/camera/preview?source=${encodeURIComponent(source)}`;
	const img = new Image();
	img.onload = function() {
		showPreviewImage(previewUrl);
	};
	img.onerror = function() {
		showPreviewError();
	};
	img.src = previewUrl;
}

function schedulePreviewUpdate() {
	if (previewUpdateTimeout) {
		clearTimeout(previewUpdateTimeout);
	}
	previewUpdateTimeout = setTimeout(updatePreview, 1000);
}

addSerialCameraButton?.addEventListener('click', async () => {
	cameraTypeSelection.style.display = 'none';
	addCameraForm.style.display = 'block';
	serialCameraSetup.style.display = 'block';
	rtspCameraSetup.style.display = 'none';
	rtspUrlInput.required = false;
	serialDeviceSelect.required = true;
	serialLoading.style.display = 'block';
	serialDeviceSelect.style.display = 'none';
	noSerialDeviceMessage.style.display = 'none';

	try {
		const response = await fetch('/camera/serial_devices');
		const devices = await response.json();
		serialDeviceSelect.innerHTML = '';
		if (devices.length > 0) {
			const defaultOption = document.createElement('option');
			defaultOption.value = '';
			defaultOption.textContent = 'Select a serial device';
			defaultOption.disabled = true;
			defaultOption.selected = true;
			serialDeviceSelect.appendChild(defaultOption);
			
			devices.forEach(device => {
				const option = document.createElement('option');
				option.value = device;
				option.textContent = device;
				serialDeviceSelect.appendChild(option);
			});
			serialDeviceSelect.style.display = 'block';
			serialDeviceSelect.selectedIndex = 0;
			const changeEvent = new Event('change', { bubbles: true });
			serialDeviceSelect.dispatchEvent(changeEvent);
		} else {
			noSerialDeviceMessage.style.display = 'block';
			serialDeviceSelect.required = false;
		}
	} catch (error) {
		console.error('Error fetching serial devices:', error);
		noSerialDeviceMessage.textContent = 'Error fetching devices.';
		noSerialDeviceMessage.style.display = 'block';
	} finally {
		serialLoading.style.display = 'none';
	}
});

addRtspCameraButton?.addEventListener('click', () => {
	cameraTypeSelection.style.display = 'none';
	addCameraForm.style.display = 'block';
	serialCameraSetup.style.display = 'none';
	rtspCameraSetup.style.display = 'block';
	serialDeviceSelect.required = false;
	rtspUrlInput.required = true;
});

enablePreview?.addEventListener('change', updatePreview);

serialDeviceSelect?.addEventListener('change', () => {
	if (enablePreview.checked) {
		updatePreview();
	}
});

rtspUrlInput?.addEventListener('input', () => {
	if (enablePreview.checked) {
		schedulePreviewUpdate();
	}
});

addCameraForm?.addEventListener('submit', async (e) => {
	e.preventDefault();
	const formData = new FormData(addCameraForm);
	const data = {};
	formData.forEach((value, key) => {
		if (value) {
			data[key] = value;
		}
	});

	try {
		const response = await fetch('/config/add-camera', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify(data),
		});

		if (response.ok) {
			addCameraModalOverlay.style.display = 'none';
			addCameraForm.reset();
			addCameraForm.style.display = 'none';
			cameraTypeSelection.style.display = 'flex';
			location.reload();
		} else {
			const errorData = await response.json();
			alert(`Error: ${errorData.detail}`);
		}
	} catch (error) {
		console.error('Error adding camera:', error);
		alert('An error occurred while adding the camera.');
	}
});

addCameraModalClose?.addEventListener('click', function() {
	addCameraModalOverlay.style.display = 'none';
	addCameraForm.reset();
	addCameraForm.style.display = 'none';
	cameraTypeSelection.style.display = 'flex';
	serialCameraSetup.style.display = 'none';
	rtspCameraSetup.style.display = 'none';
	serialDeviceSelect.required = false;
	rtspUrlInput.required = false;
	serialDeviceSelect.innerHTML = '';
	serialDeviceSelect.style.display = 'none';
	noSerialDeviceMessage.style.display = 'none';
	serialLoading.style.display = 'none';
	enablePreview.checked = false;
	hidePreview();
	if (previewUpdateTimeout) {
		clearTimeout(previewUpdateTimeout);
	}
});

