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
            //console.warn('event listener Received countdown_time event:', countdownData);
            AlertCountdown(countdownData);
        } catch (error) {
            console.error('Error parsing countdown_time SSE event data:', error, e.data);
        }
    });

    evtSource.addEventListener('camera_updated', (e) => {
        try {
            const cameraData = JSON.parse(e.data);
            console.warn('event listener Received camera_updated event:', cameraData);
            UpdateCameraState(cameraData);
        } catch (error) {
            console.error('Error parsing camera_updated SSE event data:', error, e.data);
        }
    });

    evtSource.addEventListener('error', (err) => {
        console.error('SSE event error', err, 'readyState=', evtSource.readyState);
    });
}


function parseAlertData(alert_data) {
    return typeof alert_data === 'string' ? JSON.parse(alert_data) : alert_data;
}


function AlertCountdown(data) {
    // Typically only called once with alert
    //calling with countdownTime <=0 stops the countdown after sending 0 to UI

    console.warn('Starting countdown for alert:', data);
    const countdownTime = typeof data === 'number' ? data : (data?.countdown_time || 0);
    //if (countdownTime <= 0) return;

    const countdownTimerId = 'countdown';
    const countdownAction = typeof data === 'object' ? data.countdown_action : null;

    const alert_status = typeof data === 'object' ? data.alert_status : null;

    // Check to see if stop requested
    if (countdownTime <= 0) {
        if (window[countdownTimerId]) {
            //console.warn('Stopping countdown timer');
            clearInterval(window[countdownTimerId]);
            delete window[countdownTimerId];
        }
        // Dispatch event
        console.warn('stopping countdown');
        document.dispatchEvent(new CustomEvent('defectRaised', {
            detail: {
                action: countdownAction,
                countdown: 0,
                alert_status: alert_status
            }
        }));
        return;
        }

    // Prevent multiple timers
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
                countdown: secondsLeft,
                alert_status: alert_status
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


function UpdateCameraState(data) {

    //console.warn('updating camera state:', data);

    const camera_uuid = typeof data === 'object' ? data.camera_uuid : null;

    const state = typeof data === 'object' ? data.state : null;

        // Dispatch event
        //console.warn('updating camera status for camera_uuid:', camera_uuid, 'state:', state );
        document.dispatchEvent(new CustomEvent('cameraStateUpdated', {
            detail: {
                camera_uuid: camera_uuid,
                state: state
            }
        }));
        return;
}


if (evtSource) {
    evtSource.onmessage = (e) => {
        try {
            let packet_data = JSON.parse(e.data);
            packet_data = packet_data.data;
            if (packet_data) {
                if (packet_data.event == "alert") {
                    console.warn('Wrong call - no event called alert should be raised');
                }
                else if (packet_data.event == "countdown_time") {
                    //console.warn('onmessage countdown_time event:', packet_data);
                    AlertCountdown(packet_data.data);
                }
                else if (packet_data.event == "camera_updated") {
                    console.warn('onmessage camera_updated event:', packet_data);
                    UpdateCameraState(packet_data.data);
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


