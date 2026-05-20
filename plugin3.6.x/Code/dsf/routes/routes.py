"""Consolidated FastAPI routes moved from the previous route modules."""

import json
import asyncio
import time
import uuid

from fastapi import APIRouter, Body, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, Response, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from logger_module import logger
from models import AlertAction, SavedConfig
from duet_printer import suspend_print_job

from utils.alert_utils import alert_to_response_json, dismiss_alert, get_alert
import cv2
from utils.camera_utils import (
    xadd_camera as add_camera,
    find_available_serial_cameras,
    get_camera_state,
    xremove_camera as remove_camera_util,
    update_camera_state,
)
from utils.camera_state_manager import get_camera_state_manager
from utils.config import (
    CAMERA_SETTINGS,
    CAMERA_STATES,
    DEFAULT_CAMERA_SETTINGS,
    COUNTDOWN_SETTINGS,
    add_to_config,
    delete_from_config,
    get_config,
    STREAM_MAX_FPS,
    STREAM_JPEG_QUALITY,
    STREAM_MAX_WIDTH,
    DETECTION_INTERVAL_MS,
    MIN_SSE_DISPATCH_DELAY_MS,
)
from utils.shared_video_stream import get_shared_stream_manager
from utils.stream_utils import _live_detection_loop, generate_frames, stream_optimizer
#from utils.sse_utils import outbound_packet_fetch, stop_and_remove_polling_task
from utils.sse_utils import outbound_packet_fetch

router = APIRouter()

# alert_routes.py
@router.post("/alert/dismiss")
async def alert_response(request: Request,
                         alert_id: str = Body(..., embed=True),
                         action: AlertAction = Body(..., embed=True)):
    """Handle alert response actions including dismiss, cancel, and pause."""
    alert = get_alert(alert_id)
    camera_uuid = alert.camera_uuid if alert else None
    if not alert or camera_uuid is None:
        return {"message": f"Alert {alert_id} not found."}
    response = None
    match action:
        case AlertAction.DISMISS:
            response = await dismiss_alert(alert_id)
        case AlertAction.CANCEL_PRINT | AlertAction.PAUSE_PRINT:
            suspend_print_job(camera_uuid, action)
            return await dismiss_alert(alert_id)
    if not response:
        response = {"message": f"Alert {alert_id} not found."}
    return response


@router.get("/alert/active")
async def get_active_alerts(request: Request):
    """Retrieve all currently active alerts."""
    alerts = []
    for alert in request.app.state.alerts.values():
        alerts.append(json.loads(alert_to_response_json(alert)))
    return {"active_alerts": alerts}


# detection_routes.py
@router.post("/detect/live/start")
async def start_live_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Start continuous live detection on a specified camera."""
    global CAMERA_STATES
    camera_state = CAMERA_STATES.get(camera_uuid)
    if camera_state and camera_state.get("live_detection_running"):
        return {"success": True, "message": f"Live detection already running for camera {camera_uuid}"}

    CAMERA_STATES[camera_uuid] = {
            "live_detection_running": False,
            "last_result": '',
            "last_time": None,
            "defect_active": False,
            "live_detection_task": None
    }

    try:
        print(f'attempting to create live detection loop for {camera_uuid}')
        print(f'with app.state {request.app.state}')
        task = asyncio.create_task(_live_detection_loop(request.app.state, camera_uuid))
        
        CAMERA_STATES[camera_uuid]['live_detection_running'] = True
        CAMERA_STATES[camera_uuid]['live_detection_task'] = task
        CAMERA_STATES[camera_uuid]['last_time'] = time.time()

    except Exception as e:
        logger.error("Error starting live detection for camera %s: %s", camera_uuid, e)
        return {"success": False, "message": f"Failed to start live detection for camera {camera_uuid}"}

    return {"success": True, "message": f"Live detection started for camera {camera_uuid}"}


@router.post("/detect/live/stop")
async def stop_live_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Stop continuous live detection on a specified camera."""
    global CAMERA_STATES

    if not CAMERA_STATES[camera_uuid]['live_detection_running']:
        return {"message": f"Live detection not running for camera {camera_uuid}"}
    
    live_detection_task = CAMERA_STATES[camera_uuid]['live_detection_task']
    if live_detection_task:
        try: #Just cancel the task
            #await asyncio.wait_for(live_detection_task, timeout=0.25)
            #logger.debug("Live detection task for camera %s finished successfully.", camera_uuid)
        #except asyncio.TimeoutError:
            #logger.debug("Live detection task for camera %s did not finish in time.", camera_uuid)
            live_detection_task.cancel()
            CAMERA_STATES[camera_uuid] = {
                "live_detection_running": False,
                "last_result": '',
                "last_time": None,
                "defect_active": False,
                "live_detection_task": None
            }
            logger.debug("Stopped live detection task for camera %s", camera_uuid)
        except Exception as e:
            logger.error("Error stopping live detection task for camera %s: %s", camera_uuid, e)

    return {"message": f"Live detection stopped for camera {camera_uuid}"}


