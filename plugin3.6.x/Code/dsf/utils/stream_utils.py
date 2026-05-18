import asyncio
from logger_module import logger
import time
from typing import Dict, Tuple

import cv2
import numpy as np
from PIL import Image

from .model_utils import _run_inference
from .sse_utils import sse_update_camera_state, append_new_outbound_packet

from .shared_video_stream import get_shared_camera_frame
from models import Alert, AlertAction, SSEDataType, Notification
from .config import (get_config, STREAM_MAX_FPS,
					 STREAM_JPEG_QUALITY,
					 STREAM_MAX_WIDTH,
					 DETECTION_INTERVAL_MS)
from .config import (CAMERA_SETTINGS,CAMERA_STATES,COUNTDOWN_SETTINGS,ALERTS)


import uuid

from .alert_utils import (dismiss_alert, alert_to_response_json,
						  get_alert, append_new_alert)

from .camera_utils import (get_camera_state, get_camera_state_sync,
						   update_camera_state, update_camera_detection_history)

# from .notification_utils import send_defect_notification
from duet_printer import get_printer_config, suspend_print_job, duet_send_notification






class StreamOptimizer:
	"""Optimizes video stream frames and detection loops based on configuration."""

	def __init__(self):
		"""Initialize the stream optimizer with empty cache and timing."""
		self._config_cache = {}
		# self._last_config_check = 0
		# self._config_check_interval = 30.0
	'''
	def invalidate_cache(self):
		"""Clear cached streaming settings to force re-read from configuration."""
		self._last_config_check = 0
		self._config_cache.clear()
	'''
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
		#current_time = time.time()
		#if (current_time - self._last_config_check) > self._config_check_interval:
		if self._config_cache == {}:
			#config = get_config()
			#startup_mode = config.get(SavedConfig.STARTUP_MODE, SiteStartupMode.LOCAL)
			#tunnel_provider = config.get(SavedConfig.TUNNEL_PROVIDER, None)
			#optimize_for_tunnel = config.get(SavedConfig.STREAM_OPTIMIZE_FOR_TUNNEL, None)
			'''
			if optimize_for_tunnel is None:
				is_tunnel_mode = startup_mode == (SiteStartupMode.TUNNEL
												  and tunnel_provider is not None)
			else:
				is_tunnel_mode = optimize_for_tunnel
			if is_tunnel_mode:
				default_fps = config.get(SavedConfig.STREAM_TUNNEL_FPS, STREAM_TUNNEL_FPS)
				default_quality = STREAM_TUNNEL_JPEG_QUALITY
				default_width = STREAM_TUNNEL_MAX_WIDTH
				default_detection_interval = DETECTION_TUNNEL_INTERVAL_MS
			else:
			
			default_fps = config.get(SavedConfig.STREAM_MAX_FPS, STREAM_MAX_FPS)
			default_quality = STREAM_JPEG_QUALITY
			default_width = STREAM_MAX_WIDTH
			default_detection_interval = DETECTION_INTERVAL_MS
			'''
			self._config_cache = {
				'max_fps': STREAM_MAX_FPS,
				'jpeg_quality': STREAM_JPEG_QUALITY,
				'max_width': STREAM_MAX_WIDTH,
				'detection_interval_ms': DETECTION_INTERVAL_MS
			}
			'''SRS Loops thrrough here like a banchee every time - need to optimize'''
		# print(f'{self._config_cache=}')	
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

	def log_optimization_info(self):
		"""Log current stream optimization settings for debugging."""
		settings = self._get_current_settings()
		mode_info = "local"
		logger.debug("Stream optimization settings for %s mode:", mode_info)
		logger.debug("  Max FPS: %d", settings['max_fps'])
		logger.debug("  JPEG Quality: %d", settings['jpeg_quality'])
		logger.debug("  Max Width: %d", settings['max_width'])
		logger.debug("  Detection Interval: %dms", settings['detection_interval_ms'])

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
	if frame_count == 0:
		stream_optimizer.log_optimization_info()
	try:
		while True:
			if stream_optimizer.should_limit_fps(last_frame_time):
				time.sleep(0.001)
				continue
			# camera_state = camera_state_getter(camera_uuid)
			# SRS can likely remove the state getter and delete synchronous get state references
			camera_state = CAMERA_SETTINGS[camera_uuid] 
			logger.debug(f'############# Camera {camera_uuid} - Optimized Frame Generation - State: {camera_state}')
			contrast = CAMERA_SETTINGS.get(camera_uuid).get('contrast')
			brightness = CAMERA_SETTINGS.get(camera_uuid).get('brightness')
			focus = CAMERA_SETTINGS.get(camera_uuid).get('focus')
			# contrast = camera_state.contrast
			# brightness = camera_state.brightness
			# focus = camera_state.focus
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
	try:
		print(f'STARTING ODL {camera_uuid}')
		detection_count = 0
		#camera_state_ref = get_camera_state_sync_func(camera_uuid)
		#detection_history = {}
		majority_vote_window = CAMERA_SETTINGS[camera_uuid]['majority_vote_window']
		majority_vote_threshold = CAMERA_SETTINGS[camera_uuid]['majority_vote_threshold']
		countdown_control = COUNTDOWN_SETTINGS['countdown_control']
		countdown_time = COUNTDOWN_SETTINGS['countdown_time']
		num_cameras = len(CAMERA_SETTINGS)
	except Exception as e:
		print(f'WTF !!! {camera_uuid} ERROR {e}')

	global _MAJORITY_VOTE, _CAMERA_AGREEMENT
	_MAJORITY_VOTE = {}
	_CAMERA_AGREEMENT = []

	#stream_optimizer.log_optimization_info()
	# pylint: disable=E1101
	try:
		while True:
			print(f'STARTING DETECTION LOOP FOR CAMERA {camera_uuid}')
			camera_state = CAMERA_STATES[camera_uuid]
			if not CAMERA_STATES[camera_uuid]['live_detection_running']:
				break
			try:
				frame = get_shared_camera_frame(camera_uuid)
			except Exception as e:
				logger.warning("Failed to get frame from shared camera stream %s", camera_uuid)
				CAMERA_STATES[camera_uuid]['live_detection_running'] = False
				"""
				await update_functions['update_camera_state'](camera_uuid, {
					"error": "Failed to get frame from shared stream",
					"live_detection_running": False
				})
				"""
				break
			#SRS Can remove and instead get once from above loop
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
			try:
				print(f'GETTING PREDICTION FOR {camera_uuid}')
				prediction = await _run_inference(app_state.model,
												tensor,
												app_state.prototypes,
												app_state.defect_idx,
												app_state.device)
				print(f'GOT PREDICTION {prediction} FOR {camera_uuid}')
				numeric = prediction[0] if isinstance(prediction, list) else prediction
			except Exception as e:
				logger.debug("Detection inference error for camera %s: %s", camera_uuid, e)
				numeric = None
			label = app_state.class_names[numeric] if (
				isinstance(numeric, int)
				and 0 <= numeric < len(app_state.class_names)
				) else str(numeric)
			current_timestamp = time.time()
			''' SRS dont use history any more
			await update_functions['update_camera_detection_history'](camera_uuid,
																	  label,
																	  current_timestamp)
			'''
			print(f'Camera {camera_uuid} - Detection result: {label} at {current_timestamp}')
			CAMERA_STATES[camera_uuid]['last_time'] = current_timestamp
			CAMERA_STATES[camera_uuid]['last_result'] = label
			
			"""SRS
			await update_functions['update_camera_state'](camera_uuid, {
				"last_result": label,
				"last_time": current_timestamp
			})
			"""
			#asyncio.create_task(sse_update_camera_state(camera_uuid))
			detection_count += 1
			if isinstance(numeric, int) and numeric == app_state.defect_idx:
				do_alert = False
				#SRS camera_lock = camera_state_ref.lock
				# SRS CHANGE HERE FOR _camera_failure_threshold function - does not need history or timestamp
				last_result = 0 # assumes success
				if label == 'failure':
					last_result = 1

				#SRS async with camera_lock:
				passed_majority_vote = _camera_failure_threshold(camera_uuid,majority_vote_window,majority_vote_threshold,last_result)
				passed_camera_combination = False
				if passed_majority_vote:
					logger.debug(f'{passed_majority_vote=}')
					passed_camera_combination = _passed_multi_camera_test(countdown_control,camera_uuid,num_cameras)

				if passed_majority_vote and passed_camera_combination:
					logger.debug(f'{passed_camera_combination =}')
					'''
					# Can remove since blocked by sleep during alert
					if camera_state_ref.current_alert_id is None:
						camera_state_ref.current_alert_id = True
						do_alert = True
					'''
					do_alert = True
					if do_alert:
						'''SRS'''
						# alert = await _create_alert_and_notify(camera_state_ref,
						alert = await _create_alert_and_notify(camera_uuid, frame, current_timestamp)
						
						asyncio.create_task(_send_alert(alert))

						# Wait for countdown time during active alert
						await asyncio.sleep(countdown_time)

						#del _camera_failure_threshold.counts # reset for all
						# _passed_multi_camera_test.alert_uuids = [] # reset the combination test
						#if hasattr(_camera_failure_threshold, "counts"): del _camera_failure_threshold.counts # reset for all
						_MAJORITY_VOTE = {}
						_CAMERA_AGREEMENT = []

			detection_interval = stream_optimizer.get_detection_interval()
			print(f'sleeping for {detection_interval} seconds')			
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
		for frame_data in create_optimized_frame_generator(camera_uuid, get_camera_state_sync):
			yield frame_data
	# pylint: disable=E1101
	except Exception as e:
		logger.error("Generate Frames - Error in optimized frame generation for camera %s: %s", camera_uuid, e)
		try:
			while True:
				camera_state = get_camera_state_sync(camera_uuid)
				contrast = camera_state.contrast
				brightness = camera_state.brightness
				focus = camera_state.focus
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
			

