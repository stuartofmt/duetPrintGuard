// =========================
// Settings page
// =========================
const { onMounted, reactive, ref } = Vue;

const PREVIEW_DELAY = 1000; // ms after the stream URL stops changing before the preview reloads

const countdownActions = [
	{ title: 'Ignore', value: 'ignore' },
	{ title: 'Cancel Print', value: 'cancel_print' },
	{ title: 'Pause Print', value: 'pause_print' }
];

const countdownControls = [
	{ title: 'Any', value: 'any_camera' },
	{ title: 'All', value: 'all_cameras' }
];

const isRtsp = (url) => (url || '').trim().toLowerCase().startsWith('rtsp://');
const normalise = (text) => (text || '').trim().toLowerCase();

PG.mount({
	setup() {
		const cameras = ref([]);
		const selected = ref(null);
		const snapshot = reactive({ url: '', loading: false, failed: false });
		const countdown = reactive({ countdown_action: 'ignore', countdown_time: 0, countdown_control: 'any_camera' });
		const addForm = ref(null);
		const add = reactive({
			show: false, saving: false, nickname: '', source: '', snapshot: '',
			preview: false, previewUrl: '', previewState: ''
		});
		let previewTimeout = null;

		// =========================
		// Cameras
		// =========================
		async function loadCameras() {
			let list = {};
			try {
				list = (await PG.api.get('/config/get-camera-list'))?.list || {};
			} catch (err) {
				console.error('Failed to fetch camera list:', err);
				PG.notify('Failed to load the camera list.', 'error');
			}
			cameras.value = Object.entries(list).map(([uuid, camera]) => ({
				uuid,
				nickname: camera.nickname,
				source: camera.source,
				autostart: Boolean(camera.autostart),
				majority_vote_threshold: camera.majority_vote_threshold ?? 1,
				majority_vote_window: camera.majority_vote_window ?? 1
			}));

			const stillSelected = selected.value && cameras.value.find((c) => c.uuid === selected.value.uuid);
			if (stillSelected) {
				selected.value = stillSelected;
			} else if (cameras.value.length) {
				select(cameras.value[0]);
			} else {
				selected.value = null;
				snapshot.url = '';
				openAddCamera();
			}
		}

		function select(camera) {
			if (selected.value?.uuid === camera.uuid && snapshot.url) {
				return;
			}
			selected.value = camera;
			loadSelectedSnapshot();
		}

		function loadSelectedSnapshot() {
			if (!selected.value) return;
			Object.assign(snapshot, {
				url: `/camera/snapshot/${selected.value.uuid}?t=${Date.now()}`,
				loading: true,
				failed: false
			});
		}

		async function saveAutostart(camera) {
			try {
				await PG.api.postJson('/settings/update_autostart', { camera_uuid: camera.uuid, autostart: camera.autostart });
			} catch (err) {
				camera.autostart = !camera.autostart;
				PG.notify(`Failed to update autostart: ${err.message}`, 'error');
			}
		}

		async function saveCameraSettings(camera) {
			try {
				await PG.api.postForm('/settings/save-settings', {
					camera_uuid: camera.uuid,
					majority_vote_threshold: camera.majority_vote_threshold,
					majority_vote_window: camera.majority_vote_window
				});
			} catch (err) {
				PG.notify(`Failed to save camera settings: ${err.message}`, 'error');
			}
		}

		async function removeCamera(camera) {
			if (!await PG.confirm(`Are you sure you want to remove the camera "${camera.nickname}"?`, { color: 'error' })) {
				return;
			}
			try {
				const result = await PG.api.postJson('/config/remove-camera', { camera_uuid: camera.uuid });
				if (result?.success === false) throw new Error('the camera was not found');
				PG.notify(`Removed ${camera.nickname}.`);
			} catch (err) {
				PG.notify(`Failed to remove camera: ${err.message}`, 'error');
			}
			await loadCameras();
		}

		// =========================
		// Countdown
		// =========================
		async function loadCountdown() {
			try {
				const settings = (await PG.api.get('/config/get-countdown-settings'))?.settings;
				if (settings) {
					countdown.countdown_action = settings.countdown_action || 'ignore';
					countdown.countdown_time = settings.countdown_time || 0;
					countdown.countdown_control = settings.countdown_control || 'any_camera';
				}
			} catch (err) {
				console.error('Countdown settings error:', err);
			}
		}

		async function saveCountdown() {
			try {
				await PG.api.postForm('/config/update-countdown', { ...countdown });
			} catch (err) {
				PG.notify(`Failed to save countdown settings: ${err.message}`, 'error');
			}
		}

		// =========================
		// Add camera
		// =========================
		const rules = {
			required: (v) => Boolean((v || '').trim()) || 'Required',
			uniqueNickname: (v) => !cameras.value.some((c) => normalise(c.nickname) === normalise(v))
				|| 'A camera with this nickname already exists',
			uniqueSource: (v) => !cameras.value.some((c) => normalise(c.source) === normalise(v))
				|| 'A camera with this source already exists',
			// HTTP cameras need a snapshot URL (used for detection and snapshots) - RTSP cameras do not
			snapshot: (v) => isRtsp(add.source) || Boolean((v || '').trim()) || 'Required for HTTP cameras'
		};

		function openAddCamera() {
			Object.assign(add, {
				show: true, saving: false, nickname: '', source: '', snapshot: '',
				preview: false, previewUrl: '', previewState: ''
			});
		}

		function closeAddCamera() {
			clearTimeout(previewTimeout);
			add.show = false;
			add.previewUrl = ''; // stops the preview stream
		}

		function updatePreview() {
			clearTimeout(previewTimeout);
			const source = add.source.trim();
			if (!add.preview || !source) {
				add.previewUrl = '';
				add.previewState = add.preview ? 'error' : '';
				return;
			}
			add.previewState = 'loading';
			add.previewUrl = `/camera/preview?source=${encodeURIComponent(source)}`;
		}

		function schedulePreview() {
			clearTimeout(previewTimeout);
			if (add.preview) {
				previewTimeout = setTimeout(updatePreview, PREVIEW_DELAY);
			}
		}

		async function addCamera() {
			const { valid } = await addForm.value.validate();
			if (!valid) return;

			const data = { nickname: add.nickname.trim(), source: add.source.trim() };
			if (add.snapshot.trim()) data.snapshot = add.snapshot.trim();

			add.saving = true;
			try {
				await PG.api.postJson('/config/add-camera', data);
				PG.notify(`Added ${data.nickname}.`);
				closeAddCamera();
				await loadCameras();
			} catch (err) {
				console.error('Failed adding camera:', err);
				PG.notify(err.message || 'Failed to add camera', 'error');
			} finally {
				add.saving = false;
			}
		}

		onMounted(() => {
			loadCameras();
			loadCountdown();
		});

		return {
			cameras, selected, snapshot, countdown, countdownActions, countdownControls,
			addForm, add, rules,
			select, loadSelectedSnapshot, saveAutostart, saveCameraSettings, removeCamera, saveCountdown,
			openAddCamera, closeAddCamera, updatePreview, schedulePreview, addCamera
		};
	}
});
