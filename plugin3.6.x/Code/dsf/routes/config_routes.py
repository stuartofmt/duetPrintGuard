from logger_module import logger
import time
import uuid

from fastapi import APIRouter, Body, HTTPException, Request

from utils.config import CAMERA_SETTINGS, DEFAULT_CAMERA_SETTINGS, CAMERA_STATES, update_config
from utils.config import (STREAM_MAX_FPS,
                            STREAM_JPEG_QUALITY, STREAM_MAX_WIDTH,
                            DETECTION_INTERVAL_MS,
                            MIN_SSE_DISPATCH_DELAY_MS,COUNTDOWN_ACTION, COUNTDOWN_TIME, COUNTDOWN_CONTROL,
                            )
from utils.camera_utils import update_camera_state

from models import  SavedConfig, CountdownSettings

router = APIRouter()

@router.post("/config/add-camera")
async def add_camera_ep(request: Request):
    """Add a new camera."""
    data = await request.json()
    nickname = data.get('nickname')
    source = data.get('source')
    if not nickname or not source:
        raise HTTPException(status_code=400, detail="Missing camera nickname or source.")
    '''SRS What happens here ??'''
    #camera = await add_camera(source=source, nickname=nickname)
    camera_uuid = str(uuid.uuid4()) 
    # Initialize camera settings with defaults
    update_config({'camera_settings': {camera_uuid: {
        "nickname": nickname,
        "source": source,
        **DEFAULT_CAMERA_SETTINGS
	}}})

    return {"camera_uuid": camera_uuid, "nickname": nickname, "source": source}


@router.post("/config/remove-camera")
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


@router.get("/config/get-camera-list", include_in_schema=False)
async def camera_list(request: Request):
    """Get a list of current camera id's, nickname ansd source

    Args:
        request (Request): The FastAPI request object.

    Returns:
        Dict: A dictionary containing a list of camera UUIDs, nicknames, and sources.
    """
    # pylint: disable=import-outside-toplevel
    camera_uuid_list = {}
    for camera_uuid in CAMERA_SETTINGS:
        camera_uuid_list[camera_uuid] = {
            "nickname": CAMERA_SETTINGS[camera_uuid].get("nickname", ""),
            "source": CAMERA_SETTINGS[camera_uuid].get("source", "")
        }
    print(f'{camera_uuid_list=}')
    return {"camera_list": camera_uuid_list}

@router.get("/get/camerasettings", include_in_schema=False)
async def camera_settings(request: Request):
    """Get a list of current camera settings

    Args:
        request (Request): The FastAPI request object.

    Returns:
        dict of camera settings
    """
    # pylint: disable=import-outside-toplevel
    return {"camera_settings": CAMERA_SETTINGS}


@router.get("/config/get-feed-settings", include_in_schema=False)
async def get_feed_settings():
    """Retrieve current camera feed and detection settings.

    Returns:
        dict: Current feed settings including FPS, quality, detection intervals,
              polling rates, and calculated detections per second.

    Raises:
        HTTPException: If loading settings fails due to configuration errors.
    """
    try:
        config = get_config()
        # pylint:disable=import-outside-toplevel
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
    """Retrieve countdown settings.

    Returns:
        dict: Current countdown_action and countdown_time

    Raises:
        HTTPException: If loading settings fails due to configuration errors.
    """
    try:
        config = get_config()
        config = config.get(SavedConfig.COUNTDOWN, {})

        # pylint:disable=import-outside-toplevel

        
        countdown = {
            SavedConfig.COUNTDOWN_ACTION.value: config.get(SavedConfig.COUNTDOWN_ACTION, COUNTDOWN_ACTION),
            SavedConfig.COUNTDOWN_TIME.value: config.get(SavedConfig.COUNTDOWN_TIME, COUNTDOWN_TIME),
            SavedConfig.COUNTDOWN_CONTROL.value: config.get(SavedConfig.COUNTDOWN_CONTROL, COUNTDOWN_CONTROL)
        }
        print(countdown)
        return {"success": True, "countdown": countdown}
    except Exception as e:
        logger.error("Error loading countdown settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load countdown settings: {str(e)}"
        )
    
#SRS Unused for now - may want to add back in later if we want a non js way to update these settings    
@router.post("/config/save-countdown-settings ", include_in_schema=False)
async def save_countdown_settings(settings: CountdownSettings):
    """Save countdown settings to configuration.

    Args:
        settings (CountdownSettings): Countdown configuration settings including action, time, and condition.

    Returns:
        dict: Success status and message indicating settings were saved.

    Raises:
        HTTPException: If saving fails due to validation or storage errors.
    """
    try:
        config_data = {
            SavedConfig.COUNTDOWN: {
                SavedConfig.COUNTDOWN_ACTION: settings.countdown_action,
                SavedConfig.COUNTDOWN_TIME: settings.countdown_time,
                SavedConfig.COUNTDOWN_CONTROL: settings.countdown_control
            }
        }
        update_config(config_data)
        #ream_optimizer.invalidate_cache()
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
    """Get the current setting of a specific camera.
    """

    camera_setting = CAMERA_SETTINGS[camera_uuid]

    return camera_setting

@router.post("/config/get-camera-state", include_in_schema=False)
async def get_camera_state(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Get the current state of a specific camera.
    """
    camera_state = CAMERA_STATES[camera_uuid]

    return camera_state
