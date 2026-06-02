"""Consolidated FastAPI routes moved from the previous route modules."""


import asyncio
import time
import uuid
import sys
import glob
from copy import deepcopy

from fastapi import APIRouter, Body, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, Response, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from logger_module import logger

from duet_printer import suspend_print_job

import cv2

from utils.config import (
	CAMERA_SETTINGS,
	CAMERA_STATES,
	DEFAULT_CAMERA_SETTINGS,
	COUNTDOWN_SETTINGS,
	add_to_config,
	delete_from_config
)
from utils.shared_video_stream import get_shared_stream_manager
from utils.stream_utils import UI_countdown, start_live_detection, stop_live_detection, save_request, create_optimized_frame_generator

router = APIRouter()


def find_available_serial_cameras() -> list[str]:
	"""Find all available serial camera devices.

	Returns:
		list[str]: device paths or index strings for available cameras.
	"""
	logger.debug("INFO: Running on platform: %s", sys.platform)
	if sys.platform.startswith('linux'):
		logger.debug("INFO: Detected Linux platform. Searching for /dev/video* devices.")
		device_paths = glob.glob('/dev/video*')
		if device_paths:
			logger.debug("INFO: Found device paths: %s", device_paths)
			return sorted(device_paths)
		else:
			logger.warning("WARN: No /dev/video* devices found. Falling back to index probing.")
	api_preference = cv2.CAP_ANY
	if sys.platform == "win32":
		api_preference = cv2.CAP_DSHOW
	available_indices = []
	index = 0
	while len(available_indices) < 10:
		cap = cv2.VideoCapture(index, api_preference)
		if cap.isOpened():
			logger.debug("INFO: Camera found at index: %s", index)
			available_indices.append(str(index))
			cap.release()
		else:
			logger.debug("INFO: No camera found at index: %s", index)
			cap.release()
			break
		index += 1
	return available_indices

# alert_routes.py
@router.post("/countdown/action")
async def alert_response(request: Request,
						 action = Body(..., embed=True)):
	"""
	Handle alert response actions including ignore, cancel, and pause resume.
	Can be raised m the UI at any time independent of the alert's countdown status
	"""

	await UI_countdown('stop') #Stop the countdown timer on the UI immediately when an action is taken

	global COUNTDOWN_SETTINGS
	match action:
		case 'ignore': # allowing new alerts to be triggered 
			COUNTDOWN_SETTINGS['alert_status'] = 'inactive'
		case 'pause_print':
			COUNTDOWN_SETTINGS['alert_status'] = 'paused'
			suspend_print_job(action)
			for camera_uuid,settings in CAMERA_STATES.items():
				if settings['live_detection_running'] == 'yes': # only pause cameras that are currently running
					await stop_live_detection(camera_uuid)
					CAMERA_STATES[camera_uuid]['live_detection_running'] = 'paused' # Need cuz stop sets to inacive
		case 'resume_print':
			COUNTDOWN_SETTINGS['alert_status'] = 'resumed'
			suspend_print_job(action)
			for camera_uuid,settings in CAMERA_STATES.items():
				if settings['live_detection_running'] == 'paused':
					await start_live_detection(camera_uuid)
			COUNTDOWN_SETTINGS['alert_status'] = 'inactive' # reset after action
		case 'cancel_print':
			COUNTDOWN_SETTINGS['alert_status'] = 'cancelled' # Not reset since print job has been stopped
			suspend_print_job(action)
			for camera_uuid,settings in CAMERA_STATES.items():
				if settings['live_detection_running'] == 'yes':
					await stop_live_detection(camera_uuid)


# index_routes.py
@router.get("/index", include_in_schema=False)
async def serve_index(request: Request):
	"""Serve the main index page."""
	from app import templates
	return templates.TemplateResponse("index.html", {
		"request": request
	})