# index_routes.py
@router.get("/index", include_in_schema=False)
async def serve_index(request: Request):
    """Serve the main index page."""
    from app import templates
    return templates.TemplateResponse("index.html", {
        "request": request
    })


@router.post("/xindex", include_in_schema=False)
async def update_index_settings(request: Request,
                          camera_uuid: str = Form(...),
                          sensitivity: float = Form(...),
                          brightness: float = Form(...),
                          contrast: float = Form(...),
                          focus: float = Form(...),
                          countdown_time: int = Form(...),
                          countdown_action: str = Form(...),
                          majority_vote_threshold: int = Form(...),
                          majority_vote_window: int = Form(...),
                          ):
    """Update camera settings from the index page."""
    await update_camera_state(camera_uuid, {
        "sensitivity": sensitivity,
        "brightness": brightness,
        "contrast": contrast,
        "focus": focus,
        "countdown_time": countdown_time,
        "countdown_action": countdown_action,
        "majority_vote_threshold": majority_vote_threshold,
        "majority_vote_window": majority_vote_window,
    })
    return RedirectResponse("/index", status_code=303)


# settings_routes.py
@router.get("/settings", include_in_schema=False)
async def serve_settings(request: Request):
    """Serve the settings page."""
    from app import templates
    if len(CAMERA_SETTINGS) <= 0:
        logger.warning("No camera UUIDs found, attempting to initialize cameras...")
    return templates.TemplateResponse("settings.html", {
        "request": request
    })


@router.post("/settings/save-settings", include_in_schema=False)
async def update_settings(request: Request,
                          camera_uuid: str = Form(...),
                          sensitivity: float = Form(...),
                          brightness: float = Form(...),
                          contrast: float = Form(...),
                          focus: float = Form(...),
                          majority_vote_threshold: int = Form(...),
                          majority_vote_window: int = Form(...)
                          ):
    """Update camera settings from the settings page."""
    add_to_config({'camera_settings': {camera_uuid: {
        "sensitivity": sensitivity,
        "brightness": brightness,
        "contrast": contrast,
        "focus": focus,
        "majority_vote_threshold": majority_vote_threshold,
        "majority_vote_window": majority_vote_window
    }}})
    return RedirectResponse("/settings", status_code=303)


@router.post("/settings/update-countdown", include_in_schema=False)
async def update_settings_countdown(request: Request,
                            countdown_action: str = Form(...),
                            countdown_time: int = Form(...),
                            countdown_control: str = Form(...)
                          ):
    """Update countdown settings from the settings page."""
    print(f"Received countdown settings update: action={countdown_action}, time={countdown_time}, control={countdown_control}")
    add_to_config({'countdown_settings': {
                            "countdown_action": countdown_action,
                            "countdown_time": countdown_time,
                            "countdown_control": countdown_control
                            }})
    return RedirectResponse("/settings", status_code=303)


