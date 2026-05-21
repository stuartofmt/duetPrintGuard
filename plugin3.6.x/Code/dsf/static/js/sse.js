/*
const evtSource = new EventSource('/sse');
const notificationPopup = document.getElementById('notificationPopup');
const notificationMessage = document.getElementById('notificationMessage');
const notificationImage = document.getElementById('notificationImage');
const notificationCountdownTimer = document.getElementById('notificationCountdownTimer');
const dismissNotificationBtn = document.getElementById('dismissNotificationBtn');
const cancelPrintBtn = document.getElementById('cancelPrintBtn');
const pausePrintBtn = document.getElementById('pausePrintBtn');
*/
let currentAlertId = null;

//document.addEventListener('DOMContentLoaded', loadPendingAlerts);

function getLocalActiveAlerts() {
    try {
        return JSON.parse(localStorage.getItem('activeAlerts')) || {};
    } catch (e) {
        console.error("Error parsing activeAlerts from localStorage:", e);
        return {};
    }
}

function getRemoteActiveAlerts() {
    return fetch('/alert/active', {
        method: 'GET',
    })
        .then(response => response.json())
        .then(data => data.active_alerts || [])
        .catch(error => {
            console.error("Error fetching remote active alerts:", error);
            return [];
        });
}

function saveActiveAlert(alert) {
    const activeAlerts = getLocalActiveAlerts();
    const expirationTime = Date.now() + (alert.countdown_time || 10) * 1000;
    activeAlerts[alert.id] = {
        data: alert,
        expirationTime: expirationTime
    };
    localStorage.setItem('activeAlerts', JSON.stringify(activeAlerts));
}

function removeActiveAlert(alertId) {
    const activeAlerts = getLocalActiveAlerts();
    if (activeAlerts[alertId]) {
        delete activeAlerts[alertId];
        localStorage.setItem('activeAlerts', JSON.stringify(activeAlerts));
    }
}

async function loadPendingAlerts() {
    const activeAlerts = getLocalActiveAlerts();
    const now = Date.now();
    const remoteAlerts = await getRemoteActiveAlerts();
    const remoteAlertIds = remoteAlerts.map(alert => alert.id);
    
    Object.keys(activeAlerts).forEach(alertId => {
        if (activeAlerts[alertId].expirationTime < now || !remoteAlertIds.includes(alertId)) {
            delete activeAlerts[alertId];
        }
    });
    
    remoteAlerts.forEach(remoteAlert => {
        if (!activeAlerts[remoteAlert.id]) {
            const alert_start_time = remoteAlert.timestamp * 1000;
            const expirationTime = alert_start_time + (remoteAlert.countdown_time * 1000);
            activeAlerts[remoteAlert.id] = {
                data: remoteAlert,
                expirationTime: expirationTime
            };
        }
    });
    
    localStorage.setItem('activeAlerts', JSON.stringify(activeAlerts));
    const alertIds = Object.keys(activeAlerts);

    alertIds.forEach(alertId => {
        const alert = activeAlerts[alertId].data;
        alert.countdown_time = Math.max(1, Math.floor((activeAlerts[alertId].expirationTime - now) / 1000));
        displayAlert(alert);
        console.warn('Pending Alert');
    });
    
    return alertIds.length > 0;
}

function displayAlert(alert_data) {
    const parsedData = parseAlertData(alert_data);
    //updateAlertUI(parsedData);
    startAlertCountdown(parsedData);
    //saveActiveAlert(parsedData);
}

function parseAlertData(alert_data) {
    return typeof alert_data === 'string' ? JSON.parse(alert_data) : alert_data;
}


function startAlertCountdown(data) {
    console.warn('Starting countdown for alert:', data);
    if (!data || !data.camera_uuid) return;

    const countdownTimerId = 'countdown';
    //const countdownTimerId = `countdown-${data.camera_uuid}`;

    // Clear any existing timer for this camera
    // only one timer instance - ignore calls during countdown
    if (window[countdownTimerId]) {
        return;
        //clearInterval(window[countdownTimerId]);
        //delete window[countdownTimerId];
    }

    const startTime = Date.now();
    const countdownTime = data.countdown_time || 0;
    const endTime = startTime + countdownTime * 1000;


    function updateCountdown() {
        const now = Date.now();
        const secondsLeft = Math.max(0, Math.ceil((endTime - now) / 1000));

        // Dispatch event
        document.dispatchEvent(new CustomEvent('defectRaised', {
            detail: {
                alert_id: data.id,
                action: data.countdown_action,
                countdown: secondsLeft
            }
        }));
        

        // Update local storage
        const activeAlerts = getLocalActiveAlerts();
        if (activeAlerts[data.id]) {
            activeAlerts[data.id].expirationTime = endTime;
            localStorage.setItem('activeAlerts', JSON.stringify(activeAlerts));
        }

        // Stop when done
        if (secondsLeft <= 0) {
            clearInterval(window[countdownTimerId]);
            delete window[countdownTimerId];
        }
    }

    // Start interval FIRST
    window[countdownTimerId] = setInterval(updateCountdown, 1000);

    // Then run immediately
    updateCountdown();
}


evtSource.onmessage = (e) => {
    try {
        let packet_data = JSON.parse(e.data);
        packet_data = packet_data.data;
        if (packet_data) {
            if (packet_data.event == "alert") {
                displayAlert(packet_data.data);
            }
            else if (packet_data.event == "camera_state") {
                const cameraData = packet_data.data;
                if (!cameraData.camera_uuid) {
                    console.warn("Camera data missing camera_uuid", cameraData);
                }
                if (typeof cameraData.live_detection_running !== 'boolean') {
                    cameraData.live_detection_running = !!cameraData.live_detection_running;
                }
                document.dispatchEvent(new CustomEvent('cameraStateUpdated', {
                    detail: cameraData
                }));
            }
            else if (packet_data.event == "printer_state") {
                const printerData = packet_data.data;
                document.dispatchEvent(new CustomEvent('printerStateUpdated', {
                    detail: printerData
                }));
        } else {
                document.dispatchEvent(new CustomEvent('cameraStateUpdated', {
                    detail: 'No Packet Data'
                }));
            }
        }
    } catch (error) {
        console.error("Error processing SSE message:", error);
    }
};

evtSource.onerror = (err) => {
    console.error("SSE error", err);
};


