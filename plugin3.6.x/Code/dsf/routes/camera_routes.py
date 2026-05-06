from logger_module import logger
import time
import uuid

import cv2  # pylint: disable=E0401
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse, Response

#from utils.camera_utils import (add_camera, find_available_serial_cameras,
#                                  get_camera_state)
from utils.camera_utils import (find_available_serial_cameras,
                                  get_camera_state)
from utils.camera_utils import remove_camera as remove_camera_util
from utils.shared_video_stream import get_shared_stream_manager
from utils.stream_utils import generate_frames
from utils.camera_state_manager import get_camera_state_manager
from utils.config import CAMERA_SETTINGS,DEFAULT_CAMERA_SETTINGS,update_config

router = APIRouter()

@router.post("/camera/state", include_in_schema=False)
async def get_camera_state_ep(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Get the current state of a specific camera.
    """
    logger.debug('entered get_camera_state_ep with camera_uuid: %s', camera_uuid) #  at least every n seconds by index.js
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
    """Stream live camera feed for a specific camera.
    """
    return StreamingResponse(generate_frames(camera_uuid),
                             media_type='multipart/x-mixed-replace; boundary=frame')


@router.get('/camera/snapshot/{camera_uuid}', include_in_schema=False)
async def camera_snapshot(camera_uuid: str):
    manager = get_shared_stream_manager()

    try:
        # 🔥 YOU MUST GET SOURCE HERE
        # camera_state = await get_camera_state(camera_uuid)
        # source = camera_state.source   # ← adjust if different field name
        # SRS
        source = CAMERA_SETTINGS.get(camera_uuid, {}).get('source')

        # ✅ NOW create stream correctly
        stream = manager.get_stream(camera_uuid, source)

        # Wait for frame
        max_wait_time = 10  # seconds
        sleep_time = 0.5  # seconds between checks
        elapsed_time = 0 # seconds

        while not stream.is_frame_available() and elapsed_time < max_wait_time:
            time.sleep(sleep_time)
            elapsed_time += sleep_time

        if not stream.is_frame_available():
            raise HTTPException(status_code=404, detail="No frame available")

        frame = stream.get_frame()
        if frame is None:
            raise HTTPException(status_code=500, detail="Failed to read frame")

        _, buffer = cv2.imencode('.jpg', frame)
        return Response(content=buffer.tobytes(), media_type="image/jpeg")

    except Exception as e:
        logger.error("Snapshot error for %s: %s", camera_uuid, e)
        raise

@router.post("/camera/add")
async def add_camera_ep(request: Request):
    """Add a new camera."""
    data = await request.json()
    nickname = data.get('nickname')
    source = data.get('source')
    if not nickname or not source:
        raise HTTPException(status_code=400, detail="Missing camera nickname or source.")
    '''SRS What happens here ??'''
    camera = await add_camera(source=source, nickname=nickname)
    # Initialize camera settings with defaults
    update_config({'camera_settings':
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


def generate_preview_frames(source: str):
    """Generate frames for camera preview using shared video stream.
    """
    preview_uuid = f"preview_{uuid.uuid4()}"
    manager = get_shared_stream_manager()
    try:
        stream = manager.get_stream(preview_uuid, source)
        max_wait = 50
        wait_count = 0
        while not stream.is_frame_available() and wait_count < max_wait:
            time.sleep(0.1)
            wait_count += 1
        if not stream.is_frame_available():
            logger.error("Failed to get initial frame from source: %s", source)
            return
        while True:
            frame = stream.get_frame()
            if frame is None:
                logger.warning("Failed to get frame from source: %s", source)
                time.sleep(0.1)
                continue
            _, buffer = cv2.imencode('.jpg', frame)
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
    """Stream live camera preview for a specific source without registration.
    """
    return StreamingResponse(generate_preview_frames(source),
                             media_type='multipart/x-mixed-replace; boundary=frame')

@router.get("/camera/cameralist", include_in_schema=False)
async def camera_list(request: Request):
    """Get a list of current camera id's

    Args:
        request (Request): The FastAPI request object.

    Returns:
        list of camera UUID
    """
    # pylint: disable=import-outside-toplevel
    camera_uuid_list = []
    for camera_uuid in CAMERA_SETTINGS:
        camera_uuid_list.append(camera_uuid)
    print(f'{camera_uuid_list=}')
    return {"camera_list": camera_uuid_list}
    '''
    camera_state_manager = get_camera_state_manager()
    camera_uuids = await camera_state_manager.get_all_camera_uuids()
    print(f'{camera_uuids= }')
    return {"camera_list": camera_uuids}
    '''
