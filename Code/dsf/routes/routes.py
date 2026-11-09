"""Consolidated FastAPI routes moved from the previous route modules."""


import asyncio
import math
import os
import signal
import threading
import time
import uuid
import json
from urllib.parse import urlsplit, urlunsplit
from copy import deepcopy

from fastapi import APIRouter, Body, Form, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, Response, JSONResponse
from sse_starlette.sse import EventSourceResponse

from logger_module import logger

from messages import CodedHTTPException, Message, coded, coded_errors
from alert_text import alert_text
from printer_control import running_as_plugin, suspend_print_job, printer_info, printer_settings_changed, reset_notification_counters

import cv2

from utils.config import (
        STREAM_MAX_FPS,
        CAMERA_SETTINGS,
        CAMERA_STATES,
        DEFAULT_CAMERA_SETTINGS,
        COUNTDOWN_SETTINGS,
        add_to_config,
        delete_from_config
)
from duet_config import DUET, get_config_for_ui, update_config
from utils.shared_video_stream import get_shared_stream_manager
from utils.detector import SENSITIVITY_STEPS
from utils.mjpeg_source import is_http_source, check_mjpeg_stream, fetch_snapshot_bytes, stream_mjpeg
from utils.stream_utils import (UI_countdown, default_notification_text, start_live_detection, stop_live_detection,
                                save_app_state_request, create_optimized_frame_generator,
                                pause_all_detection, stop_all_detection, resume_all_detection)

router = APIRouter()


# alert_routes.py
@router.post("/countdown/action")
async def alert_response(request: Request,
                         action=Body(..., embed=True)):
    """
    Handle alert response actions including ignore, cancel, and pause resume.
    Can be raised m the UI at any time independent of the alert's countdown status
    """

    if action not in ('ignore', 'pause_print', 'resume_print', 'cancel_print'):
        raise CodedHTTPException(400, Message("unknownAction", f"Unknown action {action}", action=action))

    await UI_countdown('stop')  # Stop the countdown timer on the UI immediately when an action is taken

    global COUNTDOWN_SETTINGS
    # Printer commands wait for the printer to change state, so they run in a thread
    match action:
        case 'ignore':  # allowing new alerts to be triggered
            COUNTDOWN_SETTINGS['alert_status'] = 'inactive'
        case 'pause_print':
            COUNTDOWN_SETTINGS['alert_status'] = 'paused'
            await asyncio.to_thread(suspend_print_job, action)
            await pause_all_detection()
            COUNTDOWN_SETTINGS['alert_status'] = 'paused'
        case 'resume_print':
            COUNTDOWN_SETTINGS['alert_status'] = 'resumed'
            await asyncio.to_thread(suspend_print_job, action)
            await resume_all_detection()
            COUNTDOWN_SETTINGS['alert_status'] = 'inactive'  # reset after action
        case 'cancel_print':
            COUNTDOWN_SETTINGS['alert_status'] = 'cancelled'
            await asyncio.to_thread(suspend_print_job, action)
            await stop_all_detection()
            COUNTDOWN_SETTINGS['alert_status'] = 'cancelled'  # Not reset since print job has been stopped
    return {"success": True}


# The pages are built from ui/ (Vue + Vuetify, built with Vite) into static/app - see ui/vite.config.js
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "app")


def serve_page(name):
    """A built page. The browser checks for a newer copy each time (the assets it loads have hashed names)."""
    return FileResponse(os.path.join(APP_DIR, f"{name}.html"), headers={"Cache-Control": "no-cache"})


@router.get("/index", include_in_schema=False)
async def serve_index():
    """Serve the Detection page."""
    return serve_page("index")


@router.get("/settings", include_in_schema=False)
async def serve_settings():
    """Serve the Settings page."""
    return serve_page("settings")


@router.get("/config", include_in_schema=False)
async def serve_config():
    """Serve the Configuration page."""
    return serve_page("config")


@router.get("/config/get-app-config", include_in_schema=False)
async def get_app_config():
    """Get the application configuration (secrets are not returned)."""
    config = get_config_for_ui()
    # What is sent when the ntfy / Pushover title or message is left blank
    title, message = default_notification_text(alert_text('cameraPlaceholder', '<camera nickname>'))
    config['default_notification'] = {'title': title, 'message': message}
    return config


