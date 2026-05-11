import time
from logger_module import logger

from fastapi import Form, Request, APIRouter
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse

from utils.config import (STREAM_MAX_FPS,
                            STREAM_JPEG_QUALITY, STREAM_MAX_WIDTH,
                            DETECTION_INTERVAL_MS,
                            add_to_config, get_config)
from utils.camera_utils import update_camera_state
from utils.camera_state_manager import get_camera_state_manager
from utils.stream_utils import stream_optimizer
from models import FeedSettings, SavedConfig

router = APIRouter()

@router.get("/index", include_in_schema=False)
async def serve_index(request: Request):
    """Serve the main index page with camera states and configuration.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        TemplateResponse: Rendered index.html template with camera states and settings.
    """
    # pylint: disable=import-outside-toplevel
    from app import templates
    camera_state_manager = get_camera_state_manager()
    camera_uuids = await camera_state_manager.get_all_camera_uuids()
    if not camera_uuids:
        logger.warning("No camera UUIDs found, Check Settings...")
        #SRS - dont initialize in this UI
        #camera_uuids = await camera_state_manager.get_all_camera_uuids()
    camera_states = {}
    for cam_uuid in camera_uuids:
        camera_states[cam_uuid] = await camera_state_manager.get_camera_state(cam_uuid)
    return templates.TemplateResponse("index.html", {
        "camera_states": camera_states,
        "request": request,
        "current_time": time.time(),
    })

# pylint: disable=unused-argument
@router.post("/index", include_in_schema=False)
async def update_settings(request: Request,
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
    """Update camera settings and detection parameters.

    Args:
        request (Request): The FastAPI request object.
        camera_uuid (str): UUID of the camera to update settings for.
        sensitivity (float): Detection sensitivity level.
        brightness (float): Camera brightness setting.
        contrast (float): Camera contrast setting.
        focus (float): Camera focus setting.
        countdown_time (int): Alert countdown duration in seconds.
        countdown_action (str): Action to take when countdown expires.
        majority_vote_threshold (int): Number of detections needed for majority vote.
        majority_vote_window (int): Time window for majority vote calculation.

    Returns:
        RedirectResponse: Redirect to the main index page.
    """
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