# settings_routes.py
@router.get("/settings", include_in_schema=False)
async def serve_settings(request: Request):
	"""Serve the settings page."""
	from app import templates
	return templates.TemplateResponse("settings.html", {
		"request": request
	})


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
async def serve_camera_stream(request: Request, nickname: str):
	"""Serve an HTML page for a named camera stream."""
	camera_uuid = get_camera_uuid_by_nickname(nickname)
	if not camera_uuid:
		raise HTTPException(status_code=404, detail="Camera not found")
	from app import templates
	return templates.TemplateResponse("stream.html", {
		"request": request,
		"camera_uuid": camera_uuid,
		"nickname": CAMERA_SETTINGS[camera_uuid].get('nickname', nickname)
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

@router.post("/settings/update_autostart", include_in_schema=False)
async def update_autostart(request: Request):
	"""Update camera autostart setting."""
	data = await request.json()
	camera_uuid = data.get('camera_uuid')
	checkbox = data.get('autostart')
	if isinstance(checkbox, bool):
		autostart = checkbox
	elif isinstance(checkbox, str):
		autostart = checkbox.lower() in ("on", "true", "1")
	else:
		autostart = False
	if not camera_uuid:
		raise HTTPException(status_code=400, detail="Missing camera_uuid")
	add_to_config({'camera_settings': {camera_uuid: {
		"autostart": autostart
	}}})
	return {"success": True, "autostart": autostart}




@router.post("/settings/update-countdown", include_in_schema=False)
async def update_settings_countdown(request: Request,
							countdown_action: str = Form(...),
							countdown_time: int = Form(...),
							countdown_control: str = Form(...)
						  ):
	"""Update countdown settings from the settings page."""
	add_to_config({'countdown_settings': {
							"countdown_action": countdown_action,
							"countdown_time": countdown_time,
							"countdown_control": countdown_control
							}})
	return RedirectResponse("/settings", status_code=303)


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


@router.get('/camera/stream/{camera_uuid}', include_in_schema=False)
async def camera_stream(camera_uuid: str):
	if camera_uuid not in CAMERA_SETTINGS:
		raise HTTPException(status_code=404, detail="Camera not found")
	return StreamingResponse(
		create_optimized_frame_generator(camera_uuid, lambda: None),
		media_type='multipart/x-mixed-replace; boundary=frame'
	)


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
	default_camera_settings = deepcopy(DEFAULT_CAMERA_SETTINGS) # Precaution vs shallow copy
	add_to_config({'camera_settings': {camera_uuid: {
		"nickname": nickname,
		"source": source,
		**default_camera_settings
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
		#first shutdown the camera feed if it's running
		from utils.shared_video_stream import get_shared_stream_manager
		manager = get_shared_stream_manager()
		manager.cleanup_all()
		logger.debug("Cleaned up camera resources successfully.")
		delete_from_config({'camera_settings': camera_uuid})
		if camera_uuid in CAMERA_STATES:
			delete_from_config({'camera_states': camera_uuid})
		return {"success": True}
	except KeyError:
		return {"success": False}


@router.get("/config/get-camera-list", include_in_schema=False)
async def config_camera_list(request: Request):
	"""Get a list of current camera id's, nickname and source."""
	try:
		camera_uuid_list = {}
		for camera_uuid in CAMERA_SETTINGS:
			camera_uuid_list[camera_uuid] = {
				"nickname": CAMERA_SETTINGS[camera_uuid].get("nickname", ""),
				"source": CAMERA_SETTINGS[camera_uuid].get("source", ""),
				"autostart": CAMERA_SETTINGS[camera_uuid].get("autostart", False)
			}
		logger.debug(f'{camera_uuid_list=}')
		return {"success": True, "list": camera_uuid_list}
	except:
		return {"success": False}


@router.get("/config/get-countdown-settings", include_in_schema=False)
async def get_countdown_settings(request: Request):
	"""Retrieve countdown settings."""
	try:
		settings = COUNTDOWN_SETTINGS
		return {"success": True, "settings": settings}
	except:
		return {"success": False}

@router.post("/config/get-camera-setting", include_in_schema=False)
async def get_camera_setting(request: Request, camera_uuid: str = Body(..., embed=True)):
	"""Get the current setting of a specific camera."""
	try:
		setting = CAMERA_SETTINGS.get(camera_uuid)
		return {"success": True, "setting": setting}
	except:
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
	"""Update countdown settings from config."""
	try:
		add_to_config({'countdown_settings': {
								"countdown_action": countdown_action,
								"countdown_time": countdown_time,
								"countdown_control": countdown_control
								}})
		return {"success": True}
	except:
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

broadcast_task = None

async def outbound_packet_fetch():
	"""Async generator for outbound SSE packets.
	
	Currently unused as broadcasts are handled through direct calls to managerSSE.broadcast().
	This exists to prevent NameError in start_broadcast_loop().
	"""
	while False:
		yield  # This loop never executes, but makes this an async generator

async def start_broadcast_loop():
	global broadcast_task
	if broadcast_task is not None:
		return

	async def loop():
		async for packet in outbound_packet_fetch():
			await managerSSE.broadcast(packet)

	broadcast_task = asyncio.create_task(loop())


@router.get("/sse")
async def sse_connect(request: Request):
	"""Establish Server-Sent Events connection for real-time updates."""
	await start_broadcast_loop()
	queue = await managerSSE.connect()

	async def send_packet():
		try:
			# Send current countdown state to new client if one is active
			if managerSSE.last_countdown_state is not None:
				yield managerSSE.last_countdown_state
			
			while True:
				if await request.is_disconnected():
					logger.warning('sse request disconnected')
					logger.warning(f'{request}')
					break
				packet = await queue.get()
				yield packet
		finally:
			await managerSSE.disconnect(queue)

	return EventSourceResponse(send_packet())



# detection_routes.py
@router.post("/detect/live/start")
async def starting_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
	"""Start continuous live detection on a specified camera."""
	try:
		save_request(request)
		await start_live_detection(camera_uuid)
	except Exception as e:
		logger.error("Error starting live detection for camera %s: %s", camera_uuid, e)
		return {"success": False, "message": f"Failed to start live detection for camera {camera_uuid}"}

	return {"success": True, "message": f"Live detection started for camera {camera_uuid}"}


@router.post("/detect/live/stop")
async def stopping_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
	"""Stop continuous live detection on a specified camera."""
	try:
		await stop_live_detection(camera_uuid)
	except Exception as e:
			logger.error("Error stopping live detection task for camera %s: %s", camera_uuid, e)

	return {"message": f"Live detection stopped for camera {camera_uuid}"}
