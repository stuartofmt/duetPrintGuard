import asyncio
import json
from logger_module import logger
import time
from typing import Dict, Tuple

import cv2
import numpy as np
from PIL import Image
from copy import deepcopy

from .model_utils import _run_inference

from .shared_video_stream import get_shared_camera_frame

from .config import (STREAM_MAX_FPS,
					 STREAM_JPEG_QUALITY,
					 STREAM_MAX_WIDTH,
					 DETECTION_INTERVAL_MS)
from .config import (CAMERA_SETTINGS,CAMERA_STATES,COUNTDOWN_SETTINGS, DEFAULT_CAMERA_STATE)

import uuid

from duet_printer import get_printer_config, suspend_print_job, duet_send_notification


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
			'''SRS Loops thrrough here like a banchee every time - need to optimize'''
		return self._config_cache

	def get_stream_settings(self) -> Dict:
		"""Get the cached stream settings."""
		return self._get_current_settings()

	def should_limit_fps(self, last_frame_time: float) -> bool:
		"""Determine if streaming should pause to respect max FPS.

		Args:
			last_frame_time (float): Timestamp of the last streamed frame.

		Returns:
			bool: True if waiting is needed, False otherwise.
		"""
		settings = self._get_current_settings()
		max_fps = settings['max_fps']
		if max_fps <= 0:
			return False
		min_frame_interval = 1.0 / max_fps
		return (time.time() - last_frame_time) < min_frame_interval

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
		'''
		if settings['is_tunnel_mode']:
			encode_params.extend([cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
		'''
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

	try:
		while True:
			if stream_optimizer.should_limit_fps(last_frame_time):
				time.sleep(0.001)
				continue

			camera_state = CAMERA_SETTINGS[camera_uuid] 
			logger.debug(f'############# Camera {camera_uuid} - Optimized Frame Generation - State: {camera_state}')
			contrast = CAMERA_SETTINGS.get(camera_uuid).get('contrast')
			brightness = CAMERA_SETTINGS.get(camera_uuid).get('brightness')
			focus = CAMERA_SETTINGS.get(camera_uuid).get('focus')

			frame = get_shared_camera_frame(camera_uuid)
			if frame is None:
				logger.warning("Failed to get frame from shared camera stream %s", camera_uuid)
				time.sleep(0.1)
				continue
			frame = cv2.convertScaleAbs(frame, alpha=contrast, beta=int((brightness - 1.0) * 255))
			if focus and focus != 1.0:
				blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=focus)
				frame = cv2.addWeighted(frame, 1.0 + focus, blurred, -focus, 0)
			frame, settings = stream_optimizer.optimize_frame(frame)
			frame_bytes = stream_optimizer.encode_frame(frame)
			last_frame_time = time.time()
			frame_count += 1
			yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
			if frame_count % 300 == 0:
				settings = stream_optimizer.get_stream_settings()
				logger.debug("Camera %s: Streamed %d frames, mode: %s",
							camera_uuid, frame_count,
							"tunnel" if settings['is_tunnel_mode'] else "local")
	except Exception as e:
		logger.error("Error in optimized frame generation for camera %s: %s", camera_uuid, e)

