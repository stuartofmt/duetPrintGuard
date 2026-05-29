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

let topControls;
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

function enqueue(task) {
  queue.push(task);
  processQueue();
}

function processQueue() {
  if (activeRequests >= MAX_CONCURRENT_SNAPSHOTS) return;
  if (queue.length === 0) return;

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
    if (!document.hidden) {
      loop();
    }
  });

  loop();

  return () => {
    stopped = true;
  };
}

// =========================
// Create UI
// =========================
function createTopRowButtons() {

  const row = document.createElement("div");
  row.className = "top-controls";

  const btnFrag = btnTemplate.content.cloneNode(true);
  const btn = btnFrag.firstElementChild;

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

  // Pause
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

  // Card
  const camFrag = camTemplate.content.cloneNode(true);
  const card = camFrag.firstElementChild;

  if (!card) {
    console.error("Camera template invalid");
    return null;
  }

  card.dataset.cameraId = camId;

  // Ensure class exists
  card.classList.add("camera-card");

  // Nickname
  const nicknameEl = card.querySelector('.nickname');

  if (nicknameEl) {
    nicknameEl.textContent = nickname;
  }

  // Button
  const button = card.querySelector(".start-stop-camera-btn");

  if (button) {

    button.addEventListener("click", () => {

      const isStart = button.textContent === BTNSTART;

      sendDetectionRequest(isStart, card, camId);

    });

  }

  row.appendChild(card);


  // Video
  const vidFrag = vidTemplate.content.cloneNode(true);
  const video = vidFrag.firstElementChild;

  if (video) {

    video.dataset.cameraId = camId;

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

  console.warn('Fetching camera list');

  try {

    const res = await fetch("/config/get-camera-list");

    if (!res.ok) {
      return [];
    }

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
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        camera_uuid: cameraUUID
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    const camData = {
      last_result: data.last_result,
      last_time: data.last_time,
      live_detection_running: data.live_detection_running,
      defect_active: data.defect_active
    };

    updateCameraDisplay(item, camData);

  } catch (error) {

    console.error(`Error fetching state for ${cameraUUID}:`, error);

    updateCameraDisplay(item, {
      last_result: 'Error',
      last_time: 0,
      live_detection_running: 'Error',
      defect_active: false
    });

  }
}

// =========================
// Control Display
// =========================
function updateControlDisplay(alert_status) {

  if (!pauseBtn) return;

  if (alert_status === 'paused') {

    pauseBtn.textContent = 'Resume';
    pauseBtn.style.backgroundColor = '#38e60d';

  } else {

    pauseBtn.textContent = 'Pause';
    pauseBtn.style.backgroundColor = '#e6b30d';

  }
}

// =========================
// Camera Display
// =========================
function updateCameraDisplay(item, d) {

  const camPred = item.querySelector(".camera-detection .detection-value");

  if (camPred) {

    camPred.textContent = d.last_result;

    camPred.style.color =
      d.last_result === 'success'
        ? 'green'
        : 'red';

    if (defectActive) {
      camPred.textContent = 'DEFECT';
    }

  }

  const lastUpdate =
    item.querySelector(".last-update .update-value");

  if (lastUpdate) {

    lastUpdate.textContent =
      d.last_time
        ? new Date(d.last_time * 1000).toLocaleTimeString()
        : '-';

  }

  const statusIndicator =
    item.querySelector('.camera-status');

  const startStopButton =
    item.querySelector('.start-stop-camera-btn');

  if (!statusIndicator || !startStopButton) {
    return;
  }

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
// Flash Countdown
// =========================
function flashCountdown(action) {

  flashButton = ignoreBtn;

  if (action === 'cancel_print') {
    flashButton = cancelBtn;
  }

  if (action === 'pause_print') {
    flashButton = pauseBtn;
  }

  if (!flashButton) return null;

  const currentColor =
    window.getComputedStyle(flashButton).backgroundColor;

  flashButton.style.setProperty(
    '--current-color',
    currentColor
  );

  flashButton.classList.add("flash");

  return flashButton;
}

function triggerFlash(el) {

  if (!el) return;

  el.classList.remove('flash');

  void el.offsetWidth;

  el.classList.add('flash');

  setTimeout(() => {
    el.classList.remove('flash');
  }, 600);
}

// =========================
// Detection Request
// =========================
async function sendDetectionRequest(
  isStart,
  item,
  cameraUUID
) {

  if (!cameraUUID) {
    console.warn("No camera UUID");
    return;
  }

  try {

    const response = await fetch(
      `/detect/live/${isStart ? 'start' : 'stop'}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          camera_uuid: cameraUUID
        })
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    console.warn(
      `${isStart ? 'Started' : 'Stopped'} detection`
    );

  } catch (err) {

    console.error(err);

  }
}

// =========================
// Update Display
// =========================
async function updateDisplay() {

  try {

    const countdown =
      await getCountdownSettings();

    const alert_status =
      countdown.alert_status;
    
    console.warn(`ALERT_STATUS = ${alert_status}`)

    updateControlDisplay(alert_status);

    await Promise.all(
      Array.from(cameraItems).map(item => {

        const camId =
          item.dataset.cameraId;

        return updateDisplayItem(item, camId);

      })
    );

  } catch (err) {

    console.error("updateDisplay failed:", err);

  }
}

// =========================
// Defect Raised Event
// =========================
document.addEventListener(
  'defectRaised',
  evt => {

    const {
      alert_id,
      action,
      countdown
    } = evt.detail;

    if (!defectActive && countdown > 0) {

      if (ignoreBtn) {
        ignoreBtn.style.display = "block";
      }

      if (countdownTimer) {
        countdownTimer.style.display = "block";
      }

      flashButton =
        flashCountdown(action);

    }

    if (countdown > 0) {

      defectActive = true;

      if (countdownTimer) {
        countdownTimer.textContent =
          'in ' + countdown + ' sec';
      }

    } else {

      defectActive = false;

      if (flashButton) {
        flashButton.classList.remove('flash');
      }

      if (ignoreBtn) {
        ignoreBtn.style.display = "none";
      }

      if (countdownTimer) {
        countdownTimer.style.display = "none";
      }

    }

  }
);

// =========================
// Countdown Settings
// =========================
async function getCountdownSettings() {

  try {

    const res = await fetch(
      "/config/get-countdown-settings"
    );

    if (!res.ok) {
      return {};
    }

    const data = await res.json();

    return data || {};

  } catch {

    return {
      countdown_action: null,
      countdown_time: null,
      countdown_control: null,
      alert_status: null
    };

  }
}

// =========================
// Execute Countdown Action
// =========================
async function executeCountdownAction(action_type) {

  try {

    const response = await fetch(
      `/countdown/action`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          action: action_type
        })
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    console.warn(
      `Executed action: ${action_type}`
    );

  } catch (error) {

    console.error(
      'Failed to execute action:',
      error
    );

  }
}

// =========================
// Init
// =========================
(async function init() {

  console.warn('Initializing');

  createTopRowButtons();

  const cameras = await getCameraList();

  if (cameras.length === 0) {

    const noCam =
      document.getElementById("noCamera");

    if (noCam) {
      noCam.style.display = "block";
    }

  }

  Object.keys(cameras).forEach(camera_uuid => {

    createDisplayItem(
      camera_uuid,
      cameras[camera_uuid].nickname
    );

  });

  cameraItems =
    document.querySelectorAll('.camera-card');

  await updateDisplay();

  setInterval(() => {
    updateDisplay().catch(console.error);
  }, 5000);

})();