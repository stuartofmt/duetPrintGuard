import asyncio
import json
from logger_module import logger
import time
from typing import Dict, Tuple

import cv2
import numpy as np
from PIL import Image
from collections import deque
from copy import deepcopy

from .model_utils import _run_inference

from .shared_video_stream import get_shared_camera_frame
from .mjpeg_source import fetch_snapshot_image

from .config import (STREAM_MAX_FPS,
					 STREAM_JPEG_QUALITY,
					 STREAM_MAX_WIDTH,
					 DETECTION_INTERVAL_MS)
from .config import (CAMERA_SETTINGS,CAMERA_STATES,COUNTDOWN_SETTINGS, DEFAULT_CAMERA_STATE)


from duet_printer import suspend_print_job, duet_send_notification


class StreamOptimizer:
	"""Optimizes video stream frames and detection loops based on configuration."""

	def __init__(self):
		"""Initialize the stream optimizer with empty cache and timing."""
		self._config_cache = {}

	def _get_current_settings(self) -> Dict:
		"""Retrieve or update current stream settings from configuration.

		Returns:
			Dict: A dictionary containing stream settings:
				{
					'max_fps': int,
					'jpeg_quality': int,
					'max_width': int,
					'detection_interval_ms': float,
				}
		"""

		if self._config_cache == {}:
			self._config_cache = {
				'max_fps': STREAM_MAX_FPS,
				'jpeg_quality': STREAM_JPEG_QUALITY,
				'max_width': STREAM_MAX_WIDTH,
				'detection_interval_ms': DETECTION_INTERVAL_MS
			}
		return self._config_cache

	def get_stream_settings(self) -> Dict:
		"""Get the cached stream settings."""
		return self._get_current_settings()

	def optimize_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict]:
		"""Resize frame based on max width and return associated settings.

		Args:
			frame (np.ndarray): The original image frame.

		Returns:
			Tuple[np.ndarray, Dict]: The resized frame and current stream settings.
		"""
		settings = self._get_current_settings()
		max_width = settings['max_width']
		height, width = frame.shape[:2]
		if width > max_width:
			ratio = max_width / width
			new_width = max_width
			new_height = int(height * ratio)
			# pylint: disable=E1101
			frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
		return frame, settings

	def encode_frame(self, frame: np.ndarray) -> bytes:
		"""Encode frame to JPEG with configured quality.

		Args:
			frame (np.ndarray): The frame to encode.

		Returns:
			bytes: The JPEG-encoded byte string.
		"""
		settings = self._get_current_settings()
		jpeg_quality = settings['jpeg_quality']
		# pylint: disable=E1101
		encode_params = [
			cv2.IMWRITE_JPEG_QUALITY, jpeg_quality,
			cv2.IMWRITE_JPEG_OPTIMIZE, 1,
		]
		success, buffer = cv2.imencode('.jpg', frame, encode_params)
		if not success:
			_, buffer = cv2.imencode('.jpg', frame)
		return buffer.tobytes()

	def get_detection_interval(self) -> float:
		"""Get the time interval between detections in seconds."""
		return self._get_current_settings()['detection_interval_ms'] / 1000.0

stream_optimizer = StreamOptimizer()


def create_optimized_frame_generator(camera_uuid: str, camera_state_getter):
	"""Generator yielding optimized JPEG frames for streaming using shared video stream.

	Args:
		camera_uuid (str): The UUID of the camera.

	Yields:
		bytes: Multipart JPEG frame data.
	"""
	# pylint: disable=E1101
	last_frame_time = 0
	frame_count = 0
	max_fps = stream_optimizer.get_stream_settings()['max_fps']
	min_interval = 1.0 / max_fps if max_fps > 0 else 0
	missing_frames = False

	try:
		while True:
			wait = last_frame_time + min_interval - time.time()
			if wait > 0:
				time.sleep(wait) # Until the next frame is due

			frame = get_shared_camera_frame(camera_uuid)
			if frame is None:
				if not missing_frames: # Warn once per outage, not every 0.1 s
					logger.warning("Failed to get frame from shared camera stream %s", camera_uuid)
					missing_frames = True
				time.sleep(0.1)
				continue
			missing_frames = False
			frame, _ = stream_optimizer.optimize_frame(frame)
			frame_bytes = stream_optimizer.encode_frame(frame)
			last_frame_time = time.time()
			frame_count += 1
			yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
			if frame_count % 300 == 0:
				logger.debug("Camera %s: Streamed %d frames", camera_uuid, frame_count)
	except Exception as e:
		logger.error("Error in optimized frame generation for camera %s: %s", camera_uuid, e)