async def create_optimized_detection_loop(app_state, camera_uuid):
	"""
	Asynchronous loop for real-time defect detection with optimizations using shared video stream.

	Args:
		app_state: Model and transformation context for detection.
		camera_uuid (str): The UUID of the camera.
		get_camera_state_sync_func (callable): Function to get camera state synchronously.
		update_functions (dict): A mapping of update function names to coroutines,
			e.g., {'update_camera_state': ..., 'update_camera_detection_history': ...}.
	"""
	global CAMERA_SETTINGS, CAMERA_STATES, COUNTDOWN_SETTINGS
	COUNTDOWN_SETTINGS['alert_status'] = 'inactive' # reset alert status
	detection_count = 0

	majority_vote_window = CAMERA_SETTINGS[camera_uuid]['majority_vote_window']
	majority_vote_threshold = CAMERA_SETTINGS[camera_uuid]['majority_vote_threshold']
	countdown_control = COUNTDOWN_SETTINGS['countdown_control']
	countdown_time = COUNTDOWN_SETTINGS['countdown_time']
	num_cameras = len(CAMERA_SETTINGS)


	global _MAJORITY_VOTE, _CAMERA_AGREEMENT
	_MAJORITY_VOTE = {}
	_CAMERA_AGREEMENT = []

	# pylint: disable=E1101
	try:
		logger.debug(f'STARTING DETECTION LOOP FOR CAMERA {camera_uuid}')
		while True:
			if CAMERA_STATES[camera_uuid]['live_detection_running'] != 'yes':
				break

			if COUNTDOWN_SETTINGS['alert_status'] == 'inactive': # No point in burning CPU
				try:
					frame = get_shared_camera_frame(camera_uuid)
				except Exception as e:
					logger.warning("Failed to get frame from shared camera stream %s", camera_uuid)
					CAMERA_STATES[camera_uuid]['live_detection_running'] = 'no'
					CAMERA_STATES[camera_uuid]['last_result'] = 'Failed to get frame'
					break

				# SRS possibly remove and instead get once from above loop
				# Leaving here may allow settings changes on-the-fly
				camera_setting = CAMERA_SETTINGS[camera_uuid]
				contrast = camera_setting['contrast']
				brightness = camera_setting['brightness']
				focus = camera_setting['focus']

				frame = cv2.convertScaleAbs(frame, alpha=contrast, beta=int((brightness - 1.0) * 255))
				if focus and focus != 1.0:
					blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=focus)
					frame = cv2.addWeighted(frame, 1.0 + focus, blurred, -focus, 0)
				detection_frame, _ = stream_optimizer.optimize_frame(frame)
				image = Image.fromarray(cv2.cvtColor(detection_frame, cv2.COLOR_BGR2RGB))
				tensor = app_state.transform(image).unsqueeze(0).to(app_state.device)
				
				"""
				This is where the detection happens
				we run inference on the current frame tensor, get a numeric prediction
				and then map that to a label.
				We also handle any exceptions that occur during inference and log them.
				The resulting label and timestamp are stored in the camera state for
				potential use in alerting logic.
				"""
				try:
					prediction = await _run_inference(app_state.model,
													tensor,
													app_state.prototypes,
													app_state.defect_idx,
													app_state.device)
					numeric = prediction[0] if isinstance(prediction, list) else prediction
				except Exception as e:
					logger.debug("Detection inference error for camera %s: %s", camera_uuid, e)
					numeric = None

				#SRS Nonesense - just take numeric o or 1 and make success / failure
				label = ''	
				label = app_state.class_names[numeric] if (
					isinstance(numeric, int)
					and 0 <= numeric < len(app_state.class_names)
					) else str(numeric)
				
				current_timestamp = time.time()
				
				"""
				UI periodically polls for camera state updates to show
				the latest detection result and timestamp.
				"""

				CAMERA_STATES[camera_uuid]['last_time'] = current_timestamp
				CAMERA_STATES[camera_uuid]['last_result'] = label
				
				"""
				A running count of successive detections is maintained
				to determine if we have enough evidence to trigger an alert.
				The majority vote logic checks if we have seen enough failures
				in the recent history to consider the defect active.
				The multi-camera agreement logic checks if other cameras are also detecting
				accoding to COUNTDOWN_SETTINGS.
				"""

				detection_count += 1
				if isinstance(numeric, int) and numeric == app_state.defect_idx:

					last_result = 0 # assumes success
					if label == 'failure':
						last_result = 1


					
					passed_majority_vote = _camera_failure_threshold(camera_uuid,majority_vote_window,majority_vote_threshold,last_result)
					passed_camera_combination = False
					CAMERA_STATES[camera_uuid]['defect_active'] = False
					
					if passed_majority_vote: # only check if the current camera detects failure
						logger.debug(f'{passed_majority_vote=} for camera {camera_uuid}')
						passed_camera_combination = _passed_multi_camera_test(countdown_control,camera_uuid,num_cameras)
						logger.debug(f'{passed_camera_combination =}')
						CAMERA_STATES[camera_uuid]['defect_active'] = True # only requires one camera to trigger

					do_alert = False
					if passed_majority_vote and passed_camera_combination:
						logger.debug(f'In Alert')
						# reset tests
						_MAJORITY_VOTE = {}
						_CAMERA_AGREEMENT = []
						do_alert = True

					if do_alert:
										
						# Send defect notification
						send_defect_notification(camera_uuid) # sync

						#Start the UI countdown disply
						await UI_countdown('start') # sync but non-blocking

						# If no user intervention before countdown - perform action
						asyncio.create_task(_take_action_after_countdown())

						# Wait for countdown time during active alert
						await asyncio.sleep(countdown_time)
						
						# reset alert status
						if COUNTDOWN_SETTINGS['alert_status'] == 'active': # Dont change if paused or cancelled
							COUNTDOWN_SETTINGS['alert_status'] = 'inactive'

			detection_interval = stream_optimizer.get_detection_interval()		
			await asyncio.sleep(detection_interval)

	finally:
		pass