@router.post("/config/save-app-config", include_in_schema=False)
async def save_app_config(request: Request):
    """Validate and save the application configuration."""
    data = await request.json()
    printer_before = (DUET.IP, DUET.PORT, DUET.PASSWORD)
    try:
        errors, restart_keys = update_config(data)
    except OSError as e:
        logger.error("Failed to save configuration: %s", e)
        raise CodedHTTPException(500, Message("configNotSaved", f"Failed to save configuration: {e}", error=e))
    if errors:
        return JSONResponse(status_code=400, content={"success": False, "errors": errors, "errorCodes": coded_errors(errors)})
    logger.info("Configuration updated from config page")
    if (DUET.IP, DUET.PORT, DUET.PASSWORD) != printer_before:
        printer_settings_changed()
    return {"success": True, "restart_required": restart_keys}


def get_camera_uuid_by_nickname(nickname: str):
    """Resolve a configured camera UUID from its nickname."""
    if not nickname:
        return None

    normalized = nickname.strip().lower()
    for camera_uuid, settings in CAMERA_SETTINGS.items():
        if settings and settings.get('nickname', '').strip().lower() == normalized:
            return camera_uuid

    return None


@router.get("/stream/{nickname}", include_in_schema=False)
async def serve_camera_stream(nickname: str):
    """Serve the page for a named camera stream. It gets the camera's details from /stream-info/<nickname>."""
    if not get_camera_uuid_by_nickname(nickname):
        raise CodedHTTPException(404, Message("cameraNotFound", "Camera not found"))
    return serve_page("stream")


@router.get("/stream-info/{nickname}", include_in_schema=False)
async def camera_stream_info(request: Request, nickname: str):
    """What the stream page needs: the camera's id, nickname, and its own stream URL (None for RTSP)."""
    camera_uuid = get_camera_uuid_by_nickname(nickname)
    if not camera_uuid:
        raise CodedHTTPException(404, Message("cameraNotFound", "Camera not found"))
    return {
            "camera_uuid": camera_uuid,
            "nickname": CAMERA_SETTINGS[camera_uuid].get('nickname', nickname),
            "direct_url": direct_stream_url(CAMERA_SETTINGS[camera_uuid].get('source'), request)
    }


def direct_stream_url(source, request):
    """The camera's own stream URL for the browser to load directly, at the camera's frame rate.

    Only HTTP (MJPEG) sources - browsers cannot play RTSP, so those return None and are shown
    through the plugin (limited to STREAM_MAX_FPS). A localhost source is on this machine, so it is
    given this machine's address as the browser sees it.
    """
    if not is_http_source(source):
        return None
    url = urlsplit(source)
    if url.hostname in ('localhost', '127.0.0.1', '::1'):
        netloc = request.url.hostname + (f':{url.port}' if url.port else '')
        if url.username:
            netloc = url.netloc.rsplit('@', 1)[0] + '@' + netloc
        url = url._replace(netloc=netloc)
    return urlunsplit(url)


@router.post("/settings/save-settings", include_in_schema=False)
async def update_settings(request: Request,
                          camera_uuid: str = Form(...),
                          majority_vote_threshold: int = Form(...),
                          majority_vote_window: int = Form(...),
                          sensitivity: int = Form(0)
                          ):
    """Update camera settings from the settings page."""
    if camera_uuid not in CAMERA_SETTINGS:
        raise CodedHTTPException(404, Message("cameraNotFound", "Camera not found"))
    if not -SENSITIVITY_STEPS <= sensitivity <= SENSITIVITY_STEPS:
        raise CodedHTTPException(400, Message("sensitivityRange", f"Sensitivity must be between -{SENSITIVITY_STEPS} and {SENSITIVITY_STEPS}.",
                                              steps=SENSITIVITY_STEPS))
    if majority_vote_threshold < 1:
        raise CodedHTTPException(400, Message("thresholdMin", "Majority vote threshold must be at least 1."))
    # A defect needs at least threshold failures within the window, so a smaller window could never trigger
    if majority_vote_window < majority_vote_threshold:
        raise CodedHTTPException(400, Message("windowMin", "Majority vote window must be at least the threshold."))
    add_to_config({'camera_settings': {camera_uuid: {
            "majority_vote_threshold": majority_vote_threshold,
            "majority_vote_window": majority_vote_window,
            "sensitivity": sensitivity
    }}})
    return {"success": True}


