"""
Application configuration for duetPrintGuard

All settings are held in duetPrintGuard.json (in the folder given at startup,
alongside the log file):
- the sections in CONFIG_SCHEMA, edited through the /config web page
- camera_settings and countdown_settings, edited through the /settings web page
  (held in memory by utils/config.py, which loads and saves them through this module)

The file is stored zlib-compressed and base64 encoded so it is not plain
text, prefixed with a CRC32 checksum of the encoded data ("<crc32>:<base64>").
This is obfuscation only - it is not encryption. If the checksum does not
validate (or the file cannot be decoded) the file is deleted and a new
one is created from the defaults.

No config file is required - if there is no json file, one is created
from the defaults (with no cameras) on startup.

The section objects (DUET, UI, etc.) are created on import and are only
ever updated in place, so modules that import them see live changes.
"""
import base64
import binascii
import json
import os
import zlib
import threading

global DUET, UI, LOGGING, ACTION, MACRO, NTFY, PUSHOVER

CONFIGFILENAME = 'duetPrintGuard.json'

# section -> key -> (type, default, restart_required)
CONFIG_SCHEMA = {
	'UI': {
		'PORT': (int, 0, True),
		'IP' : (str,'',False)
	},
	'LOGGING': {
		'LEVEL': (str, 'INFO', False),
	},
	'ACTION': {
		'PAUSE': (str, '', False),
		'RESUME': (str, '', False),
		'CANCEL': (str, '', False),
	},
	'MACRO': {
		'MACRO': (str, '', False),
		'MAXTIMES': (int, 3, False),
	},
	'NTFY': {
		'TOPIC': (str, '', False),
		'TITLE': (str, '', False),
		'MESSAGE': (str, '', False),
		'PRIORITY': (int, 3, False),
		'MAXTIMES': (int, 3, False),
	},
	'PUSHOVER': {
		'API': (str, '', False),
		'USER': (str, '', False),
		'TITLE': (str, '', False),
		'MESSAGE': (str, '', False),
		'MAXTIMES': (int, 3, False),
	},
}

# Set by the program at startup - not shown on, or editable from, the config page
HIDDEN_SETTINGS = {('UI', 'IP')}

# Sections managed by utils/config.py (cameras and the defect countdown)
CAMERA_SECTION = 'camera_settings'
COUNTDOWN_SECTION = 'countdown_settings'
DEFAULT_COUNTDOWN_SETTINGS = {'countdown_time': 60, 'countdown_action': 'ignore', 'countdown_control': 'any_camera'}

LOG_LEVELS = ['INFO', 'DEBUG']


class ConfigSection:
	pass


DUET, UI, LOGGING, ACTION, MACRO, NTFY, PUSHOVER = (ConfigSection() for _ in range(7))
_SECTIONS = {'UI': UI, 'LOGGING': LOGGING, 'ACTION': ACTION,
			 'MACRO': MACRO, 'NTFY': NTFY, 'PUSHOVER': PUSHOVER}

_config_file = None
_logger = None
# Every read-modify-write of the file holds this, so a camera change and a config page save can't overwrite each other
_lock = threading.RLock()


def _convert(value, value_type):
	"""Convert a raw value (from json, ini or form) to the schema type. Raises ValueError."""
	if value_type is bool:
		if isinstance(value, bool):
			return value
		return str(value).strip().lower() in ['true', '1', 't', 'y', 'yes', 'on']
	if value_type is int:
		try:
			return int(str(value).strip())
		except ValueError:
			raise ValueError('must be a whole number') from None
	return '' if value is None else str(value).strip()


