console.info('sse.js loaded');

let evtSource;
try {
    evtSource = new EventSource('/sse');
    console.info('Attempting SSE connection to /sse');
} catch (error) {
    console.error('Failed to create EventSource', error);
}

if (evtSource) {
    evtSource.onopen = (event) => {
        console.info('SSE connection opened', event);
    };

    evtSource.onerror = (err) => {
        console.error('SSE error', err, 'readyState=', evtSource.readyState);
    };

    evtSource.addEventListener('countdown_time', (e) => {
        try {
            const countdownData = JSON.parse(e.data);
            console.warn('Received countdown_time event:', countdownData);
            startAlertCountdown(countdownData);
        } catch (error) {
            console.error('Error parsing countdown_time SSE event data:', error, e.data);
        }
    });

    evtSource.addEventListener('error', (err) => {
        console.error('SSE event error', err, 'readyState=', evtSource.readyState);
    });
}

/*
const notificationPopup = document.getElementById('notificationPopup');
const notificationMessage = document.getElementById('notificationMessage');
const notificationImage = document.getElementById('notificationImage');
const notificationCountdownTimer = document.getElementById('notificationCountdownTimer');
const dismissNotificationBtn = document.getElementById('dismissNotificationBtn');
const cancelPrintBtn = document.getElementById('cancelPrintBtn');
const pausePrintBtn = document.getElementById('pausePrintBtn');
*/
//let currentAlertId = null;

//document.addEventListener('DOMContentLoaded', loadPendingAlerts);
/*
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
*/

function parseAlertData(alert_data) {
    return typeof alert_data === 'string' ? JSON.parse(alert_data) : alert_data;
}


function startAlertCountdown(data) {
    console.warn('Starting countdown for alert:', data);
    const countdownTime = typeof data === 'number' ? data : (data?.countdown_time || 0);
    if (countdownTime <= 0) return;

    const countdownTimerId = 'countdown';
    const countdownAction = typeof data === 'object' ? data.countdown_action : null;

    if (window[countdownTimerId]) {
        return;
    }

    const startTime = Date.now();
    const endTime = startTime + countdownTime * 1000;


    function updateCountdown() {
        const now = Date.now();
        const secondsLeft = Math.max(0, Math.ceil((endTime - now) / 1000));

        // Dispatch event
        document.dispatchEvent(new CustomEvent('defectRaised', {
            detail: {
                action: countdownAction,
                countdown: secondsLeft
            }
        }));

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


if (evtSource) {
    evtSource.onmessage = (e) => {
        try {
            let packet_data = JSON.parse(e.data);
            packet_data = packet_data.data;
            if (packet_data) {
                if (packet_data.event == "alert") {
                    console.warn('Wrong call');
                }
                else if (packet_data.event == "countdown_time") {
                    console.warn('Received countdown_time event:', packet_data);
                    startAlertCountdown(packet_data.data);
                }
            } else {
                console.warn('No data in SSE message');
            }
        } catch (error) {
            console.error("Error processing SSE message:", error);
        }
    };

    evtSource.addEventListener('error', (err) => {
        console.error('SSE event error', err, 'readyState=', evtSource.readyState);
    });
}


