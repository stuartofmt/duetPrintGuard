

// =========================
// Templates
// =========================
const camTemplate = document.getElementById("camera-template");
const vidTemplate = document.getElementById("video-template");
const topbtnTemplate = document.getElementById("top-button-template");
const bottombtnTemplate = document.getElementById("bottom-button-template");
const grid = document.getElementById("grid");
const noCameraModal = document.getElementById("noCamera");
const noCameraClose = document.getElementById("closeModal");
const noCameraSettingsBtn = document.getElementById("noCameraSettingsBtn");

// =========================
// Globals
// =========================
 let cameraItems;
 let detectionStatus;
 let BTNSTOP = 'Stop Detection';
 let BTNSTART =  'Start Detection';
 let defectActive = false;
 let autostartSet = false;

 //
  let topControls;
  let ignoreBtn;
  let pauseBtn;
  let cancelBtn;
  let countdownTimer;
  let flashButton;

  let settingsBtn;
  let autostartBtn;

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
  if (activeRequests >= MAX_CONCURRENT_SNAPSHOTS || queue.length === 0) return;

  const task = queue.shift();
  activeRequests++;

  task().finally(() => {
    activeRequests--;
    processQueue();
  });
}

// =========================
// Snapshot Loop
// =========================
function startSnapshots(img, camId) {
  function loop() {
    if (document.hidden) return;

    enqueue(async () => {
      img.src = `/camera/snapshot/${camId}?t=${Date.now()}`;
    });

    setTimeout(loop, 2000 + Math.random() * 500);
  }

  loop();
}

// Modal dismiss and Settings navigation for the No Camera modal
noCameraClose?.addEventListener("click", () => {
  if (noCameraModal) noCameraModal.style.display = "none";
});

noCameraModal?.addEventListener("click", (e) => {
  if (e.target === noCameraModal) {
    noCameraModal.style.display = "none";
  }
});

noCameraSettingsBtn?.addEventListener("click", () => {
  window.location.href = "/settings";
});

// =========================
// Create UI
// =========================
function createTopRowButtons(){
  const row = document.createElement("div");
  row.className = "top-button-row";
  const btnFrag = topbtnTemplate.content.cloneNode(true);
  const btn = btnFrag.firstElementChild;

  ignoreBtn = btn.querySelector(".btn-ignore");
  pauseBtn = btn.querySelector(".btn-pause");
  cancelBtn = btn.querySelector(".btn-cancel");

  // Event for Ignore button
  ignoreBtn.addEventListener("click", () => {
    executeCountdownAction('ignore')
  });

  // Event for Pause button
  pauseBtn.addEventListener("click", () => {
    if (pauseBtn.textContent === 'Resume'){
      alert('Are you sure you want to Resume the Print?');
      executeCountdownAction('resume_print');
      pauseBtn.textContent = 'Pause';
      pauseBtn.style.backgroundColor = '#e6b30d';
    } else {
      alert('Are you sure you want to Pause the Print?');
      executeCountdownAction('pause_print')
      pauseBtn.textContent = 'Resume';
      pauseBtn.style.backgroundColor = '#38e60d';
    }

  });

  // Event for Cancel button
  cancelBtn.addEventListener("click", () => {
    alert('Are you sure you want to Cancel the Print?');
    executeCountdownAction('cancel_print')
  });

  row.appendChild(btn);
  grid.appendChild(row);

}

function createBottomRowButtons(){
  const row = document.createElement("div");
  row.className = "bottom-button-row";
  const btnFrag = bottombtnTemplate.content.cloneNode(true);
  const btn = btnFrag.firstElementChild;

  settingsBtn = btn.querySelector(".btn-settings");
  autostartBtn = btn.querySelector(".btn-autostart");
  //cancelBtn = btn.querySelector(".btn-cancel");

  // Event for setting button
  settingsBtn.addEventListener("click", () => {
    window.location.href = "/settings";
  });

  // Event for autostart button
  autostartBtn.addEventListener("click", () => {
    reenableAutoStart()
  });

  row.appendChild(btn);
  grid.appendChild(row);

}





//function createDisplayItem(camId,nickname,autostart = false) {
function createDisplayItem(camId,nickname) {
  // Wrapper (CRITICAL)
  const row = document.createElement("div");
  row.className = "camera-row";

  // Card
  const camFrag = camTemplate.content.cloneNode(true);
  const card = camFrag.firstElementChild;
  card.dataset.cameraId = camId;
  // use boolean properties for autostart state (no dataset keys)
  //card.autostart = !!autostart;
  //card.autostartPending = false;

    // 🔑 Update template content
  const nicknameEl = card.querySelector('.nickname');
  if (nicknameEl) nicknameEl.textContent = nickname;

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
  });

  // Video
  const vidFrag = vidTemplate.content.cloneNode(true);
  const video = vidFrag.firstElementChild;
  const img = video.querySelector("img");

  video.dataset.cameraId = camId;

  startSnapshots(img, camId);

  // Add click listener to open stream in new tab
  img.addEventListener("click", (event) => {

      event.preventDefault();
      window.open(`/stream/${nickname}`, '_blank');

  });

  // Assemble
  row.appendChild(card);
  row.appendChild(video);

  grid.appendChild(row);
}