def generate_frames(camera_uuid: str):
	"""Fallback frame generator if optimized generator fails, using shared video stream.

	Args:
		camera_uuid (str): The UUID of the camera.

	Yields:
		bytes: Multipart JPEG frame data.
	"""
	try:
		for frame_data in create_optimized_frame_generator(camera_uuid, CAMERA_SETTINGS[camera_uuid]):
			yield frame_data
	# pylint: disable=E1101
	except Exception as e:
		logger.error("Generate Frames - Error in optimized frame generation for camera %s: %s", camera_uuid, e)
		try:
			while True:
				contrast = CAMERA_SETTINGS[camera_uuid].get('contrast')
				brightness = CAMERA_SETTINGS[camera_uuid].get('brightness')
				focus = CAMERA_SETTINGS[camera_uuid].get('focus')
				frame = get_shared_camera_frame(camera_uuid)
				if frame is None:
					logger.warning("Failed to get frame from shared camera stream %s", camera_uuid)
					time.sleep(0.1)
					continue
				frame = cv2.convertScaleAbs(frame,
								alpha=contrast,
								beta=int((brightness - 1.0) * 255))
				if focus and focus != 1.0:
					blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=focus)
					frame = cv2.addWeighted(frame, 1.0 + focus, blurred, -focus, 0)
				_, buffer = cv2.imencode('.jpg', frame)
				frame_bytes = buffer.tobytes()
				yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
		except Exception as fallback_e:
			logger.error("Error in fallback frame generation for camera %s: %s",
						  camera_uuid,
						  fallback_e)
			

def _camera_failure_threshold(cam_uuid,window,threshold,latest_failure):
	'''
	latest_failure == 1 for failure and 0 for success
	'''
	global _MAJORITY_VOTE
	# initial setup

	counts = _MAJORITY_VOTE

	# Add new cam_uuid
	if counts.get(cam_uuid) is None:
		counts[cam_uuid] = {'failure_count': 0, 'stack': (), 'stack_length':0}

	failure_count = counts[cam_uuid]['failure_count']
	stack = counts[cam_uuid]['stack']
	stack_length = counts[cam_uuid]['stack_length']
 
	slicer = stack_length // window # integer divide ==>  0 if < window else 1
	
	# update the failure count
	oldest_entry = 0
	if stack_length >= window: 	# Dont grow the stack
		oldest_entry = stack[0]
	else:						# Still filling the stack window
		stack_length += 1
	
	failure_count = failure_count + latest_failure-oldest_entry # latest and oldest may both have been failure

	# Can we finish ?
	if failure_count >= threshold:
		return True

	stack = (*stack[slicer:], latest_failure) # max # entries == window 
	counts[cam_uuid] = {'failure_count': failure_count, 'stack': stack, 'stack_length':stack_length}
	return False


def _passed_multi_camera_test(countdown_control, camera_uuid,num_cameras):
	global _CAMERA_AGREEMENT

	if countdown_control == 'any_camera':
		if camera_uuid not in _CAMERA_AGREEMENT:
				_CAMERA_AGREEMENT.append(camera_uuid)

		print(f'Any {_CAMERA_AGREEMENT=}')
		
		if len(_CAMERA_AGREEMENT) >= 1: #Ok on first camera or more
			return True
		else:
			return False
		
	# If all_cameras is active - only trigger if no countdown is active
	if countdown_control == 'all_cameras':
		if camera_uuid not in _CAMERA_AGREEMENT:
			_CAMERA_AGREEMENT.append(camera_uuid)
		
		print(f'All {_CAMERA_AGREEMENT=}')

		if len(_CAMERA_AGREEMENT) >= num_cameras: # First time we hit the required number of cameras
				return True
		else:		   
			return False
	

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
				"countdown_action": COUNTDOWN_SETTINGS['countdown_action'],
				"alert_status": COUNTDOWN_SETTINGS['alert_status']
			})
		}
		await managerSSE.broadcast(payload)
		logger.debug("Broadcasted countdown_time SSE event successfully")
	except Exception as e:
		logger.error("Failed to broadcast countdown_time SSE event: %s", e)