def _validate(section, key, value):
	"""Raise ValueError if a (converted) value is not acceptable."""
	if section == 'UI' and key == 'PORT':
		# 0 = find a free port automatically at startup
		if not 0 <= value <= 65535:
			raise ValueError('must be between 0 and 65535')
	elif key == 'PORT' and not 1 <= value <= 65535:
		raise ValueError('must be between 1 and 65535')
	if key == 'MAXTIMES' and value < 0:
		raise ValueError('must be 0 or more')
	if section == 'NTFY' and key == 'PRIORITY' and not 1 <= value <= 5:
		raise ValueError('must be between 1 and 5')
	if section == 'LOGGING' and key == 'LEVEL' and value not in LOG_LEVELS:
		raise ValueError(f'must be one of {", ".join(LOG_LEVELS)}')
	if section == 'MACRO' and key == 'MACRO' and '"' in value:
		raise ValueError('must not contain quotes')


def _defaults():
	config = {section: {key: spec[1] for key, spec in keys.items()}
			  for section, keys in CONFIG_SCHEMA.items()}
	config[CAMERA_SECTION] = {}
	config[COUNTDOWN_SECTION] = dict(DEFAULT_COUNTDOWN_SETTINGS)
	return config


def _merge(target, source):
	"""Merge known, valid settings from source into target. Invalid values are logged and ignored."""
	cameras = source.get(CAMERA_SECTION)
	if isinstance(cameras, dict):
		target[CAMERA_SECTION] = {uuid: settings for uuid, settings in cameras.items() if isinstance(settings, dict)}
	countdown = source.get(COUNTDOWN_SECTION)
	if isinstance(countdown, dict):
		target[COUNTDOWN_SECTION].update({k: v for k, v in countdown.items() if k in DEFAULT_COUNTDOWN_SETTINGS})

	for section, keys in CONFIG_SCHEMA.items():
		values = {k.upper(): v for k, v in (source.get(section) or {}).items()}
		for key, (value_type, _, _) in keys.items():
			if key not in values:
				continue
			try:
				value = _convert(values[key], value_type)
				_validate(section, key, value)
				target[section][key] = value
			except ValueError as e:
				_logger.warning(f'Ignoring invalid config value {section}.{key} = {values[key]!r}: {e}')


def _checksum(payload):
	return f'{zlib.crc32(payload.encode("ascii")):08x}'


def _encode(config):
	"""Compress and base64 encode the config, prefixed with a checksum."""
	data = json.dumps(config).encode('utf-8')
	payload = base64.b64encode(zlib.compress(data, 9)).decode('ascii')
	return f'{_checksum(payload)}:{payload}'


def _decode(text):
	"""Reverse _encode. Raises ValueError if the checksum does not validate."""
	checksum, sep, payload = text.strip().partition(':')
	if not sep or not payload.isascii() or checksum != _checksum(payload):
		raise ValueError('checksum does not validate')
	try:
		data = zlib.decompress(base64.b64decode(payload, validate=True))
	except (binascii.Error, zlib.error) as e:
		raise ValueError(f'not a valid encoded config: {e}')
	config = json.loads(data.decode('utf-8'))
	if not isinstance(config, dict):
		raise ValueError('not a valid config')
	return config


def _save(config):
	with _lock:
		tmp_file = _config_file + '.tmp'
		with open(tmp_file, 'w', encoding='ascii') as f:
			f.write(_encode(config))
		os.replace(tmp_file, _config_file)


def _apply(config):
	"""Update the section objects in place so existing imports see the new values."""
	for section in CONFIG_SCHEMA:
		for key, value in config[section].items():
			setattr(_SECTIONS[section], key, value)


def _load():
	config = _defaults()
	with _lock:
		if os.path.exists(_config_file):
			try:
				with open(_config_file, 'r', encoding='utf-8') as f:
					text = f.read()
			except OSError as e:
				_logger.error(f'Could not read {_config_file} - using defaults: {e}')
				return config
			try:
				_merge(config, _decode(text))
			except ValueError as e:
				_logger.error(f'Invalid config file {_config_file} ({e}) - recreating from defaults')
				_recreate_defaults()
	return config


