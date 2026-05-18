"""SRS
Refactored so that nothing is run on import and all initialization is done through explicit function calls.
This allows for better control of when and how the configuration is loaded,
especially in the context of DWC where we want to aet paths etc based on a passed argument.
"""

import json
import uuid
from logger_module import logger
import os
import fcntl
import threading

import torch
from platformdirs import user_data_dir

from .model_downloader import get_model_downloader
from models import AlertAction, SavedConfig

from duet_config import DUET

# Config version - increment this when the config structure changes
# SRS reduced config to just camera states
CONFIG_VERSION = "2.0.0"

'''
Refactored so that only minimal camera info is persisted in the config file
and all runtime state is reset on startup.
Config info is now held in memory
No more need for locks around config access since we only read/write on startup
and when updating infrequent camera states.
'''
# The camera configuration that is accessed by other modules
# Frequently updated and exist only in memory - not persisted to disk
CAMERA_STATES = {}
ALLOWED_CAMERA_STATES = set('last_result last_time live_detection_running'.split())

# Defaults
# DETECTION_TIMEOUT = 5
# DETECTION_THRESHOLD = 3
DETECTION_VOTING_WINDOW = 5
DETECTION_VOTING_THRESHOLD = 2
SENSITIVITY = 1.0
BRIGHTNESS = 1.0
CONTRAST = 1.0
FOCUS = 1.0

# Default but can be updated by user and persisted in config
CAMERA_SETTINGS = {}
PERSISTED_CAMERA_SETTINGS = set('nickname source majority_vote_window majority_vote_threshold sensitivity brightness contrast focus'.split())
# Note nickname and source are created with camera. Default settinga are added at that time
DEFAULT_CAMERA_SETTINGS = {'majority_vote_window': DETECTION_VOTING_WINDOW,
						   'majority_vote_threshold': DETECTION_VOTING_THRESHOLD,
						   'sensitivity': SENSITIVITY, 'brightness': BRIGHTNESS,
						   'contrast': CONTRAST,
						   'focus': FOCUS}

#Settings that determine if a defect should be declared

COUNTDOWN_TIME = 60
COUNTDOWN_ACTION = 'dismiss'
COUNTDOWN_CONTROL = "any_camera"

COUNTDOWN_SETTINGS = {'countdown_time': COUNTDOWN_TIME, 'countdown_action': COUNTDOWN_ACTION, 'countdown_control': COUNTDOWN_CONTROL}

# In process alerts are gathered here - no defaults
ALERTS= {}

# Streaming and detection parameters
DETECTIONS_PER_SECOND = .25 #15
STREAM_MAX_FPS = 2 #30
STREAM_JPEG_QUALITY = 85
STREAM_MAX_WIDTH = 1280
DETECTION_INTERVAL_MS = 1000 / DETECTIONS_PER_SECOND
MIN_SSE_DISPATCH_DELAY_MS = 100 #100
STANDARD_STAT_POLLING_RATE_MS = 250 #250
SUCCESS_LABEL = "success"

DEVICE_TYPE = "cuda" if (torch.cuda.is_available()) else (
	"mps" if (torch.backends.mps.is_available()) else "cpu")

_config_lock = threading.RLock()
_file_lock = None


def config_set_paths_and_initialize():
	global BASE_DIR, APP_DATA_DIR, SSL_DATA_DIR,CONFIG_FILE, SECRETS_FILE, LOCK_FILE, SSL_CERT_FILE, SSL_CA_FILE,KEYRING_SERVICE_NAME

	APP_DATA_DIR = ""
	BASE_DIR = os.path.dirname(os.path.abspath(__name__))

	APP_DATA_DIR = user_data_dir("duetprintguard", "duetprintguard")
	if  not APP_DATA_DIR.startswith('/home') :  # Likely running as plugin user_data_dir will not resolve
		# So we put it where dsf has permissions
		APP_DATA_DIR = os.path.join(BASE_DIR, '.sbc')
	else: # used for local testing
		logger.warning(f"Using app data directory: {APP_DATA_DIR}")


	os.makedirs(APP_DATA_DIR, exist_ok=True)

	CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
	LOCK_FILE = os.path.join(APP_DATA_DIR, "config.lock")
 
	# continue with phase 2 of initialization which depends on these paths being set
	init_config()