function createSettingsButton() {
  const row = document.createElement("div");
  row.className = "top-controls";

  const button = document.createElement("button");
  button.className = "control btn-settings";
  button.textContent = "Settings";
  button.addEventListener("click", () => {
    window.location.href = "/settings";
  });

  row.appendChild(button);
  grid.appendChild(row);
}

function createAutostartButton() {
  const row = document.createElement("div");
  row.className = "top-controls";

  const button = document.createElement("button");
  button.className = "control btn-settings";
  button.textContent = "Reenable Autostart";
  button.addEventListener("click", () => {
    reenableAutoStart();
  });

  row.appendChild(button);
  grid.appendChild(row);
}


async function updateCameraDisplay(item, d) {

  const camPred = item.querySelector(".camera-detection .detection-value"); 
  camPred.textContent = d.last_result;
  camPred.style.color = d.last_result === 'success' ? 'green' : 'red';

  const lastUpdate = item.querySelector(".last-update .update-value")
  lastUpdate.textContent = d.last_time ? new Date(d.last_time * 1000).toLocaleTimeString() : '-';

  let statusIndicator = item.querySelector('.camera-status');
  let startStopButton = item.querySelector('.start-stop-camera-btn');
  detectionStatus = d.live_detection_running;

  if (detectionStatus === 'yes') {
      statusIndicator.textContent = `Detecting`;
      statusIndicator.style.color = '#2ecc40';
      statusIndicator.style.backgroundColor = 'transparent';
      startStopButton.textContent = BTNSTOP;
      startStopButton.style.backgroundColor = '#f30606';
      
  } else {
      statusIndicator.textContent = `Inactive`;
      statusIndicator.style.color = '#f30606';
      statusIndicator.style.backgroundColor = 'transparent';
      startStopButton.textContent = BTNSTART;
      startStopButton.style.backgroundColor = '#2ecc40';
  }
  
  // Display autostop button if autostart is enabled for any
  const autostart = Boolean(d.autostart);
  console.warn(d);
  console.warn(autostart);
  if (autostart) {
    autostartBtn.style.display = "block";
  }
  else{
    autostartBtn.style.display = "none";
  }
}

function flashCountdown(action) {

  flashButton = ignoreBtn;
  if (action == 'cancel_print'){
    flashButton = cancelBtn;
  } else if (action == 'pause_print'){
    flashButton = pauseBtn;
  }

  if (!flashButton) {
    return null;
  }

  // Get the current background color of the button
  const currentColor = window.getComputedStyle(flashButton).backgroundColor;

  // Set the current color as a CSS variable
  flashButton.style.setProperty('--current-color', currentColor);

  flashButton.classList.add("flash");

  return flashButton;
}


function triggerFlash(el) {
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');

  setTimeout(() => {
    el.classList.remove('flash');
  }, 600);
}

