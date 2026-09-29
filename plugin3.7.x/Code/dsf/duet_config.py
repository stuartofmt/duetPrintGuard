"""
Application configuration for duetPrintGuard

Settings are held in duetPrintGuard.json (in the plugin's sys directory)
and are edited through the /config web page.
No config file is required - defaults are used for anything not set.

If a legacy duetPrintGuard.config (ini format) exists and there is no
json file yet, its values are imported once on startup.

The section objects (DUET, UI, etc.) are created on import and are only
ever updated in place, so modules that import them see live changes.
"""
import configparser
import json
import os
import socket

global DUET, UI, LOGGING, ACTION, MACRO, NTFY, PUSHOVER

CONFIGFILENAME = 'duetPrintGuard.json'
LEGACYCONFIGFILENAME = 'duetPrintGuard.config'

# section -> key -> (type, default, restart_required)
CONFIG_SCHEMA = {
	'DUET': {
		'IP': (str, '', True),        # Blank = auto-detect this machine's ip address
		'PORT': (int, 80, True),
		'PASSWORD': (str, 'reprap', True),
		'POWERCHECK': (bool, True, True),
	},
	'UI': {
		'PORT': (int, 8002, True),
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

# Values that are never sent to the browser
SECRET_SETTINGS = {('DUET', 'PASSWORD')}

LOG_LEVELS = ['WARNING', 'INFO', 'DEBUG']


class ConfigSection:
	pass


DUET, UI, LOGGING, ACTION, MACRO, NTFY, PUSHOVER = (ConfigSection() for _ in range(7))
_SECTIONS = {'DUET': DUET, 'UI': UI, 'LOGGING': LOGGING, 'ACTION': ACTION,
			 'MACRO': MACRO, 'NTFY': NTFY, 'PUSHOVER': PUSHOVER}

_config_file = None
_logger = None


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
	if key == 'PORT' and not 1 <= value <= 65535:
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
	return {section: {key: spec[1] for key, spec in keys.items()}
			for section, keys in CONFIG_SCHEMA.items()}


def _merge(target, source):
	"""Merge known, valid settings from source into target. Invalid values are logged and ignored."""
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


def _read_legacy_config(file_path):
	"""Read a legacy ini style config file. Commented out (;) or blank values are skipped."""
	parser = configparser.ConfigParser()
	parser.read(file_path)
	return {section.upper(): {k: v for k, v in parser.items(section) if v.strip() != ''}
			for section in parser.sections()}


def _save(config):
	tmp_file = _config_file + '.tmp'
	with open(tmp_file, 'w', encoding='utf-8') as f:
		json.dump(config, f, indent=2)
	os.replace(tmp_file, _config_file)


def _apply(config):
	"""Update the section objects in place so existing imports see the new values."""
	for section, values in config.items():
		for key, value in values.items():
			setattr(_SECTIONS[section], key, value)


def get_local_ip():
	"""Get the ip address of this machine."""
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect(('10.255.255.255', 1))  # doesn't even have to be reachable
		return s.getsockname()[0]
	except Exception:
		return '127.0.0.1'
	finally:
		s.close()


def _load():
	config = _defaults()
	if os.path.exists(_config_file):
		try:
			with open(_config_file, 'r', encoding='utf-8') as f:
				_merge(config, json.load(f))
		except (OSError, json.JSONDecodeError) as e:
			_logger.error(f'Could not read {_config_file} - using defaults: {e}')
	return config


def get_DWC_config(file_path, logger):
	"""Load the configuration, creating it (from defaults or a legacy config file) if needed."""
	global _config_file, _logger
	_logger = logger
	_config_file = os.path.join(file_path, CONFIGFILENAME)
	logger.debug(f'Looking for config file at {_config_file}')

	if not os.path.exists(_config_file):
		config = _defaults()
		legacy_file = os.path.join(file_path, LEGACYCONFIGFILENAME)
		if os.path.exists(legacy_file):
			logger.info(f'Importing settings from {legacy_file}')
			_merge(config, _read_legacy_config(legacy_file))
		else:
			logger.info('No configuration found - using defaults')
		try:
			_save(config)
			logger.info(f'Configuration saved to {_config_file}')
		except OSError as e:
			logger.error(f'Could not save {_config_file}: {e}')

	config = _load()
	_apply(config)

	if not DUET.IP:
		DUET.IP = get_local_ip()
		logger.info(f'Using detected ip address {DUET.IP}')
	UI.HOST = '0.0.0.0'
	DUET.DWC = True
	DUET.FILE_PATH = file_path
	return True


def get_config_for_ui():
	"""Return the current saved settings, with secrets removed, plus field metadata."""
	config = _load()
	settings = {}
	for section, keys in CONFIG_SCHEMA.items():
		settings[section] = {}
		for key, (value_type, default, restart) in keys.items():
			secret = (section, key) in SECRET_SETTINGS
			settings[section][key] = {
				'value': '' if secret else config[section][key],
				'type': value_type.__name__,
				'default': '' if secret else default,
				'restart': restart,
				'secret': secret,
				'is_set': config[section][key] != default if secret else None,
			}
	return {'settings': settings, 'detected_ip': get_local_ip(), 'log_levels': LOG_LEVELS}


def update_config(updates):
	"""Validate and save settings from the config page.

	Blank secret values leave the stored value unchanged.
	Returns (errors, restart_keys). Nothing is saved if there are errors.
	"""
	config = _load()
	errors = {}
	restart_keys = []
	live_changes = []
	log_level = LOGGING.LEVEL
	for section, keys in CONFIG_SCHEMA.items():
		values = updates.get(section) or {}
		for key, (value_type, _, restart) in keys.items():
			if key not in values:
				continue
			if (section, key) in SECRET_SETTINGS and str(values[key]) == '':
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