async def create_optimized_detection_loop(app_state, camera_uuid):
	"""
	Asynchronous loop for real-time defect detection on one camera.

	Settings (majority vote, countdown) are read on every pass, so changes on the
	Settings page apply without restarting detection.

	Args:
		app_state: Model and transformation context for detection.
		camera_uuid (str): The UUID of the camera.
	"""
	global CAMERA_SETTINGS, CAMERA_STATES, COUNTDOWN_SETTINGS
	COUNTDOWN_SETTINGS['alert_status'] = 'inactive' # reset alert status

	global _MAJORITY_VOTE, _CAMERA_AGREEMENT
	_MAJORITY_VOTE = {}
	_CAMERA_AGREEMENT = []

	# pylint: disable=E1101
	logger.debug(f'STARTING DETECTION LOOP FOR CAMERA {camera_uuid}')
	while True:
		if CAMERA_STATES.get(camera_uuid, {}).get('live_detection_running') != 'yes':
			break

		if COUNTDOWN_SETTINGS['alert_status'] == 'inactive': # No point in burning CPU
			# HTTP cameras: one snapshot per detection - no continuous stream decoding
			# RTSP cameras: latest frame from the shared video stream
			snapshot_url = CAMERA_SETTINGS[camera_uuid].get('snapshot')
			try:
				if snapshot_url:
					image = await asyncio.to_thread(fetch_snapshot_image, snapshot_url)
				else:
					frame = await asyncio.to_thread(get_shared_camera_frame, camera_uuid)
					image = None if frame is None else Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
			except Exception as e:
				logger.warning("Failed to get frame from camera %s - stopping detection: %s", camera_uuid, e)
				CAMERA_STATES[camera_uuid]['live_detection_running'] = 'no'
				CAMERA_STATES[camera_uuid]['last_result'] = 'Failed to get frame'
				await send_updateCamera_state(camera_uuid)
				break

			if image is None: # Camera did not respond - try again next interval
				logger.warning("No image from camera %s - skipping this detection", camera_uuid)
				await asyncio.sleep(stream_optimizer.get_detection_interval())
				continue

			tensor = app_state.transform(image).unsqueeze(0).to(app_state.device)

			# Run inference on the frame and map the numeric prediction to a label
			try:
				prediction = await _run_inference(app_state.model,
												tensor,
												app_state.prototypes,
												app_state.defect_idx,
												app_state.device)
				numeric = prediction[0] if isinstance(prediction, list) else prediction
			except Exception as e:
				logger.warning("Detection inference error for camera %s: %s", camera_uuid, e)
				numeric = None

			if isinstance(numeric, int) and 0 <= numeric < len(app_state.class_names):
				label = app_state.class_names[numeric]
			else:
				label = 'Error'

			CAMERA_STATES[camera_uuid]['last_time'] = time.time()
			CAMERA_STATES[camera_uuid]['last_result'] = label

			# Every frame goes into the majority vote, so failures are counted within the last
			# window frames. A defect is raised on a failure frame that brings the count up to the threshold.
			settings = CAMERA_SETTINGS[camera_uuid]
			is_failure = isinstance(numeric, int) and numeric == app_state.defect_idx
			failures_in_window = _record_vote(camera_uuid, settings['majority_vote_window'], is_failure)
			passed_majority_vote = is_failure and failures_in_window >= settings['majority_vote_threshold']

			# defect_active is used to display the defect in the UI - one camera is enough
			CAMERA_STATES[camera_uuid]['defect_active'] = passed_majority_vote
			if passed_majority_vote:
				CAMERA_STATES[camera_uuid]['last_result'] = 'DEFECT'
			await send_updateCamera_state(camera_uuid)

			if passed_majority_vote:
				logger.debug(f'{passed_majority_vote=} for camera {camera_uuid}')
				# Check the cameras required by "Which Cameras" agree
				passed_camera_combination = _passed_multi_camera_test(COUNTDOWN_SETTINGS['countdown_control'], camera_uuid)
				logger.debug(f'{passed_camera_combination=}')

				if passed_camera_combination:
					logger.debug('In Alert')
					# reset tests
					_MAJORITY_VOTE = {}
					_CAMERA_AGREEMENT = []
					await _raise_alert(camera_uuid)

		await asyncio.sleep(stream_optimizer.get_detection_interval())