def _camera_failure_threshold(uuid,window,threshold,latest_failure):
	'''
	latest_failure == 1 for failure and 0 for success
	'''
	global _MAJORITY_VOTE
	# initial setup

	counts = _MAJORITY_VOTE

	# Add new uuid
	if counts.get(uuid) is None:
		counts[uuid] = {'failure_count': 0, 'stack': (), 'stack_length':0}

	failure_count = counts[uuid]['failure_count']
	stack = counts[uuid]['stack']
	stack_length = counts[uuid]['stack_length']
 
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
	counts[uuid] = {'failure_count': failure_count, 'stack': stack, 'stack_length':stack_length}
	return False


def _passed_multi_camera_test(countdown_control, camera_uuid,num_cameras):
	global _CAMERA_AGREEMENT

	alert_uuids = _CAMERA_AGREEMENT
	
	if countdown_control == 'any_camera': #Ok on first camera
		if len(alert_uuids) == 0:
			alert_uuids.append(camera_uuid)
			return True
		else:
			if camera_uuid not in alert_uuids:
				alert_uuids.append(camera_uuid)
				return False
		
	# If all_cameras is active - only trigger if no countdown is active
	if countdown_control == 'all_cameras':
		if camera_uuid not in alert_uuids:
			alert_uuids.append(camera_uuid)
			if len(alert_uuids) >= num_cameras: # First time we hit the required number of cameras, start the countdown
				return True
				   
		return False
	