# camera_routes.py
@router.post("/xcamera/state", include_in_schema=False)
async def get_camera_state_ep(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Get the current state of a specific camera."""
    logger.debug('entered get_camera_state_ep with camera_uuid: %s', camera_uuid)
    camera_state = await get_camera_state(camera_uuid)
    detection_times = [t for t, _ in camera_state.detection_history] if (
        camera_state.detection_history
        ) else []
    response = {
        "nickname": camera_state.nickname,
        "start_time": camera_state.start_time,
        "last_result": camera_state.last_result,
        "last_time": camera_state.last_time,
        "detection_times": detection_times,
        "error": camera_state.error,
        "live_detection_running": camera_state.live_detection_running,
        "brightness": camera_state.brightness,
        "contrast": camera_state.contrast,
        "focus": camera_state.focus,
        "majority_vote_threshold": camera_state.majority_vote_threshold,
        "majority_vote_window": camera_state.majority_vote_window,
        "current_alert_id": camera_state.current_alert_id,
        "sensitivity": camera_state.sensitivity,
        "printer_id": camera_state.printer_id,
        "printer_config": camera_state.printer_config,
        "countdown_action": camera_state.countdown_action,
        "countdown_time": camera_state.countdown_time,
        "countdown_control":camera_state.countdown_control
    }
    return response


@router.get('/camera/feed/{camera_uuid}', include_in_schema=False)
async def camera_feed(camera_uuid: str):
    """Stream live camera feed for a specific camera."""
    return StreamingResponse(generate_frames(camera_uuid),
                             media_type='multipart/x-mixed-replace; boundary=frame')


@router.get('/camera/snapshot/{camera_uuid}', include_in_schema=False)
async def camera_snapshot(camera_uuid: str):
    manager = get_shared_stream_manager()
    try:
        source = CAMERA_SETTINGS.get(camera_uuid, {}).get('source')
        stream = manager.get_stream(camera_uuid, source)
        max_wait_time = 10
        sleep_time = 0.5
        elapsed_time = 0
        while not stream.is_frame_available() and elapsed_time < max_wait_time:
            time.sleep(sleep_time)
            elapsed_time += sleep_time
        if not stream.is_frame_available():
            raise HTTPException(status_code=404, detail="No frame available")
        frame = stream.get_frame()
        if frame is None:
            raise HTTPException(status_code=500, detail="Failed to read frame")

        # Apply camera settings (brightness/contrast/focus) so snapshot matches live feed
        try:
            cam_settings = CAMERA_SETTINGS.get(camera_uuid, {})
            contrast = cam_settings.get('contrast', 1.0)
            brightness = cam_settings.get('brightness', 1.0)
            focus = cam_settings.get('focus', 1.0)
            frame = cv2.convertScaleAbs(frame, alpha=contrast, beta=int((brightness - 1.0) * 255))
            if focus and focus != 1.0:
                blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=focus)
                frame = cv2.addWeighted(frame, 1.0 + focus, blurred, -focus, 0)
        except Exception:
            # If processing fails, fallback to raw frame
            pass

        _, buffer = cv2.imencode('.jpg', frame)
        return Response(content=buffer.tobytes(), media_type="image/jpeg")
    except Exception as e:
        logger.error("Snapshot error for %s: %s", camera_uuid, e)
        raise


@router.post("x/camera/add")
async def add_camera_ep(request: Request):
    """Add a new camera."""
    data = await request.json()
    nickname = data.get('nickname')
    source = data.get('source')
    if not nickname or not source:
        raise HTTPException(status_code=400, detail="Missing camera nickname or source.")
    camera = await add_camera(source=source, nickname=nickname)
    add_to_config({'camera_settings':
                   {camera['camera_uuid']: {
                    "nickname": camera['nickname'],
                    "source": camera['source'],
                    **DEFAULT_CAMERA_SETTINGS
                    }}
                }
                )
    return {"camera_uuid": camera['camera_uuid'], "nickname": camera['nickname'], "source": camera['source']}


@router.post("/camera/remove")
async def remove_camera_ep(request: Request):
    """Remove a camera."""
    data = await request.json()
    camera_uuid = data.get('camera_uuid')
    if not camera_uuid:
        raise HTTPException(status_code=400, detail="Missing camera_uuid.")
    success = await remove_camera_util(camera_uuid)
    if not success:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return {"message": "Camera removed successfully."}


@router.get("/camera/serial_devices")
async def get_serial_devices_ep():
    """Get a list of available serial devices."""
    devices = find_available_serial_cameras()
    return devices


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
    preview_uuid = f"preview_{uuid.uuid4()}"
    manager = get_shared_stream_manager()
    stream = manager.get_stream(preview_uuid, source)
    max_wait = 50
    wait_count = 0
    while not stream.is_frame_available() and wait_count < max_wait:
        time.sleep(0.1)
        wait_count += 1
    if not stream.is_frame_available():
        manager.release_stream(preview_uuid)
        raise HTTPException(status_code=504, detail="Preview stream failed to start")
    return StreamingResponse(generate_preview_frames(source, preview_uuid),
                             media_type='multipart/x-mixed-replace; boundary=frame')


@router.get("/camera/cameralist", include_in_schema=False)
async def camera_list(request: Request):
    """Get a list of current camera id's."""
    camera_uuid_list = []
    for camera_uuid in CAMERA_SETTINGS:
        camera_uuid_list.append(camera_uuid)
    print(f'{camera_uuid_list=}')
    return {"camera_list": camera_uuid_list}


# config_routes.py
@router.post("/config/add-camera")
async def add_camera_config(request: Request):
    """Add a new camera."""
    data = await request.json()
    nickname = data.get('nickname')
    source = data.get('source')
    if not nickname or not source:
        raise HTTPException(status_code=400, detail="Missing camera nickname or source.")
    camera_uuid = str(uuid.uuid4())
    add_to_config({'camera_settings': {camera_uuid: {
        "nickname": nickname,
        "source": source,
        **DEFAULT_CAMERA_SETTINGS
    }}})
    return {"camera_uuid": camera_uuid, "nickname": nickname, "source": source}


@router.post("/config/remove-camera")
async def remove_camera_config(request: Request):
    """Remove a camera."""
    data = await request.json()
    camera_uuid = data.get('camera_uuid')
    if not camera_uuid or camera_uuid not in CAMERA_SETTINGS:
        raise HTTPException(status_code=400, detail="Missing camera_uuid.")
    try:
        delete_from_config({'camera_settings': camera_uuid})
        if camera_uuid in CAMERA_STATES:
            delete_from_config({'camera_states': camera_uuid})
        return {"success": True}
    except KeyError:
        raise HTTPException(status_code=404, detail="Camera not found.")


@router.get("/config/get-camera-list", include_in_schema=False)
async def config_camera_list(request: Request):
    """Get a list of current camera id's, nickname and source."""
    camera_uuid_list = {}
    for camera_uuid in CAMERA_SETTINGS:
        camera_uuid_list[camera_uuid] = {
            "nickname": CAMERA_SETTINGS[camera_uuid].get("nickname", ""),
            "source": CAMERA_SETTINGS[camera_uuid].get("source", "")
        }
    print(f'{camera_uuid_list=}')
    return {"camera_list": camera_uuid_list}


@router.get("/get/camera-settings", include_in_schema=False)
async def camera_settings(request: Request):
    """Get current camera settings."""
    return {"camera_settings": CAMERA_SETTINGS}


@router.get("/xonfig/get-feed-settings", include_in_schema=False)
async def get_feed_settings():
    """Retrieve current camera feed and detection settings."""
    try:
        config = get_config()
        settings = {
            "stream_max_fps": config.get(SavedConfig.STREAM_MAX_FPS, STREAM_MAX_FPS),
            "stream_jpeg_quality": config.get(SavedConfig.STREAM_JPEG_QUALITY, STREAM_JPEG_QUALITY),
            "stream_max_width": config.get(SavedConfig.STREAM_MAX_WIDTH, STREAM_MAX_WIDTH),
            "detection_interval_ms": config.get(SavedConfig.DETECTION_INTERVAL_MS, DETECTION_INTERVAL_MS),
            "min_sse_dispatch_delay_ms": config.get(SavedConfig.MIN_SSE_DISPATCH_DELAY_MS, MIN_SSE_DISPATCH_DELAY_MS)
        }
        settings["detections_per_second"] = round(1000 / settings["detection_interval_ms"])
        return {"success": True, "settings": settings}
    except Exception as e:
        logger.error("Error loading feed settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load feed settings: {str(e)}"
        )


@router.get("/config/get-countdown-settings", include_in_schema=False)
async def get_countdown_settings():
    """Retrieve countdown settings."""
    return {
        "success": True,
        "countdown_settings": {
            'countdown_action': COUNTDOWN_SETTINGS.get('countdown_action'),
            'countdown_time': COUNTDOWN_SETTINGS.get('countdown_time'),
            'countdown_control': COUNTDOWN_SETTINGS.get('countdown_control')
        }
    }


@router.post("/xconfig/save-countdown-settings ", include_in_schema=False)
async def save_countdown_settings(settings: dict):
    """Save countdown settings."""
    try:
        add_to_config({
            'countdown_settings': {
                'countdown_action': settings['countdown_action'],
                'countdown_time': settings['countdown_time'],
                'countdown_control': settings['countdown_control']
            }
        })
        logger.debug("Countdown settings saved successfully.")
        return {"success": True, "message": "Countdown settings saved successfully."}
    except Exception as e:
        logger.error("Error saving countdown settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save countdown settings: {str(e)}"
        )


@router.post("/config/get-camera-setting", include_in_schema=False)
async def get_camera_setting(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Get the current setting of a specific camera."""
    camera_setting = CAMERA_SETTINGS.get(camera_uuid)
    if camera_setting is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_uuid} not found.")
    return camera_setting


@router.post("/config/get-camera-state", include_in_schema=False)
async def get_camera_state_config(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Get the current state of a specific camera."""
    if camera_uuid not in CAMERA_SETTINGS:
        raise HTTPException(status_code=404, detail=f"Camera {camera_uuid} not found.")
    
    latest_state = CAMERA_STATES[camera_uuid]
    return {
        'live_detection_running': latest_state.get('live_detection_running'),
        'last_result': latest_state.get('last_result'),
        'last_time': latest_state.get('last_time'),
        'defect_active': latest_state.get('defect_active')
    }


@router.post("/config/update-countdown", include_in_schema=False)
async def update_countdown(request: Request,
                            countdown_action: str = Form(...),
                            countdown_time: int = Form(...),
                            countdown_control: str = Form(...)
                          ):
    """Update countdown settings from config."""
    print(f"Received countdown settings update: action={countdown_action}, time={countdown_time}, control={countdown_control}")
    add_to_config({'countdown_settings': {
                            "countdown_action": countdown_action,
                            "countdown_time": countdown_time,
                            "countdown_control": countdown_control
                            }})
    return {"success": True}


# sse_routes.py
class SSEManager:
    def __init__(self):
        self.clients = []
        self.lock = asyncio.Lock()

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
            for client in self.clients:
                await client.put(message)


manager = SSEManager()

broadcast_task = None

async def start_broadcast_loop():
    global broadcast_task
    if broadcast_task is not None:
        return

    async def loop():
        async for packet in outbound_packet_fetch():
            await manager.broadcast(packet)

    broadcast_task = asyncio.create_task(loop())


@router.get("/sse")
async def sse_connect(request: Request):
    """Establish Server-Sent Events connection for real-time updates."""
    await start_broadcast_loop()
    queue = await manager.connect()

    async def send_packet():
        try:
            while True:
                if await request.is_disconnected():
                    logger.warning('sse request disconnected')
                    logger.warning(f'{request}')
                    break
                packet = await queue.get()
                yield packet
        finally:
            await manager.disconnect(queue)

    return EventSourceResponse(send_packet())

"""SRS
@router.post("/sse/stop-polling")
async def stop_polling(request: Request, camera_uuid: str = Body(..., embed=True)):
    stop_and_remove_polling_task(camera_uuid)
    return {"message": "Polling stopped for camera UUID {}".format(camera_uuid)}
"""