@router.post("/settings/update_autostart", include_in_schema=False)
async def update_autostart(request: Request):
    """Update camera autostart setting."""

    from app import activate_autostart_detection
    data = await request.json()
    camera_uuid = data.get('camera_uuid')
    checkbox = data.get('autostart')
    if isinstance(checkbox, bool):
        autostart = checkbox
    elif isinstance(checkbox, str):
        autostart = checkbox.lower() in ("on", "true", "1")
    else:
        autostart = False
    if camera_uuid not in CAMERA_SETTINGS:
        raise CodedHTTPException(404, Message("cameraNotFound", "Camera not found"))
    add_to_config({'camera_settings': {camera_uuid: {
            "autostart": autostart}}})

    # Since we updated autostart - check to see if any cameras have it set then let index UI
    autostartSet = any(
            settings.get("autostart", False)
            for settings in CAMERA_SETTINGS.values()
    )

    if not autostartSet:  # terminate the background thread
        activate_autostart_detection(False)

    # Update the UI
    await send_autostartUpdated_state(autostartSet)

    return {"success": True, "autostart": autostart}


@router.get('/camera/snapshot/{camera_uuid}', include_in_schema=False)
async def camera_snapshot(camera_uuid: str):
    if camera_uuid not in CAMERA_SETTINGS:
        raise CodedHTTPException(404, Message("cameraNotFound", "Camera not found"))
    try:
        # HTTP cameras: return the snapshot URL's JPEG as-is
        snapshot_url = CAMERA_SETTINGS.get(camera_uuid, {}).get('snapshot')
        if snapshot_url:
            data = await asyncio.to_thread(fetch_snapshot_bytes, snapshot_url)
            if data is None:
                raise HTTPException(status_code=502, detail="Camera snapshot failed")
            return Response(content=data, media_type="image/jpeg")

        # RTSP cameras: encode the latest frame from the shared video stream
        manager = get_shared_stream_manager()
        source = CAMERA_SETTINGS.get(camera_uuid, {}).get('source')
        stream = manager.get_stream(camera_uuid, source)
        max_wait_time = 10
        sleep_time = 0.5
        elapsed_time = 0
        while not stream.is_frame_available() and elapsed_time < max_wait_time:
            await asyncio.sleep(sleep_time)  # was time.sleep - blocked the whole server
            elapsed_time += sleep_time
        if not stream.is_frame_available():
            raise HTTPException(status_code=404, detail="No frame available")
        frame = stream.get_frame()
        if frame is None:
            raise HTTPException(status_code=500, detail="Failed to read frame")

        _, buffer = cv2.imencode('.jpg', frame)
        return Response(content=buffer.tobytes(), media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Snapshot error for %s: %s", camera_uuid, e)
        raise


def camera_live_stream(camera_uuid: str) -> StreamingResponse:
    """Live view: HTTP MJPEG is passed through as-is, RTSP is decoded and re-encoded."""
    source = CAMERA_SETTINGS[camera_uuid].get('source')
    if is_http_source(source):
        frames = stream_mjpeg(source, STREAM_MAX_FPS)
    else:
        frames = create_optimized_frame_generator(camera_uuid, lambda: None)
    return StreamingResponse(frames, media_type='multipart/x-mixed-replace; boundary=frame')


@router.get('/camera/stream/{camera_uuid}', include_in_schema=False)
async def camera_stream(camera_uuid: str):
    if camera_uuid not in CAMERA_SETTINGS:
        raise CodedHTTPException(404, Message("cameraNotFound", "Camera not found"))
    return camera_live_stream(camera_uuid)


def generate_preview_frames(source: str, preview_uuid: str):
    """Generate frames for camera preview using shared video stream."""
    manager = get_shared_stream_manager()
    try:
        stream = manager.get_stream(preview_uuid, source)
        while True:
            frame = stream.get_frame()
            if frame is None:
                logger.warning("Failed to get frame from source: %s", source)
                time.sleep(0.1)
                continue
            success, buffer = cv2.imencode('.jpg', frame)
            if not success or buffer is None or len(buffer) == 0:
                logger.warning("Invalid encoded frame from source: %s", source)
                time.sleep(0.1)
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.2)
    except (cv2.error, OSError, RuntimeError) as e:
        logger.error("Error in preview frame generation for source %s: %s", source, e)
    finally:
        try:
            manager.release_stream(preview_uuid)
        except (AttributeError, RuntimeError) as cleanup_error:
            logger.error("Error cleaning up preview stream %s: %s", preview_uuid, cleanup_error)