async def _send_alert(alert):
	"""Send an alert to clients via Server-Sent Events.

	Args:
		alert (Alert): The alert object to send.
	"""
	await append_new_outbound_packet(alert_to_response_json(alert), SSEDataType.ALERT)

async def _terminate_alert_after_cooldown(alert):
	"""Wait for the alert's countdown, then dismiss or act on the print job.

	Args:
		alert (Alert): The alert object with `countdown_time` and `countdown_action`.
	"""
	#SRS await asyncio.sleep(alert.countdown_time)
	await asyncio.sleep(COUNTDOWN_SETTINGS['countdown_time'])
	if get_alert(alert.id) is not None: # if the alert has been reset ==> ignore
		camera_uuid = alert.camera_uuid
		#camera_state = await get_camera_state(camera_uuid)
		#camera_state = CAMERA_STATES[camera_uuid]
		#if not camera_state:
		#	return
		match COUNTDOWN_SETTINGS['countdown_action']:
			case AlertAction.DISMISS:
				await dismiss_alert(alert.id)
			case AlertAction.CANCEL_PRINT | AlertAction.PAUSE_PRINT:
				# suspend_print_job(camera_uuid, camera_state.countdown_action)
				suspend_print_job(camera_uuid, COUNTDOWN_SETTINGS['countdown_action'])
				return await dismiss_alert(alert.id)
	else:
		print(f'Alert was terminated')

