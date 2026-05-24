console.warn("Countdown abstacted");

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
 let cameraItems;
 let detectionStatus;
 let BTNSTOP = 'Stop Detection';
 let BTNSTART =  'Start Detection';
 let defectActive = false;
 //let cameraUUID;
 // const countdownTimers = new Map(); // cameraId -> intervalId

 //
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

// =========================
// Create UI
// =========================
function createTopRowButtons(){
  const row = document.createElement("div");
  row.className = "button-row";
  const btnFrag = btnTemplate.content.cloneNode(true);
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

function createDisplayItem(camId,nickname) {
  // Wrapper (CRITICAL)
  const row = document.createElement("div");
  row.className = "camera-row";

  // Card
  const camFrag = camTemplate.content.cloneNode(true);
  const card = camFrag.firstElementChild;
  card.dataset.cameraId = camId;

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

  // Assemble
  row.appendChild(card);
  row.appendChild(video);

  grid.appendChild(row);
}

// =========================
// API
// =========================
async function getCameraList() {
  console.warn('Fetching camera list');
  try {
    const res = await fetch("/config/get-camera-list");
    if (!res.ok) return [];
    const data = await res.json();
    return data.camera_list || [];
  } catch {
    return [];
  }
}


function updateDisplayItem(item ,cameraUUID) {
    fetch(`/config/get-camera-state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_uuid: cameraUUID })
    })
    .then(response => {
        if (!response.ok) {
            console.warn(`Failed 1 to fetch data for camera ${cameraUUID}. Status: ${response.status} ${response.statusText}`);
            return response.json().then(errData => {
                throw new Error(`Failed 2 to fetch data for camera ${cameraUUID}: ${errData.detail || response.statusText}`);
            }).catch(() => {
                throw new Error(`Failed 3 to fetch data for camera ${cameraUUID}: ${response.statusText}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.warn(`Got data for camera ${cameraUUID}:`, data);
        const camData = {
            last_result: data.last_result,
            last_time: data.last_time,
            live_detection_running: data.live_detection_running,
            defect_active: data.defect_active
        };
        updateCameraDisplay(item,camData);
    })
    .catch(error => {
        console.error(`Error fetching state for camera ${cameraUUID}:`, error.message);
        const emptyData = {
            last_result: 'Error',
            last_time: 0,
            live_detection_running: 'Error',
            defect_active: false
        };
        return emptyData;
    });
}


function updateCameraDisplay(item, d) {

  const camPred = item.querySelector(".camera-detection .detection-value"); 
  camPred.textContent = d.last_result;
  camPred.style.color = d.last_result === 'success' ? 'green' : 'red';
  if (defectActive === true) {
    console.warn('Defect active');
    camPred.textContent = 'DEFECT';
  }

  const lastUpdate = item.querySelector(".last-update .update-value")
  lastUpdate.textContent = d.last_time ? new Date(d.last_time * 1000).toLocaleTimeString() : '-';

  let statusIndicator = item.querySelector('.camera-status');
  let startStopButton = item.querySelector('.start-stop-camera-btn');
  detectionStatus = d.live_detection_running;
  console.warn (`Camera ${item.dataset.cameraId} detection status: ${detectionStatus}`);
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
      //camPred.textContent = '';
  }

};


function flashCountdown(action) {
  //const topControls = document.querySelector(".top-controls");
  //const ignoreBtn = topControls.querySelector(".btn-ignore");
  //const pauseBtn = topControls.querySelector(".btn-pause");
  //const cancelBtn = topControls.querySelector(".btn-cancel");

  flashButton = ignoreBtn;
  if (action == 'cancel_print'){
    flashButton = cancelBtn;
  } else if (action == 'pause_print'){
    flashButton = pauseBtn;
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
        return;
    }
    console.warn(`Sending request to ${isStart ? 'start' : 'stop'} live detection for camera ${cameraUUID}`);
    fetch(`/detect/live/${isStart ? 'start' : 'stop'}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ camera_uuid: cameraUUID })
    })
    .then(response => {
        if (response.ok) {
          console.warn(`Successfully ${isStart ? 'started' : 'stopped'} live detection for camera ${cameraUUID}`);
        } else {
            response.json().then(errData => {
                console.error(`Failed to ${isStart ? 'start' : 'stop'} live detection for camera ${cameraUUID}. Server: ${errData.detail || response.statusText}`);
            }).catch(() => {
                console.error(`Failed to ${isStart ? 'start' : 'stop'} live detection for camera ${cameraUUID}. Status: ${response.status} ${response.statusText}`);
            });
        }
    })
    .catch(error => {
        console.error(`Network error or exception during ${isStart ? 'start' : 'stop'} request for camera ${cameraUUID}:`, error);
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
    ignoreBtn.style.display = "block";
    countdownTimer.style.display = "block";
    flashButton = flashCountdown(action);
  }
  if (countdown > 0) {
    defectActive  = true;
    countdownTimer.textContent = 'in ' + countdown + ' sec';
  } else {
    defectActive = false;
    flashButton.classList.remove('flash');
    ignoreBtn.style.display = "none";
    countdownTimer.style.display = "none";
  } 
});

//SRS If active - this is where its tracked
/*
document.addEventListener('cameraStateUpdated', evt => {
  return;
    console.warn('camera state updated');
    console.warn(evt.detail.camera_uuid)

    cameraItems.forEach(item => {
        const camId = item.dataset.cameraId; // data-camera-id ==> dataset.cameraId camelCase
        if (evt.detail.camera_uuid == camId){
        updateDisplayItem(item,camId);
        }
    });
});
*/





// =========================
// Init
// =========================
(async function init() {
  console.warn('Initializing');

  const cameras = await getCameraList();

  if (cameras.length === 0) {
    document.getElementById("noCamera").style.display = "block";
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
			const item = createDisplayItem(camera_uuid, cameras[camera_uuid].nickname);

		//addListenerToDisplayItem(item, camera_uuid);
		});


  //Get a list of all camera rows
    cameraItems = document.querySelectorAll('.camera-card');

    update_cameras();
    setInterval(update_cameras, 5000);
})();

//test feed settings
async function getCountdownSettings() {
  try {
    const res = await fetch("/get-countdown-settings");
    //const res = await fetch("/get-feed-settings");
    
    if (!res.ok) return [];
    const data = await res.json();
    return data.countdown || { countdown_action: null, countdown_time: null, countdown_control: null };;
  } catch {
    return { countdown_action: null, countdown_time: null, countdown_control: null };
  }
}



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