async def _take_action_after_countdown():
	"""
	Wait for the alert's countdown, then ignore or act on the print job.
	"""

	await asyncio.sleep(COUNTDOWN_SETTINGS['countdown_time'])
	
	
	if COUNTDOWN_SETTINGS['alert_status'] == 'active': # Check if the alert is still active (not dismissed or overridden by user)
		match COUNTDOWN_SETTINGS['countdown_action']:
			case 'ignore': # allowing new alerts to be triggered 
				COUNTDOWN_SETTINGS['alert_status'] = 'inactive'
			case 'pause_print':
				COUNTDOWN_SETTINGS['alert_status'] = 'paused'
				suspend_print_job(COUNTDOWN_SETTINGS['countdown_action'])
				for camera_uuid,settings in CAMERA_STATES.items():
					if settings['live_detection_running'] == 'yes': # only pause cameras that are currently running
						await stop_live_detection(camera_uuid)
						CAMERA_STATES[camera_uuid]['live_detection_running'] = 'paused'
			case 'cancel_print':
				COUNTDOWN_SETTINGS['alert_status'] = 'cancelled' # Not reset since print job has been stopped
				suspend_print_job(COUNTDOWN_SETTINGS['countdown_action'])
				for camera_uuid,settings in CAMERA_STATES.items():
					if settings['live_detection_running'] == 'yes': # only stop cameras that are currently running
						await stop_live_detection(camera_uuid)
				



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
	except Exception as e:
		logger.error("Error creating optimized detection loop for camera %s: %s", camera_uuid, e)
		CAMERA_STATES[camera_uuid]["last_result"] = 'Error in detection loop'
		CAMERA_STATES[camera_uuid]["live_detection_running"] = 'no'

	
def send_defect_notification(camera_uuid):

	#if COUNTDOWN_SETTINGS['alert_status'] != 'inactive': # don't send if in countdown
	#	return
	
	COUNTDOWN_SETTINGS['alert_status'] = 'active'
	logger.debug("Attempting to send defect notification")

	if COUNTDOWN_SETTINGS['countdown_control'] == 'all_cameras':
		title_msg = f"duetPrintguard: All cameras"
	else:
		title_msg = f"duetPrintguard: {CAMERA_SETTINGS[camera_uuid]['nickname']}"

	if COUNTDOWN_SETTINGS['countdown_action'] == 'pause_print':
		action_msg = f"Print will be paused if not dismissed within {COUNTDOWN_SETTINGS['countdown_time']} seconds."
	elif COUNTDOWN_SETTINGS['countdown_action'] == 'cancel_print':
		action_msg = f"Print will be cancelled if not dismissed within {COUNTDOWN_SETTINGS['countdown_time']} seconds."
	else:
		action_msg = f"Alert will be dismissed automatically in {COUNTDOWN_SETTINGS['countdown_time']} seconds if not dismissed manually."

	notification = {'title': title_msg,'body': action_msg}

	if duet_send_notification(notification):
		logger.debug("Notification send completed")
	else:
		logger.error("Unexpected error sending notification")

global _SAVED_REQUEST

def save_request(request):
	global _SAVED_REQUEST
	_SAVED_REQUEST = request


async def start_live_detection(camera_uuid):
	"""Start continuous live detection on a specified camera."""
	global CAMERA_STATES, _SAVED_REQUEST
	request = _SAVED_REQUEST

	camera_state = CAMERA_STATES.get(camera_uuid)
	if camera_state and camera_state["live_detection_running"] == 'yes':
		return {"success": True, "message": f"Live detection already running for camera {camera_uuid}"}

	CAMERA_STATES[camera_uuid] = deepcopy(DEFAULT_CAMERA_STATE) # Precaution vs shallow copy

	try:
		task = asyncio.create_task(_live_detection_loop(request.app.state, camera_uuid))
		
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

	if CAMERA_STATES[camera_uuid]['live_detection_running'] != 'yes':
		return {"message": f"Live detection not running for camera {camera_uuid}"}
	
	live_detection_task = CAMERA_STATES[camera_uuid]['live_detection_task']
	if live_detection_task:
		try: 
			live_detection_task.cancel()
			CAMERA_STATES[camera_uuid] = deepcopy(DEFAULT_CAMERA_STATE) # Precaution vs shallow copy
			logger.debug("Stopped live detection task for camera %s", camera_uuid)
		except Exception as e:
			logger.error("Error stopping live detection task for camera %s: %s", camera_uuid, e)

	return {"message": f"Live detection stopped for camera {camera_uuid}"}