# async def _create_alert_and_notify(camera_state_ref, camera_uuid, frame, timestamp_arg):
async def _create_alert_and_notify(camera_uuid, frame, timestamp_arg):
	"""Create a new Alert object and notify all subsystems.

	Args:
		camera_state_ref (CameraState): The state reference for the camera.
		camera_uuid (str): The UUID of the camera.
		frame (ndarray): The image frame where a defect was detected.
		timestamp_arg (float): The timestamp of detection.

	Returns:
		Alert: The newly created alert.
	"""
	print('DETECTION UTILS ALERT')
	alert_id = f"{camera_uuid}_{str(uuid.uuid4())}"
	# pylint: disable=E1101
	_, img_buf = cv2.imencode('.jpg', frame)
	has_printer = get_printer_config(camera_uuid) is not None

	alert = Alert(
		id=alert_id,
		camera_uuid=camera_uuid,
		timestamp=timestamp_arg,
		snapshot=img_buf.tobytes(),
		title=f"Defect - Camera {CAMERA_SETTINGS[camera_uuid]['nickname']}",
		message=f"Defect detected on camera {CAMERA_SETTINGS[camera_uuid]['nickname']}",
		countdown_time=COUNTDOWN_SETTINGS['countdown_time'],
		countdown_action=COUNTDOWN_SETTINGS['countdown_action'],
		countdown_control=COUNTDOWN_SETTINGS['countdown_control'],
		has_printer=has_printer,
	)

	append_new_alert(alert)
	asyncio.create_task(_terminate_alert_after_cooldown(alert))
	#await update_camera_state(camera_uuid, {"current_alert_id": alert_id})
	CAMERA_STATES[camera_uuid]['current_alert_id'] = alert_id
	await send_defect_notification(alert_id)
	return alert

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
	
	update_functions = {
		'update_camera_state': update_camera_state,
		'update_camera_detection_history': update_camera_detection_history,
	}
	try:
		print(f'TRYING TO CREATE OPTIMIZED DETECTION LOOP FOR {camera_uuid}')
		await create_optimized_detection_loop(
			app_state,
			camera_uuid
		)
	except Exception as e:
		logger.error("Error creating optimized detection loop for camera %s: %s", camera_uuid, e)
		CAMERA_STATES[camera_uuid]["last_result"] = 'Error in detection loop'
		CAMERA_STATES[camera_uuid]["live_detection_running"] = False
		"""
		CAMERA_STATES[camera_uuid]["live_detection_running"] = False
		await update_camera_state(camera_uuid, {
			"error": f"Detection loop error: {str(e)}",
			"live_detection_running": False
		})
		"""

	
async def send_defect_notification(alert_id):
	"""Send a defect notification for a given alert ID to all subscribers.

	Args:
		alert_id (str): The ID of the alert for which to send a notification.
	"""
	logger.debug("Attempting to send defect notification for alert ID: %s", alert_id)
	alert = get_alert(alert_id)
	if alert:
		logger.debug("Alert found for ID %s, preparing notification", alert_id)
		# pylint: disable=import-outside-toplevel
		#from .camera_utils import get_camera_state
		#camera_state = await get_camera_state(alert.camera_uuid)
		camera_state = CAMERA_SETTINGS[alert.camera_uuid]
		#camera_nickname = camera_state.nickname if camera_state else alert.camera_uuid
		camera_nickname = camera_state['nickname']
		notification = Notification(
			title=f"duetPrintGuard",
			body=f"Defect detected on camera {camera_nickname}",
		)
		subscriptions = []  #SRS NOT NEEDED - DELETE REFERENCES
		logger.debug("Created notification object without image payload, sending to %d subscriptions",
					  len(subscriptions))
		send_notification(notification)
	else:
		logger.error("No alert found for ID: %s", alert_id)

#SRS
def send_notification(notification: Notification):
	"""Send a push notification to all current subscriptions.

	Args:
		notification (Notification): The notification object to send. Should have 'title' and 'body' fields at minimum.

	Returns:
		bool: True if at least one notification was sent successfully, False otherwise.
	"""
	logger.info("Starting notification send process")
	logger.debug(notification)

	if duet_send_notification(notification):
		logger.debug("Notification send completed")
		return True
	else:
		logger.error("Unexpected error sending notification")
		return False