@router.get('/camera/preview', include_in_schema=False)
async def camera_preview(source: str):
    """Stream live camera preview for a specific source without registration."""
    if not source or not source.strip():
        raise HTTPException(status_code=400, detail="Missing preview source")
    if is_http_source(source):  # MJPEG passed through as-is
        return StreamingResponse(stream_mjpeg(source, 5),
                                 media_type='multipart/x-mixed-replace; boundary=frame')
    preview_uuid = f"preview_{uuid.uuid4()}"
    manager = get_shared_stream_manager()
    stream = manager.get_stream(preview_uuid, source)
    max_wait = 50
    wait_count = 0
    while not stream.is_frame_available() and wait_count < max_wait:
        await asyncio.sleep(0.1)  # was time.sleep - blocked the whole server
        wait_count += 1
    if not stream.is_frame_available():
        manager.release_stream(preview_uuid)
        raise HTTPException(status_code=504, detail="Preview stream failed to start")
    return StreamingResponse(generate_preview_frames(source, preview_uuid),
                             media_type='multipart/x-mixed-replace; boundary=frame')


# Get direct video feed
@router.get("/video/{nickname}/stream", include_in_schema=False)
async def stream_by_nickname(nickname: str):
    """Direct video stream by camera nickname."""
    camera_uuid = get_camera_uuid_by_nickname(nickname)
    if not camera_uuid:
        raise CodedHTTPException(404, Message("cameraNotFound", "Camera not found"))
    return camera_live_stream(camera_uuid)


async def rtsp_stream_works(source):
    """Return True if a frame can be read from an RTSP (or other OpenCV) source within 5 seconds."""
    check_uuid = f"check_{uuid.uuid4()}"
    manager = get_shared_stream_manager()
    stream = manager.get_stream(check_uuid, source)
    try:
        for _ in range(50):
            if stream.is_frame_available():
                return True
            await asyncio.sleep(0.1)
        return False
    finally:
        manager.release_stream(check_uuid)


async def check_camera_urls(source, snapshot):
    """Check the stream (and snapshot, if given) URLs of a new camera. Returns a list of problems."""
    async def snapshot_works():
        return not snapshot or await asyncio.to_thread(fetch_snapshot_bytes, snapshot) is not None

    # Checked together, so an unreachable camera only waits for one timeout
    stream_ok, snapshot_ok = await asyncio.gather(
            asyncio.to_thread(check_mjpeg_stream, source) if is_http_source(source) else rtsp_stream_works(source),
            snapshot_works())
    problems = []
    if not stream_ok:
        problems.append(Message("cameraStream", f"Could not read video from the stream URL {source}.", stream=source))
    if not snapshot_ok:
        problems.append(Message("cameraSnapshot", f"Could not get a JPEG image from the snapshot URL {snapshot}.", snapshot=snapshot))
    for problem in problems:
        logger.warning("Camera not added: %s", problem)
    return problems


