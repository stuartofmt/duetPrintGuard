"""
Nothing is run on import.
All initialization is done through explicit function calls.
"""

import os
from copy import deepcopy

import torch

from logger_module import logger
from .model_downloader import get_model_downloader

from duet_config import (CAMERA_SECTION, COUNTDOWN_SECTION, DEFAULT_COUNTDOWN_SETTINGS,
						 load_section, save_section)

# The dsf directory (holds the model files)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The camera configuration that is accessed by other modules
# Frequently updated and exist only in memory - not persisted to disk
CAMERA_STATES = {}
DEFAULT_CAMERA_STATE = {
				"live_detection_running": 'no',
				"last_result": '',
				"last_time": 0,
				"defect_active": False,
				"live_detection_task": None
							}
# Defaults
DETECTION_VOTING_WINDOW = 5
DETECTION_VOTING_THRESHOLD = 2
SENSITIVITY = 1.0 # Still used by the inference engine (model_utils)
# BRIGHTNESS = 1.0
# CONTRAST = 1.0
# FOCUS = 1.0
AUTOSTART = False

# Default but can be updated by user and persisted in config
CAMERA_SETTINGS = {}
PERSISTED_CAMERA_SETTINGS = set('nickname source snapshot majority_vote_window majority_vote_threshold autostart'.split())
# Note nickname, source and snapshot are created with camera. Default settinga are added at that time
DEFAULT_CAMERA_SETTINGS = {'majority_vote_window': DETECTION_VOTING_WINDOW,
						   'majority_vote_threshold': DETECTION_VOTING_THRESHOLD,
						   # 'sensitivity': SENSITIVITY, 'brightness': BRIGHTNESS,
						   # 'contrast': CONTRAST,
						   # 'focus': FOCUS,
						   'autostart': AUTOSTART}

#Settings that determine if a defect should be declared
# alert_status is runtime state only - it is not saved, so every start begins with no active alert
ALERT_STATUS = 'inactive'

COUNTDOWN_SETTINGS = {**DEFAULT_COUNTDOWN_SETTINGS, 'alert_status': ALERT_STATUS}

# Streaming and detection parameters
DETECTIONS_PER_SECOND = 1 #15
STREAM_MAX_FPS = 2 #30
STREAM_JPEG_QUALITY = 85
STREAM_MAX_WIDTH = 1280
DETECTION_INTERVAL_MS = 1000 / DETECTIONS_PER_SECOND
MIN_SSE_DISPATCH_DELAY_MS = 100 #100
STANDARD_STAT_POLLING_RATE_MS = 250 #250
SUCCESS_LABEL = "success"
PRINTER_POLL_SECONDS = 10 

DEVICE_TYPE = "cuda" if (torch.cuda.is_available()) else (
	"mps" if (torch.backends.mps.is_available()) else "cpu")

def _save_cameras():
	"""Save the persisted camera settings to duetPrintGuard.json."""
	save_section(CAMERA_SECTION, {
		camera_uuid: {k: v for k, v in settings.items() if k in PERSISTED_CAMERA_SETTINGS}
		for camera_uuid, settings in CAMERA_SETTINGS.items()
	})


def _save_countdown():
	"""Save the countdown settings to duetPrintGuard.json (alert_status is runtime state and is not saved)."""
	save_section(COUNTDOWN_SECTION, {k: v for k, v in COUNTDOWN_SETTINGS.items() if k in DEFAULT_COUNTDOWN_SETTINGS})


def add_to_config(updates: dict):
	"""Update camera or countdown settings in memory and save them.

	Args:
		updates (dict): {'countdown_settings': {setting: value, ...}} or
			{'camera_settings': {camera_uuid: {setting: value, ...}}}. Camera settings can be partial,
			so the frontend only needs to send the settings that changed.
	"""
	if updates.get('countdown_settings') is not None:
		for setting_type, value in updates['countdown_settings'].items():
			COUNTDOWN_SETTINGS[setting_type] = value
		_save_countdown()

	elif updates.get('camera_settings') is not None:
		for camera_uuid, settings in updates['camera_settings'].items():
			if camera_uuid not in CAMERA_SETTINGS: # New camera entry
				CAMERA_SETTINGS[camera_uuid] = deepcopy(DEFAULT_CAMERA_SETTINGS) # Precaution vs shallow copy
				CAMERA_STATES[camera_uuid] = deepcopy(DEFAULT_CAMERA_STATE)
			for setting_type, value in settings.items():
				if setting_type in PERSISTED_CAMERA_SETTINGS:
					CAMERA_SETTINGS[camera_uuid][setting_type] = value
			logger.debug(f'{CAMERA_SETTINGS[camera_uuid]=}')
		_save_cameras()


def delete_from_config(updates: dict):
	"""Remove a camera's settings (saved) or state (memory only).

	Args:
		updates (dict): {'camera_settings': camera_uuid} and/or {'camera_states': camera_uuid}
	"""
	if updates.get('camera_settings') is not None:
		CAMERA_SETTINGS.pop(updates['camera_settings'], None)
		_save_cameras()

	if updates.get('camera_states') is not None:
		# CAMERA_STATES are not persisted
		CAMERA_STATES.pop(updates['camera_states'], None)


def _fix_vote_settings(camera_settings):
	"""Raise any majority vote window that is smaller than its threshold, which could never be met.

	Returns True if a camera was changed.
	"""
	changed = False
	for settings in camera_settings.values():
		threshold = settings.get('majority_vote_threshold', DETECTION_VOTING_THRESHOLD)
		window = settings.get('majority_vote_window', DETECTION_VOTING_WINDOW)
		if window < threshold:
			logger.warning(
				"Camera %s: majority vote window %s is smaller than the threshold %s - setting the window to %s",
				settings.get('nickname', '?'), window, threshold, threshold)
			settings['majority_vote_window'] = threshold
			changed = True
	return changed


def init_config():
	"""Load the camera and countdown settings from duetPrintGuard.json into memory.

	duet_config.get_DWC_config() must have run first - it creates the file (with no cameras) if needed.
	The dicts are updated in place so modules that imported them see the loaded values.
	"""
	CAMERA_SETTINGS.clear()
	CAMERA_SETTINGS.update(load_section(CAMERA_SECTION))
	if _fix_vote_settings(CAMERA_SETTINGS):
		_save_cameras()

	COUNTDOWN_SETTINGS.clear()
	COUNTDOWN_SETTINGS.update(load_section(COUNTDOWN_SECTION))
	COUNTDOWN_SETTINGS['alert_status'] = ALERT_STATUS

	CAMERA_STATES.clear()
	for camera_uuid in CAMERA_SETTINGS:
		CAMERA_STATES[camera_uuid] = deepcopy(DEFAULT_CAMERA_STATE)

	logger.info(f'Loaded {len(CAMERA_SETTINGS)} camera(s) from the configuration')
	logger.debug(f'{CAMERA_SETTINGS=} {COUNTDOWN_SETTINGS=}')


def get_model_path() -> str:
	"""Get the model path for the detected backend."""
	try:
		return get_model_downloader().get_model_path()
	except ImportError:
		return os.path.join(BASE_DIR, "model", "model.onnx")

def get_model_options_path() -> str:
	"""Get the model options path."""
	try:
		return get_model_downloader().get_options_path()
	except ImportError:
		return os.path.join(BASE_DIR, "model", "opt.json")

def get_prototypes_dir() -> str:
	"""Get the prototypes directory path."""
	try:
		return get_model_downloader().get_prototypes_path()
	except ImportError:
		return os.path.join(BASE_DIR, "model", "prototypes")
