import time
from logger_module import logger

from fastapi import Form, Request, APIRouter
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse

from utils.config import (STREAM_MAX_FPS,
							STREAM_JPEG_QUALITY, STREAM_MAX_WIDTH,
							MIN_SSE_DISPATCH_DELAY_MS,
							COUNTDOWN_TIME, COUNTDOWN_ACTION, COUNTDOWN_CONTROL,CAMERA_SETTINGS,
							update_config, get_config, reset_all)
from utils.camera_utils import update_camera_state
from utils.camera_state_manager import get_camera_state_manager
# from utils.stream_utils import stream_optimizer
from models import FeedSettings, SavedConfig

router = APIRouter()

@router.get("/settings", include_in_schema=False)
async def serve_index(request: Request):
	"""Serve the main index page with camera states and configuration.

	Args:
		request (Request): The FastAPI request object.

	Returns:
		TemplateResponse: Rendered index.html template with camera states and settings.
	"""
	# pylint: disable=import-outside-toplevel
	from app import templates
	#camera_state_manager = get_camera_state_manager()
	#camera_uuids = await camera_state_manager.get_all_camera_uuids()
	print(f'HERE BE CAMERAS {CAMERA_SETTINGS}')
	if len(CAMERA_SETTINGS) <= 0:
		logger.warning("No camera UUIDs found, attempting to initialize cameras...")
		#SRS - Assume startup or bad state - reset all keys config etc
		#reset_all()
		#camera_uuids = await camera_state_manager.get_all_camera_uuids()
	#camera_states = {}
	#for cam_uuid in camera_uuids:
		#camera_states[cam_uuid] = await camera_state_manager.get_camera_state(cam_uuid)
	return templates.TemplateResponse("settings.html", {
		"request": request
	})
	'''
	return templates.TemplateResponse("settings.html", {
		"camera_states": camera_states,
		"request": request,
		"current_time": time.time(),
	})
	'''

# pylint: disable=unused-argument
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
	"""Update camera settings and detection parameters.

	Args:
		request (Request): The FastAPI request object.
		camera_uuid (str): UUID of the camera to update settings for.
		sensitivity (float): Detection sensitivity level.
		brightness (float): Camera brightness setting.
		contrast (float): Camera contrast setting.
		focus (float): Camera focus setting.
		majority_vote_threshold (int): Number of detections needed for majority vote.
		majority_vote_window (int): Time window for majority vote calculation.

	Returns:
		RedirectResponse: Redirect to the main index page.
	"""

	'''
	#SRS Not sure if this is ultimately needed
	await update_camera_state(camera_uuid, {
		"sensitivity": sensitivity,
		"brightness": brightness,
		"contrast": contrast,
		"focus": focus,

		"majority_vote_threshold": majority_vote_threshold,
		"majority_vote_window": majority_vote_window
	})
	'''
	update_config({'camera_settings': {camera_uuid: {
		"sensitivity": sensitivity,
		"brightness": brightness,
		"contrast": contrast,
		"focus": focus,
		"majority_vote_threshold": majority_vote_threshold,
		"majority_vote_window": majority_vote_window
	}}})
	return RedirectResponse("/settings", status_code=303)

# pylint: disable=unused-argument
@router.post("/settings/update-countdown", include_in_schema=False)
async def update_countdown(request: Request,
							countdown_action: str = Form(...),
							countdown_time: int = Form(...),
							countdown_control: str = Form(...)
						  ):
	"""Update camera settings and detection parameters.

	Args:
		request (Request): The FastAPI request object.
		majority_vote_threshold (int): Number of detections needed for majority vote.
		majority_vote_window (int): Time window for majority vote calculation.

	Returns:
		RedirectResponse: Redirect to the main index page.
	"""
	print(f"Received countdown settings update: action={countdown_action}, time={countdown_time}, control={countdown_control}")     
	#for camera_uuid in await get_camera_state_manager().get_all_camera_uuids():
	#    print(f"Updating countdown settings for camera {camera_uuid}: action={countdown_action}, time={countdown_time}, control={countdown_control}")    
	#await update_camera_state(camera_uuid, {
	update_config({'countdown_settings': {
							"countdown_action": countdown_action,
							"countdown_time": countdown_time,
							"countdown_control": countdown_control
							}})
	
	return RedirectResponse("/settings", status_code=303)