# config_routes.py
@router.post("/config/add-camera")
async def add_camera_config(request: Request):
    """Add a new camera."""
    data = await request.json()
    nickname = data.get('nickname')
    source = data.get('source')
    if not nickname or not source:
        raise CodedHTTPException(400, Message("missingNicknameSource", "Missing camera nickname or source."))
    snapshot = data.get('snapshot')
    # HTTP cameras need a snapshot URL (used for detection and snapshots) - RTSP cameras do not
    if is_http_source(source) and not snapshot:
        raise CodedHTTPException(400, Message("missingSnapshot", "Missing camera snapshot URL."))
    problems = await check_camera_urls(source, snapshot)
    if problems:
        # One problem, or both (as one message)
        raise CodedHTTPException(400, problems[0] if len(problems) == 1 else Message(
                "cameraBoth", ' '.join(problems), stream=source, snapshot=snapshot))
    camera_uuid = str(uuid.uuid4())
    default_camera_settings = deepcopy(DEFAULT_CAMERA_SETTINGS)  # Precaution vs shallow copy
    add_to_config({'camera_settings': {camera_uuid: {
            "nickname": nickname,
            "source": source,
            **({"snapshot": snapshot} if snapshot else {}),
            **default_camera_settings
    }}})
    return {"camera_uuid": camera_uuid, "nickname": nickname, "source": source, "snapshot": snapshot}


@router.post("/config/remove-camera")
async def remove_camera_config(request: Request):
    """Remove a camera."""
    data = await request.json()
    camera_uuid = data.get('camera_uuid')
    if not camera_uuid or camera_uuid not in CAMERA_SETTINGS:
        raise CodedHTTPException(400, Message("cameraNotFound", "Camera not found"))
    try:
        # Stop detection and this camera's video stream (other cameras are not affected)
        if CAMERA_STATES.get(camera_uuid, {}).get('live_detection_running') == 'yes':
            await stop_live_detection(camera_uuid)
        get_shared_stream_manager().release_stream(camera_uuid)
        logger.debug("Released camera %s", camera_uuid)
        delete_from_config({'camera_settings': camera_uuid})
        if camera_uuid in CAMERA_STATES:
            delete_from_config({'camera_states': camera_uuid})
        return {"success": True}
    except KeyError:
        return {"success": False}


@router.get("/config/get-camera-list", include_in_schema=False)
async def config_camera_list(request: Request):
    """Get a list of current camera id's, nickname, source and card settings."""
    try:
        camera_uuid_list = {}
        for camera_uuid in CAMERA_SETTINGS:
            camera_uuid_list[camera_uuid] = {
                    "nickname": CAMERA_SETTINGS[camera_uuid].get("nickname", ""),
                    "source": CAMERA_SETTINGS[camera_uuid].get("source", ""),
                    "autostart": CAMERA_SETTINGS[camera_uuid].get("autostart", False),
                    "majority_vote_threshold": CAMERA_SETTINGS[camera_uuid].get("majority_vote_threshold"),
                    "majority_vote_window": CAMERA_SETTINGS[camera_uuid].get("majority_vote_window"),
                    "sensitivity": CAMERA_SETTINGS[camera_uuid].get("sensitivity", 0)
            }

        return {"success": True, "list": camera_uuid_list}
    except Exception:
        return {"success": False}


@router.get("/config/get-countdown-settings", include_in_schema=False)
async def get_countdown_settings(request: Request):
    """Retrieve countdown settings."""
    try:
        settings = COUNTDOWN_SETTINGS
        return {"success": True, "settings": settings}
    except Exception:
        return {"success": False}