def _recreate_defaults():
	"""Delete the invalid config file and write a new one from the defaults."""
	try:
		os.remove(_config_file)
		_save(_defaults())
		_logger.info(f'Default configuration saved to {_config_file}')
	except OSError as e:
		_logger.error(f'Could not recreate {_config_file}: {e}')


def load_section(name):
	"""Return one of the sections managed by utils/config.py (CAMERA_SECTION or COUNTDOWN_SECTION)."""
	return _load()[name]


def save_section(name, value):
	"""Replace one of the sections managed by utils/config.py and save the file."""
	with _lock:
		config = _load()
		config[name] = value
		_save(config)


def get_DWC_config(file_path, logger):
	"""Load the configuration, creating it from the defaults if needed."""
	global _config_file, _logger
	_logger = logger
	_config_file = os.path.join(file_path, CONFIGFILENAME)
	logger.debug(f'Looking for config file at {_config_file}')

	if not os.path.exists(_config_file):
		logger.info('No configuration found - using defaults')
		try:
			_save(_defaults())
			logger.info(f'Configuration saved to {_config_file}')
		except OSError as e:
			logger.error(f'Could not save {_config_file}: {e}')

	config = _load()
	_apply(config)

	UI.HOST = '0.0.0.0'
	DUET.DWC = True
	DUET.FILE_PATH = file_path
	return True


def save_ui_address(ip, port):
	"""Record the ip and port actually in use, saving the ip if it differs from the config file.

	The port is not saved: the configured value stays as the user set it, so 0 keeps picking a free
	port at each startup, and a busy configured port is tried again next time. The config page shows
	the port in use separately (ui_port_in_use).
	"""
	UI.IP, UI.PORT = ip, port
	with _lock:
		config = _load()
		if config['UI']['IP'] == ip:
			return
		config['UI']['IP'] = ip
		try:
			_save(config)
			_logger.info(f'Saved UI address {ip} to {_config_file}')
		except OSError as e:
			_logger.error(f'Could not save {_config_file}: {e}')


def get_config_for_ui():
	"""Return the current saved settings plus field metadata."""
	config = _load()
	settings = {}
	for section, keys in CONFIG_SCHEMA.items():
		settings[section] = {}
		for key, (value_type, default, restart) in keys.items():
			if (section, key) in HIDDEN_SETTINGS:
				continue
			settings[section][key] = {
				'value': config[section][key],
				'type': value_type.__name__,
				'default': default,
				'restart': restart,
			}
	# UI.PORT is only applied at startup, so the in-memory value is the port in use
	return {'settings': settings, 'log_levels': LOG_LEVELS,
			'ui_port_in_use': getattr(UI, 'PORT', None), 'ui_ip_in_use': getattr(UI, 'IP', '')}


def update_config(updates):
	"""Validate and save settings from the config page.

	Returns (errors, restart_keys). Nothing is saved if there are errors.
	"""
	with _lock:
		return _update_config(updates)


def _update_config(updates):
	config = _load()
	errors = {}
	restart_keys = []
	live_changes = []
	log_level = LOGGING.LEVEL
	for section, keys in CONFIG_SCHEMA.items():
		values = updates.get(section) or {}
		for key, (value_type, _, restart) in keys.items():
			if key not in values or (section, key) in HIDDEN_SETTINGS:
				continue
			try:
				value = _convert(values[key], value_type)
				_validate(section, key, value)
			except ValueError as e:
				errors[f'{section}.{key}'] = str(e) or 'invalid value'
				continue
			if value != config[section][key]:
				config[section][key] = value
				if restart:
					restart_keys.append(f'{section}.{key}')
				else:
					live_changes.append((section, key, value))

	if errors:
		return errors, []

	_save(config)
	for section, key, value in live_changes:
		setattr(_SECTIONS[section], key, value)
	if LOGGING.LEVEL != log_level:
		from logger_module import set_log_level
		set_log_level(LOGGING.LEVEL, _logger)
	return {}, restart_keys