# Increases with every alert, so a countdown only acts on (and waits for) its own alert -
# not a newer one raised after the user dismissed it
_ALERT_ID = 0


def _alert_still_active(alert_id):
	return COUNTDOWN_SETTINGS['alert_status'] == 'active' and _ALERT_ID == alert_id


async def _raise_alert(camera_uuid):
	"""Start the countdown and send notifications, then wait until the alert ends."""
	global _ALERT_ID
	_ALERT_ID += 1
	alert_id = _ALERT_ID
	COUNTDOWN_SETTINGS['alert_status'] = 'active'
	countdown_time = COUNTDOWN_SETTINGS['countdown_time']

	# Start the UI countdown display, and the action if nobody intervenes
	await UI_countdown('start')
	_run_in_background(_take_action_after_countdown(countdown_time, alert_id))

	# Notifications can take several seconds (network retries) - send them without holding up detection
	_run_in_background(asyncio.to_thread(send_defect_notification, camera_uuid))

	# Wait for the countdown, or until the user dismisses the alert (detection then resumes straight away)
	end = time.time() + max(countdown_time, 0)
	while time.time() < end and _alert_still_active(alert_id):
		await asyncio.sleep(0.5)

	# reset alert status
	if _alert_still_active(alert_id): # Dont change if paused or cancelled
		COUNTDOWN_SETTINGS['alert_status'] = 'inactive'


# Background tasks are kept here until they finish - asyncio only keeps weak references to tasks
_BACKGROUND_TASKS = set()


def _run_in_background(coro):
	task = asyncio.create_task(coro)
	_BACKGROUND_TASKS.add(task)
	task.add_done_callback(_BACKGROUND_TASKS.discard)
	return task


def _record_vote(cam_uuid, window, is_failure):
	"""Add this frame's result to the camera's last window results. Returns the failures among them."""
	votes = _MAJORITY_VOTE.setdefault(cam_uuid, deque())
	votes.append(1 if is_failure else 0)
	while len(votes) > max(window, 1):
		votes.popleft()
	return sum(votes)


def _detecting_cameras():
	return [camera_uuid for camera_uuid, state in CAMERA_STATES.items()
			if state.get('live_detection_running') == 'yes']


def _passed_multi_camera_test(countdown_control, camera_uuid):
	"""Any camera: this camera is enough. All cameras: every camera that is detecting has raised a defect."""
	if camera_uuid not in _CAMERA_AGREEMENT:
		_CAMERA_AGREEMENT.append(camera_uuid)

	if countdown_control == 'all_cameras':
		return all(uuid in _CAMERA_AGREEMENT for uuid in _detecting_cameras())
	return True


async def UI_countdown(action):
	"""Send a direct countdown SSE event to the browser.

	This bypasses the ALERT model and the alert queueing path.
	Only the countdown payload is sent to the SSE client.
	"""
	if action == 'start':
		countdown_time = COUNTDOWN_SETTINGS['countdown_time']
	else:
		countdown_time = 0
	
	try:
		from routes.routes import managerSSE
		payload = {
			"event": "countdown_time",
			"data": json.dumps({
				"countdown_time": countdown_time,
				# When the countdown ends, so a browser that connects later gets the time remaining
				"ends_at": time.time() + countdown_time,
				"countdown_action": COUNTDOWN_SETTINGS['countdown_action'],
				"alert_status": COUNTDOWN_SETTINGS['alert_status']
			})
		}
		await managerSSE.broadcast(payload)
		logger.debug("Broadcasted countdown_time SSE event successfully")
	except Exception as e:
		logger.error("Failed to broadcast countdown_time SSE event: %s", e)

async def _take_action_after_countdown(countdown_time, alert_id):
	"""
	Wait for the alert's countdown, then ignore or act on the print job.
	"""
	await asyncio.sleep(max(countdown_time, 0))

	if _alert_still_active(alert_id): # Not dismissed or overridden by the user, and not a newer alert
		match COUNTDOWN_SETTINGS['countdown_action']:
			case 'ignore': # allowing new alerts to be triggered 
				COUNTDOWN_SETTINGS['alert_status'] = 'inactive'
			case 'pause_print':
				await asyncio.to_thread(suspend_print_job, 'pause_print')
				await pause_all_detection()
				COUNTDOWN_SETTINGS['alert_status'] = 'paused'
			case 'cancel_print':
				await asyncio.to_thread(suspend_print_job, 'cancel_print')
				await stop_all_detection()
				COUNTDOWN_SETTINGS['alert_status'] = 'cancelled' # Not reset since print job has been stopped