@router.post("/config/get-camera-setting", include_in_schema=False)
async def get_camera_setting(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Get the current setting of a specific camera."""
    try:
        setting = CAMERA_SETTINGS.get(camera_uuid)
        return {"success": True, "setting": setting}
    except Exception:
        return {"success": False}


@router.post("/config/get-camera-state", include_in_schema=False)
async def get_camera_state_config(request: Request, camera_uuid: str = Body(..., embed=True)):
    """
    Get the current state of a specific camera.
    LEAVE OUT NON SERIALIZABLE
    'live_detection_task'
    """
    try:
        # state = deepcopy(CAMERA_STATES[camera_uuid]) # A precaution vs shallow copy
        # Cannot use because raises error trying tp parse task object
        state = {}
        for key, value in CAMERA_STATES[camera_uuid].items():
            if key != 'live_detection_task':
                state[key] = value
        return {"success": True, "state": state}
    except Exception as e:
        logger.critical(f'Camera is not recognized {e=} Try restarting')
        return {"success": False}


@router.post("/config/update-countdown", include_in_schema=False)
async def update_countdown(request: Request,
                           countdown_action: str = Form(...),
                           countdown_time: int = Form(...),
                           countdown_control: str = Form(...)
                           ):
    """Update countdown settings from the settings page."""
    if countdown_action not in ('ignore', 'pause_print', 'cancel_print'):
        raise CodedHTTPException(400, Message("unknownAction", f"Unknown action {countdown_action}", action=countdown_action))
    if countdown_control not in ('any_camera', 'all_cameras'):
        raise CodedHTTPException(400, Message("unknownCameraChoice", f"Unknown camera choice {countdown_control}", choice=countdown_control))
    if countdown_time < 0:
        raise CodedHTTPException(400, Message("countdownTimeMin", "Countdown time must be 0 or more"))
    try:
        add_to_config({'countdown_settings': {
                                                        "countdown_action": countdown_action,
                                                        "countdown_time": countdown_time,
                                                        "countdown_control": countdown_control
                                                        }})
        return {"success": True}
    except Exception:
        return {"success": False}

# sse_routes.py


class SSEManager:
    def __init__(self):
        self.clients = []
        self.lock = asyncio.Lock()
        self.last_countdown_state = None  # Track last countdown for new connections

    async def connect(self):
        queue = asyncio.Queue()
        async with self.lock:
            self.clients.append(queue)
        return queue

    async def disconnect(self, queue):
        async with self.lock:
            if queue in self.clients:
                self.clients.remove(queue)

    async def broadcast(self, message):
        async with self.lock:
            # Store countdown messages for new clients
            if message.get("event") == "countdown_time":
                self.last_countdown_state = message

            for client in self.clients:
                await client.put(message)


global managerSSE
managerSSE = SSEManager()


@router.get("/sse")
async def sse_connect(request: Request):
    """Establish Server-Sent Events connection for real-time updates."""
    queue = await managerSSE.connect()

    async def send_packet():
        try:
            # Send current countdown state to new client if one is active
            if managerSSE.last_countdown_state is not None:
                yield remaining_countdown(managerSSE.last_countdown_state)

            while True:
                if await request.is_disconnected():
                    logger.debug('sse request disconnected')
                    break
                packet = await queue.get()
                yield packet
        finally:
            await managerSSE.disconnect(queue)

    return EventSourceResponse(send_packet())


def remaining_countdown(packet):
    """A countdown packet with the time left, for a browser that connects part way through it."""
    data = json.loads(packet['data'])
    ends_at = data.get('ends_at')
    if ends_at and data.get('countdown_time', 0) > 0:
        data['countdown_time'] = max(0, math.ceil(ends_at - time.time()))
    return {**packet, 'data': json.dumps(data)}


# detection_routes.py
@router.post("/detect/live/start")
async def starting_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Start continuous live detection on a specified camera."""
    try:
        save_app_state_request(request.app.state)  # Save the request state for later use in start_live_detection
        return await start_live_detection(camera_uuid)
    except Exception as e:
        logger.error("Error starting live detection for camera %s: %s", camera_uuid, e)
        message = Message("detectionNotStarted", f"Failed to start live detection for camera {camera_uuid}", camera=camera_uuid)
        return {"success": False, "message": message, "code": coded(message)}


@router.post("/detect/live/stop")
async def stopping_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Stop continuous live detection on a specified camera."""
    try:
        await stop_live_detection(camera_uuid)
    except Exception as e:
        logger.error("Error stopping live detection task for camera %s: %s", camera_uuid, e)

    return {"message": f"Live detection stopped for camera {camera_uuid}"}


@router.get("/printer/get-status", include_in_schema=False)
async def get_printer_status(request: Request):
    """Get the status of the printer."""
    try:
        return {"success": True, **printer_info()}
    except Exception as e:
        logger.error("Error getting printer status: %s", e)
        return {"success": False, "message": "Failed to get printer status"}


@router.post("/printer/connect", include_in_schema=False)
async def connect_printer(request: Request):
    """New printer settings from the page while the printer is not connected: save them and connect at once.

    Takes {ip, port, password}: a blank port is 80 and a blank password keeps the saved one.
    """
    if printer_info()["connected"]:
        message = Message("alreadyConnected", "Already connected to the printer")
        return JSONResponse(status_code=409, content={"success": False, "errors": {}, "message": message, "code": coded(message)})
    data = await request.json()
    settings = {"IP": data.get("ip") or "", "PORT": data.get("port") if str(data.get("port") or "").strip() else 80}
    if data.get("password"):
        settings["PASSWORD"] = data["password"]
    try:
        errors, _ = update_config({"DUET": settings})
    except OSError as e:
        logger.error("Failed to save the printer settings: %s", e)
        raise CodedHTTPException(500, Message("printerNotSaved", f"Failed to save the printer settings: {e}", error=e))
    if errors:
        message = Message("notSavedMarked", "Not saved - check the marked settings")
        return JSONResponse(status_code=400, content={"success": False, "errors": errors, "errorCodes": coded_errors(errors),
                                                      "message": message, "code": coded(message)})
    printer_settings_changed()  # Connects again even if nothing changed, e.g. after the printer was switched on
    address = printer_info()['address']
    message = Message("savedConnecting", f"Saved - connecting to the printer at {address}", printer=address)
    return {"success": True, "message": message, "code": coded(message)}


@router.get("/printer/enableautostart", include_in_schema=False)
async def enable_autostart(request: Request):
    """Eenable autostart"""
    from app import activate_autostart_detection
    try:
        activate_autostart_detection(True)
        return {"success": True}
    except Exception as e:
        logger.error("Error enabling autostart: %s", e)
        return {"success": False, "message": "Failed to enable autostart"}


@router.get("/printer/disableautostart", include_in_schema=False)
async def disable_autostart(request: Request):
    """Disable autostart"""
    from app import activate_autostart_detection
    try:
        activate_autostart_detection(False)
        return {"success": True}
    except Exception as e:
        logger.error("Error disabling autostart: %s", e)
        return {"success": False, "message": "Failed to disable autostart"}


async def send_autostartUpdated_state(state):
    """Send a direct autostart state SSE event to the browser.

    This bypasses the ALERT model and the alert queueing path.
    Only the camera state payload is sent to the SSE client.
    """
    try:
        from routes.routes import managerSSE
        payload = {
                "event": "autostart_updated",
                "data": json.dumps({
                        "state": state
                })
        }
        await managerSSE.broadcast(payload)
        logger.debug(f"Broadcast autostart_updated to {state}")
    except Exception as e:
        logger.error("Failed to broadcast autostartUpdated SSE event =  %s: %s", state, e)

TERMINATE_FORCE_SECONDS = 10  # Exits anyway if a clean stop has not finished by then


def _terminate():
    """Stop the program as Ctrl+C does - uvicorn shuts down cleanly - and exit anyway if that hangs."""
    def force():
        time.sleep(TERMINATE_FORCE_SECONDS)
        logger.warning('The program did not stop cleanly - forcing it to exit')
        os._exit(0)
    threading.Thread(name='forceExit', target=force, daemon=True).start()
    signal.raise_signal(signal.SIGINT)


@router.post("/terminate", include_in_schema=False)
async def terminate_program():
    """Terminate the program - not as the plugin, which DWC's plugin manager starts and stops."""
    if running_as_plugin():
        raise CodedHTTPException(403, Message("terminatePlugin", "Running as a plugin - stop it from DWC's plugin manager"))
    logger.info('Terminate the Program was pressed - stopping')
    threading.Timer(0.5, _terminate).start()  # After this reply has been sent
    message = Message("stopping", "duetPrintGuard is stopping")
    return {"success": True, "message": message, "code": coded(message)}


@router.get("/printer/resetnotifications", include_in_schema=False)
async def reset_notifications(request: Request):
    """Disable autostart"""
    try:
        reset_notification_counters()
        logger.debug(f'Notifocation counters reset')
        return {"success": True}
    except Exception as e:
        logger.error("Error disabling autostart: %s", e)
        return {"success": False, "message": "Failed to reset notifications"}
