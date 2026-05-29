// =========================
// Templates
// =========================
const camTemplate = document.getElementById("camera-template");
const vidTemplate = document.getElementById("video-template");
const btnTemplate = document.getElementById("button-template");
const grid = document.getElementById("grid");

// =========================
// Globals
// =========================
let cameraItems = [];
let detectionStatus;

const BTNSTOP = 'Stop Detection';
const BTNSTART = 'Start Detection';

let defectActive = false;

let ignoreBtn;
let pauseBtn;
let cancelBtn;
let countdownTimer;
let flashButton;

// =========================
// Snapshot Queue
// =========================
const MAX_CONCURRENT_SNAPSHOTS = 2;

let activeRequests = 0;
const queue = [];

// =========================
// Queue Helpers
// =========================
function enqueue(task) {

  queue.push(task);
  processQueue();

}

function processQueue() {

  if (activeRequests >= MAX_CONCURRENT_SNAPSHOTS) {
    return;
  }

  if (queue.length === 0) {
    return;
  }

  const task = queue.shift();

  activeRequests++;

  task()
    .catch(err => console.error("Snapshot error:", err))
    .finally(() => {
      activeRequests--;
      processQueue();
    });
}

// =========================
// Snapshot Loop
// =========================
function startSnapshots(img, camId) {

  let stopped = false;

  async function loop() {

    if (stopped) return;

    if (!document.hidden) {

      enqueue(async () => {
        img.src = `/camera/snapshot/${camId}?t=${Date.now()}`;
      });

    }

    setTimeout(loop, 2000 + Math.random() * 500);
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loop();
  });

  loop();

  return () => {
    stopped = true;
  };
}

// =========================
// No Cameras Warning (Modal)
// =========================
function showNoCamerasWarning() {

  const modal =
    document.getElementById('noCamera');

  const closeBtn =
    document.getElementById('closeModal');

  const settingsBtn =
    document.getElementById('openSettingsBtn');

  if (!modal) return;

  modal.style.display = 'flex';

  if (closeBtn) {
    closeBtn.onclick = () => {
      modal.style.display = 'none';
    };
  }

  if (settingsBtn) {
    settingsBtn.onclick = () => {
      const url = `${window.location.origin}/settings`; //do not add html
      window.open(url, '_blank');
    };
  }
}

// =========================
// Settings Tile (GRID BUTTON)
// =========================
function addSettingsTile() {

  if (!grid) return;

  const wrapper = document.createElement('div');
  wrapper.className = 'settings-tile';

  const button = document.createElement('button');
  button.className = 'settings-button';
  button.textContent = 'Open Settings';

  button.addEventListener('click', () => {
    const url = `${window.location.origin}/settings`; // Do not add html
    window.open(url, '_blank');
  });

  wrapper.appendChild(button);
  grid.appendChild(wrapper);
}

// =========================
// Create UI
// =========================
function createTopRowButtons() {

  if (!btnTemplate || !grid) return;

  const row = document.createElement("div");
  row.className = "top-controls";

  const btnFrag = btnTemplate.content.cloneNode(true);
  const btn = btnFrag.firstElementChild;

  if (!btn) return;

  ignoreBtn = btn.querySelector(".btn-ignore");
  pauseBtn = btn.querySelector(".btn-pause");
  cancelBtn = btn.querySelector(".btn-cancel");
  countdownTimer = btn.querySelector(".countdown-timer");

  // Ignore
  if (ignoreBtn) {
    ignoreBtn.addEventListener("click", () => {
      executeCountdownAction('ignore');
    });
  }

  // Pause / Resume
  if (pauseBtn) {
    pauseBtn.addEventListener("click", () => {

      if (pauseBtn.textContent === 'Resume') {

        if (confirm('Resume the print?')) {
          executeCountdownAction('resume_print');
        }

      } else {

        if (confirm('Pause the print?')) {
          executeCountdownAction('pause_print');
        }

      }
    });
  }

  // Cancel
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      if (confirm('Cancel the print?')) {
        executeCountdownAction('cancel_print');
      }
    });
  }

  row.appendChild(btn);
  grid.appendChild(row);
}