def acquire_lock():
	"""Acquire a thread and file lock for safe configuration file access.

	Ensures exclusive access to the config file by acquiring a threading lock
	and a file-based lock at `LOCK_FILE`.
	"""
	# pylint: disable=global-statement
	global _file_lock, LOCK_FILE
	_config_lock.acquire()
	_file_lock = open(LOCK_FILE, 'w')
	try:
		fcntl.flock(_file_lock, fcntl.LOCK_EX)
	except IOError as e:
		logger.warning("Failed to acquire file lock: %s", e)


def release_lock():
	"""Release the configuration file exclusivity locks.

	Releases both the file-based lock and the threading lock.
	"""
	# pylint: disable=global-statement
	global _file_lock
	if _file_lock:
		fcntl.flock(_file_lock, fcntl.LOCK_UN)
		_file_lock.close()
		_file_lock = None
	_config_lock.release()

def _get_config_nolock():
	"""Load configuration from disk without acquiring any locks.

	Returns:
		dict or None: The JSON-loaded configuration, or None if file doesn't exist or load fails.
	"""
	if os.path.exists(CONFIG_FILE):
		try:
			with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
				return json.load(f)
		except Exception as e:
			logger.error("Error loading config file: %s", e)
	return None

def get_config():
	"""Thread-safe retrieval of the application configuration.

	Acquires locks before reading the config file.

	Returns:
		dict or None: The loaded configuration dictionary, or None if not initialized.
	"""
	acquire_lock()
	try:
		return _get_config_nolock()
	finally:
		release_lock()

def add_to_config(updates: dict):
	global CAMERA_SETTINGS, COUNTDOWN_SETTINGS, CAMERA_STATES
	"""Thread-safe update of configuration values in the config file.

	Args:
		updates (dict): A mapping of config keys to their new values.
	"""

	config = _get_config_nolock() or {}
	try:
		if updates.get("countdown_settings") is not None or "countdown_settings" in updates:
			# Countdown settings are all persisted together so we can just update the whole section if any of the settings are included in the request. This allows for partial updates without needing to resend all settings, but also ensures that the persisted config is always complete for countdown settings.
			config['countdown_settings'] = updates['countdown_settings']
			COUNTDOWN_SETTINGS.clear()
			COUNTDOWN_SETTINGS.update(updates['countdown_settings'])

		elif updates.get("camera_settings") is not None or "camera_settings" in updates:
			# We want to allow partial updates to camera settings so we loop through the provided settings and only update the ones that are included in the request. This allows the frontend to send only the settings that were changed without needing to resend all settings for a camera.
			for camera_uuid, settings in updates['camera_settings'].items():
				if camera_uuid not in config['camera_settings']:
					config['camera_settings'][camera_uuid] = {}
					CAMERA_SETTINGS[camera_uuid] = {}
				for setting_type, value in settings.items():
						if setting_type in PERSISTED_CAMERA_SETTINGS:					
							config['camera_settings'][camera_uuid][setting_type] = value
							CAMERA_SETTINGS[camera_uuid][setting_type] = value

				print(f'{config['camera_settings'][camera_uuid]=}')

		elif updates.get("camera_states") is not None or "camera_states" in updates:
			# CAMERA_STATES are not persisted to config file but we want to validate the keys here and update the in memory state
			for camera_uuid, settings in updates['camera_states'].items():
				for key, value in settings.items():
						if key in ALLOWED_CAMERA_STATES:
							if camera_uuid not in CAMERA_STATES:
								CAMERA_STATES[camera_uuid] = {}
							CAMERA_STATES[camera_uuid][key] = value

		with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
			json.dump(config, f, indent=2)
	finally:
		logger.debug(f'{config=}')