function sendDetectionRequest(isStart,item, cameraUUID) {
    if (cameraUUID === null || cameraUUID === undefined) {
        console.warn(`Cannot ${isStart ? 'start' : 'stop'} detection: no valid camera selected`);
        return Promise.resolve(false);
    }

    return fetch(`/detect/live/${isStart ? 'start' : 'stop'}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ camera_uuid: cameraUUID })
    })
    .then(response => {
        if (response.ok) {
          console.warn(`Successfully ${isStart ? 'started' : 'stopped'} live detection for camera ${cameraUUID}`);
          return true;
        } else {
            return response.json().then(errData => {
                console.error(`Failed to ${isStart ? 'start' : 'stop'} live detection for camera ${cameraUUID}. Server: ${errData.detail || response.statusText}`);
                return false;
            }).catch(() => {
                console.error(`Failed to ${isStart ? 'start' : 'stop'} live detection for camera ${cameraUUID}. Status: ${response.status} ${response.statusText}`);
                return false;
            });
        }
    })
    .catch(error => {
        console.error(`Network error or exception during ${isStart ? 'start' : 'stop'} request for camera ${cameraUUID}:`, error);
        return false;
    });
}

// Update each camera item with the latest data
function update_cameras () {
    cameraItems.forEach(item => {
        const camId = item.dataset.cameraId;
        updateDisplayItem(item,camId);
    });

}

// Called from sse when defect confirmed
document.addEventListener('defectRaised', evt => {
  const { alert_id, action, countdown } = evt.detail;
  
  if (!defectActive && countdown > 0) {
    if (ignoreBtn) ignoreBtn.style.display = "block";
    if (countdownTimer) countdownTimer.style.display = "block";
    flashButton = flashCountdown(action);
  }
  if (countdown > 0) {
    defectActive  = true;
    if (countdownTimer) countdownTimer.textContent = 'in ' + countdown + ' sec';
  } else {
    defectActive = false;
    if (flashButton?.classList) flashButton.classList.remove('flash');
    if (ignoreBtn) ignoreBtn.style.display = "none";
    if (countdownTimer) countdownTimer.style.display = "none";
  } 
});

// Called from sse when camera state updated in detection loop
document.addEventListener('cameraStateUpdated', evt => {
  const { camera_uuid, state } = evt.detail;
  console.warn(`Camera state updated for camera ${camera_uuid}: state=${state}`);
  const item = Array.from(cameraItems).find(item => item.dataset.cameraId === camera_uuid);
  if (item) {
    updateCameraDisplay(item, state);
  } else {
    console.warn(`No display item found for camera ${camera_uuid}`);
  }
});

// =========================
// Init
// =========================
(async function init() {

  const cameras = await getCameraList();

  // Support both array and object return types from getCameraList()
  const cameraCount = cameras
    ? (Array.isArray(cameras) ? cameras.length : Object.keys(cameras).length)
    : 0;

  if (cameraCount === 0) {
    const noCameraEl = document.getElementById("noCamera");
    if (noCameraEl) noCameraEl.style.display = "block";
  }

  //create top row of buttons
  createTopRowButtons();
  topControls = document.querySelector(".top-controls");
  ignoreBtn = topControls.querySelector(".btn-ignore");
  pauseBtn = topControls.querySelector(".btn-pause");
  cancelBtn = topControls.querySelector(".btn-cancel");
  countdownTimer = topControls.querySelector(".countdown-timer");

  	//create a row for each camera
	Object.keys(cameras).forEach(camera_uuid => {
			const camera = cameras[camera_uuid] || {};
			//createDisplayItem(camera_uuid, camera.nickname, camera.autostart);
      createDisplayItem(camera_uuid, camera.nickname);
		//addListenerToDisplayItem(item, camera_uuid);
		});

  
  createBottomRowButtons();

  //bottomtopControls = document.querySelector(".bottom-controls");
  //settingsBtn = bottomControls.querySelector(".btn-settings");
  //autostartBtn = bottomControls.querySelector(".btn-autostart");

  // add settings button after all camera cards
  //createSettingsButton();

  //createAutostartButton();

  //Get a list of all camera rows
    cameraItems = document.querySelectorAll('.camera-card');

    update_cameras();
    //setInterval(update_cameras, 5000);
})();


function executeCountdownAction(action_type) {
    fetch(`/countdown/action`, { 
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({action: action_type })
    })
        .then(response => {
            if (response.ok) {
                console.warn(`Successfully executed alert action: ${action_type}`);
            } else {
                console.error('Failed to execute alert action');
            }
        })
        .catch(error => console.error('Error trying to execute alert action:', error));
}


// =========================
// API
// =========================
async function getCameraList() {
  try {
    const result = await fetch("/config/get-camera-list");

    if (!result.ok) {
      if (result.status){
        throw new Error(`HTTP ${result.status}`);
      }
      else{
        throw new Error('Did not get data');
      }
    }

    const data = await result.json();
    return data.list;
    
  } catch (err){
    console.warn('Error from /config/get-camera-list', err);
    return {};
  }
}


async function reenableAutoStart() {
  try {
    const result = await fetch("/printer/reenableautostart");
    if (!result.ok) {
      throw new Error(`HTTP ${result.status}`);
    }
    //const data = await result.json();
    //return data.status;
    return;
  } catch (err) {
    console.warn('Error from /printer/reanableautostart', err);
    //return null;
    return;
  }
}


async function getCountdownSettings() {
  try {
    const result = await fetch("/config/get-countdown-settings");

    if (!result.ok) {
      if (result.status){
        throw new Error(`HTTP ${result.status}`);
      }
      else{
        throw new Error('Did not get data');
      }
    }

    const data = await result.json();
    return data.settings;

  } catch (err){
    console.warn('Error from /config/get-countdown-settings', err);
    return {} ;
  }
}

async function updateDisplayItem(item, cameraUUID) {
  // Only called to initialize the display item with the latest camera state
  // SSE is used to push updates when setection is running
  try {
    const result = await fetch("/config/get-camera-state", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        camera_uuid: cameraUUID
      })
    });

    if (!result.ok) {
      if (result.status){
        throw new Error(`HTTP ${result.status}`);
      }
      else{
        throw new Error('Did not get data');
      }
    }

    const data = await result.json();
    await updateCameraDisplay(item, data.state);
    return data.state;

  } catch (err) {
    console.warn(
      `Error from /config/get-camera-state for camera ${err}:`,
      err
    );

    return {};
  }
}