// =========================
// Create Camera Display
// =========================
function createDisplayItem(camId, nickname) {

  const row = document.createElement("div");
  row.className = "camera-row";

  const camFrag = camTemplate.content.cloneNode(true);
  const card = camFrag.firstElementChild;

  if (!card) return null;

  card.dataset.cameraId = camId;
  card.classList.add("camera-card");

  const nicknameEl = card.querySelector('.nickname');
  if (nicknameEl) nicknameEl.textContent = nickname;

  const button = card.querySelector(".start-stop-camera-btn");

  if (button) {
    button.addEventListener("click", () => {
      const isStart = button.textContent === BTNSTART;
      sendDetectionRequest(isStart, card, camId);
    });
  }

  row.appendChild(card);

  const vidFrag = vidTemplate.content.cloneNode(true);
  const video = vidFrag.firstElementChild;

  if (video) {

    const img = video.querySelector("img");

    if (img) {
      startSnapshots(img, camId);
    }

    row.appendChild(video);
  }

  grid.appendChild(row);

  return card;
}

// =========================
// API
// =========================
async function getCameraList() {

  try {
    const res = await fetch("/config/get-camera-list");
    if (!res.ok) return [];
    const data = await res.json();
    return data.camera_list || [];
  } catch (err) {
    console.error(err);
    return [];
  }
}

// =========================
// Update Camera State
// =========================
async function updateDisplayItem(item, cameraUUID) {

  try {

    const response = await fetch(`/config/get-camera-state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_uuid: cameraUUID })
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();

    updateCameraDisplay(item, {
      last_result: data.last_result,
      last_time: data.last_time,
      live_detection_running: data.live_detection_running,
      defect_active: data.defect_active
    });

  } catch (error) {

    console.error(error);

    updateCameraDisplay(item, {
      last_result: 'Error',
      last_time: 0,
      live_detection_running: 'Error',
      defect_active: false
    });

  }
}

// =========================
// Camera Display Update
// =========================
function updateCameraDisplay(item, d) {

  const camPred = item.querySelector(".camera-detection .detection-value");

  if (camPred) {
    camPred.textContent = defectActive ? 'DEFECT' : d.last_result;
    camPred.style.color = d.last_result === 'success' ? 'green' : 'red';
  }

  const lastUpdate = item.querySelector(".last-update .update-value");

  if (lastUpdate) {
    lastUpdate.textContent = d.last_time
      ? new Date(d.last_time * 1000).toLocaleTimeString()
      : '-';
  }

  const statusIndicator = item.querySelector('.camera-status');
  const startStopButton = item.querySelector('.start-stop-camera-btn');

  if (!statusIndicator || !startStopButton) return;

  detectionStatus = d.live_detection_running;

  if (detectionStatus === 'yes') {

    statusIndicator.textContent = 'Detecting';
    statusIndicator.style.color = '#2ecc40';

    startStopButton.textContent = BTNSTOP;
    startStopButton.style.backgroundColor = '#f30606';

  } else {

    statusIndicator.textContent = 'Inactive';
    statusIndicator.style.color = '#f30606';

    startStopButton.textContent = BTNSTART;
    startStopButton.style.backgroundColor = '#2ecc40';
  }
}

// =========================
// Execute Action
// =========================
async function executeCountdownAction(action_type) {

  try {

    const response = await fetch(`/countdown/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action_type })
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    console.warn(`Executed action: ${action_type}`);

  } catch (error) {
    console.error(error);
  }
}

// =========================
// Update Display Loop
// =========================
async function updateDisplay() {

  try {

    const countdown = await getCountdownSettings();
    const alert_status = countdown.alert_status;

    if (pauseBtn) updateControlDisplay(alert_status);

    await Promise.all(
      Array.from(cameraItems).map(item => {
        return updateDisplayItem(item, item.dataset.cameraId);
      })
    );

  } catch (err) {
    console.error("updateDisplay failed:", err);
  }
}

// =========================
// Init
// =========================
(async function init() {

  const cameras = await getCameraList();

  if (!cameras || Object.keys(cameras).length === 0) {
    showNoCamerasWarning();
    return;
  }

  createTopRowButtons();

  Object.keys(cameras).forEach(uuid => {
    createDisplayItem(uuid, cameras[uuid].nickname);
  });

  cameraItems = document.querySelectorAll('.camera-card');

  await updateDisplay();

  // 👇 ADD SETTINGS BUTTON AFTER ALL CAMERAS
  addSettingsTile();

  setInterval(() => {
    updateDisplay().catch(console.error);
  }, 5000);

})();