def delete_from_config(updates: dict):
	global CAMERA_SETTINGS, CAMERA_STATES
	"""remove configuration from the config file for the specified camera.

	Args:
		updates (dict): A mapping of config keys to their new values.
	"""

	config = _get_config_nolock() or {}
	try:
		if updates.get("camera_settings") is not None or "camera_settings" in updates:
			# camera settings are persisted in config file so we need to remove the entry for the specified camera and then rewrite the config file.
			# We also remove it from the in memory CAMERA_SETTINGS so that it is consistent with what is persisted.
			config['camera_settings'].pop(updates['camera_settings'], None)
			CAMERA_SETTINGS.pop(updates['camera_settings'], None)
			print(f'{config['camera_settings']=}')
			with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
				json.dump(config, f, indent=2)

		if updates.get("camera_states") is not None or "camera_states" in updates:
			# CAMERA_STATES are not persisted to config file
			CAMERA_STATES.pop(updates['camera_states'], None)

	finally:
		logger.debug(f'{config=}')


def init_config():
	global CAMERA_STATES, CAMERA_SETTINGS, COUNTDOWN_SETTINGS
	"""Initialize the configuration file with default keys if missing.
	
	Checks if the config file exists and has the correct version.
	also checks if cameras have been defined
	If not creates `config.json` with defaults .
	"""

	try:
		config_needs_reset = False
		if os.path.exists(CONFIG_FILE):
			try:
				existing_config = _get_config_nolock()
				if existing_config is None:
					logger.info("Config file is corrupted or empty, recreating")
					config_needs_reset = True

				config_version = existing_config.get(SavedConfig.VERSION)
				if config_version != CONFIG_VERSION:
					logger.info(
						"Config version mismatch (config: %s, expected: %s), recreating config",
						config_version, CONFIG_VERSION)
					config_needs_reset = True

				if 'countdown_settings' not in existing_config: # Should be there after first successful setup but just in case
					logger.info("No settings in config, recreating")
					config_needs_reset = True
			except Exception as e:
				logger.warning("Error reading config file: %s, recreating", e)
				config_needs_reset = True
		else: # Config file doesn't exist, will be created with defaults
			config_needs_reset = True

		if config_needs_reset:
			reset_config()
	finally:
		#SRS - on first start of each application run - reset globals

		startup_config = _get_config_nolock()
		CAMERA_SETTINGS = startup_config.get('camera_settings', {})
		countdown_settings = startup_config.get('countdown_settings')
		if countdown_settings is not None:
			COUNTDOWN_SETTINGS.clear()
			COUNTDOWN_SETTINGS.update(countdown_settings)
		for camera_uuid,_ in CAMERA_SETTINGS.items():
			CAMERA_STATES[camera_uuid] = {
							'live_detection_running':False,
							'last_result':'',
							'last_time':None,
							'live_detection_task':None
							}
				
		logger.debug('Starting with configuration')
		logger.debug(f'{startup_config=}')


def reset_config():
	"""Reset the configuration file to default values.

	Overwrites `config.json` with default empty fields for all SavedConfig options.
	"""
	acquire_lock()

	try:
		if os.path.exists(CONFIG_FILE):
			os.remove(CONFIG_FILE)
			logger.info("Deleted old config file")

		default_config = {
			'version': CONFIG_VERSION,
			'camera_settings': CAMERA_SETTINGS,
			'countdown_settings': COUNTDOWN_SETTINGS,
		}
		with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
			json.dump(default_config, f, indent=2)
		logger.info(f'Created new config file with version {CONFIG_VERSION} at {CONFIG_FILE}')
		logger.debug(f'{default_config=}')
	finally:
		release_lock()


def reset_all():
	"""Reset keyring, config, and SSL files to a clean state.

	Invokes `reset_all_keys`, `reset_config`, and `reset_ssl_files` sequentially.
	"""
	reset_config()
	logger.debug("Config file has been reset")


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