async def pause_all_detection():
	"""Stop detection on every detecting camera, marking them 'paused' so a resume restarts them."""
	for camera_uuid in _detecting_cameras():
		await stop_live_detection(camera_uuid)
		CAMERA_STATES[camera_uuid]['live_detection_running'] = 'paused'
		await send_updateCamera_state(camera_uuid)


async def stop_all_detection():
	"""Stop detection on every detecting camera."""
	for camera_uuid in _detecting_cameras():
		await stop_live_detection(camera_uuid)


async def resume_all_detection():
	"""Restart detection on every camera that was paused."""
	for camera_uuid, state in list(CAMERA_STATES.items()):
		if state.get('live_detection_running') == 'paused':
			await start_live_detection(camera_uuid)
			await send_updateCamera_state(camera_uuid)


async def _live_detection_loop(app_state, camera_uuid):
	"""Continuously run detection on camera frames and generate alerts using shared video stream.

	This loop reads frames from the shared video stream, runs inference, updates state, 
	and dispatches alerts when defects are detected based on majority vote.

	Args:
		app_state: The application state holding model, transforms, and other context.
		camera_uuid (str): The UUID of the camera to process.
	"""
	global CAMERA_STATES
	# pylint: disable=C0415
	try:
		logger.debug(f'CREATE OPTIMIZED DETECTION LOOP FOR {camera_uuid}')
		await create_optimized_detection_loop(
			app_state,
			camera_uuid
		)
	except asyncio.CancelledError:
		raise
	except Exception as e:
		logger.error("Error in detection loop for camera %s - detection stopped: %s", camera_uuid, e)
		if camera_uuid in CAMERA_STATES: # Not if the camera has been removed
			CAMERA_STATES[camera_uuid]["last_result"] = 'Error in detection loop'
			CAMERA_STATES[camera_uuid]["live_detection_running"] = 'no'
			await send_updateCamera_state(camera_uuid)

	
def default_notification_text(camera_name):
	"""Title and message sent when no ntfy / Pushover title or message is configured.

	Also shown on the config page as the placeholder for those fields.
	"""
	if COUNTDOWN_SETTINGS['countdown_control'] == 'all_cameras':
		title_msg = "duetPrintguard: All cameras"
	else:
		title_msg = f"duetPrintguard: {camera_name}"

	countdown_time = COUNTDOWN_SETTINGS['countdown_time']
	action = COUNTDOWN_SETTINGS['countdown_action']
	if countdown_time <= 0: # The action is taken straight away
		if action == 'pause_print':
			action_msg = "Print has been paused."
		elif action == 'cancel_print':
			action_msg = "Print has been cancelled."
		else:
			action_msg = "Alert has been dismissed automatically."
	elif action == 'pause_print':
		action_msg = f"Print will be paused if not dismissed within {countdown_time} seconds."
	elif action == 'cancel_print':
		action_msg = f"Print will be cancelled if not dismissed within {countdown_time} seconds."
	else:
		action_msg = f"Alert will be dismissed automatically in {countdown_time} seconds if not dismissed manually."
	return title_msg, action_msg


def send_defect_notification(camera_uuid):
	"""Send the defect notifications (macro, ntfy, Pushover). Blocking - runs in a thread.

	The alert status is set by _raise_alert, not here - this may run after the user has dismissed the alert.
	"""
	logger.debug("Attempting to send defect notification")

	title_msg, action_msg = default_notification_text(CAMERA_SETTINGS[camera_uuid]['nickname'])
	notification = {'title': title_msg,'body': action_msg}

	if duet_send_notification(notification):
		logger.debug("Notification send completed")
	else:
		logger.error("Unexpected error sending notification")

# app.state, saved by the start route so autostart and resume can start detection
_SAVED_REQUEST = None

def save_app_state_request(app_state):
	global _SAVED_REQUEST
	_SAVED_REQUEST = app_state


async def start_live_detection(camera_uuid,request=None):
	"""Start continuous live detection on a specified camera."""
	global CAMERA_STATES, _SAVED_REQUEST
	if request is None:
		logger.debug(f'Using saved request value for start_live_detection')
		request = _SAVED_REQUEST # we just pass through app.state

	if camera_uuid not in CAMERA_SETTINGS:
		return {"success": False, "message": f"Camera {camera_uuid} not found"}
	if request is None or getattr(request, 'prototypes', None) is None:
		logger.error("Cannot start detection - the detection model did not load (see earlier errors in the log)")
		return {"success": False, "message": "The detection model is not loaded - see the plugin log"}

	camera_state = CAMERA_STATES.get(camera_uuid)
	if camera_state and camera_state["live_detection_running"] == 'yes':
		return {"success": True, "message": f"Live detection already running for camera {camera_uuid}"}

	CAMERA_STATES[camera_uuid] = deepcopy(DEFAULT_CAMERA_STATE) # Precaution vs shallow copy

	try:
		task = asyncio.create_task(_live_detection_loop(request, camera_uuid))
		
		CAMERA_STATES[camera_uuid]['live_detection_running'] = 'yes'
		CAMERA_STATES[camera_uuid]['live_detection_task'] = task
		CAMERA_STATES[camera_uuid]['last_time'] = time.time()
		COUNTDOWN_SETTINGS['alert_status'] = 'inactive' # reset global countdown status when starting detection

	except Exception as e:
		logger.error(f"Error starting live detection for camera {camera_uuid} with request {request}: {e}")
		return {"success": False, "message": f"Failed to start live detection for camera {camera_uuid}"}

	return {"success": True, "message": f"Live detection started for camera {camera_uuid}"}


async def stop_live_detection(camera_uuid):
	"""Stop continuous live detection on a specified camera."""
	global CAMERA_STATES

	# Ensure countdown is stopped when live detection is stopped
	try:
		# If detection isn't running, still ensure the UI countdown is stopped
		if CAMERA_STATES.get(camera_uuid, {}).get('live_detection_running') != 'yes':
			# reset any global countdown status
			COUNTDOWN_SETTINGS['alert_status'] = 'inactive'
			# broadcast a stop to UI so new SSE clients won't see an active countdown
			await UI_countdown('stop')
			return {"message": f"Live detection not running for camera {camera_uuid}"}

		# Cancel running detection task
		live_detection_task = CAMERA_STATES[camera_uuid].get('live_detection_task')
		if live_detection_task:
			try:
				live_detection_task.cancel()
				CAMERA_STATES[camera_uuid] = deepcopy(DEFAULT_CAMERA_STATE) # Precaution vs shallow copy
				# reset global countdown status
				COUNTDOWN_SETTINGS['alert_status'] = 'inactive'
				# ensure UI is informed to stop any countdown
				await UI_countdown('stop')
				logger.debug("Stopped live detection task for camera %s", camera_uuid)
			except Exception as e:
				logger.error("Error stopping live detection task for camera %s: %s", camera_uuid, e)
		
		# Dont need to do this on start as its updated in the detection loop
		# This is just to ensure the UI is updated if the detection loop was stopped externally
		CAMERA_STATES[camera_uuid]['live_detection_running'] = 'no'
		await send_updateCamera_state(camera_uuid)

		return {"message": f"Live detection stopped for camera {camera_uuid}"}

	except Exception as outer_e:
		logger.error("Unexpected error in stop_live_detection for %s: %s", camera_uuid, outer_e)
		# attempt best-effort cleanup
		try:
			COUNTDOWN_SETTINGS['alert_status'] = 'inactive'
			await UI_countdown('stop')
		except Exception:
			pass
		return {"message": f"Live detection stopped for camera {camera_uuid} (with errors)"}

async def send_updateCamera_state(camera_uuid):
	"""Send a direct camera state SSE event to the browser.

	This bypasses the ALERT model and the alert queueing path.
	Only the camera state payload is sent to the SSE client.
	"""
	try:
		from routes.routes import managerSSE
		# Only send relevant camera state fields to the UI
		# Exclude any non-serializable objects
		state = {k: v for k, v in CAMERA_STATES[camera_uuid].items() if k not in {'live_detection_task'}}
		payload = {
			"event": "camera_updated",
			"data": json.dumps({
				"camera_uuid": camera_uuid,
				"state": state
			})
		}
		await managerSSE.broadcast(payload)
		logger.debug(f"Broadcast camera_updated for {camera_uuid}")
	except Exception as e:
		logger.error("Failed to broadcast cameraStateUpdated SSE event for camera %s: %s", camera_uuid, e)


