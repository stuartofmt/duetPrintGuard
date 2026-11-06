"""
What duetPrintGuard does with the printer: keeps the connection and status up to date, pauses / resumes /
cancels the print, and sends the defect notifications.

The communication itself is in duet_printer.py - the same module as duetLapse3 - which works with a standalone
board (rr_ api) or an SBC (/machine api and WebSocket), found out when logging in.
"""

import os
import threading
import time
import urllib.parse

import requests

import duet_printer
import state  # Shared state - always use state.<name>
from duet_printer import forgetPrinter, getDuet, getDuetVersion, getStatus, loginPrinter, printerAddress, sendDuetGcode
from logger_module import logger
from duet_config import ACTION, DUET, MACRO, NTFY, PUSHOVER

global MACRO_TIMES, NTFY_TIMES, PUSHOVER_TIMES
MACRO_TIMES = 0
NTFY_TIMES  = 0
PUSHOVER_TIMES = 0

POLL_SECONDS = 5  # Between status checks - a standalone board drops a session after 8 seconds with no requests
RECONNECT_SECONDS = 10  # Between attempts to connect
STATUS_WAIT_SECONDS = 60  # How long to wait for the printer to reach a state after a pause / resume (e.g. finishing the current move)
DSF_PLUGIN_DIR = '/opt/dsf/plugins/'

_status = 'disconnected'
_connected = False
_error = ''  # Why the printer can not be connected, for the pages
_wake = threading.Event()  # The printer changed (SBC), or the printer settings did - check now
_passwordRefused = False  # No more tries until the printer settings change
_settingsChanges = 0  # Counts changes of the printer settings, to spot one made during a login


# ------------------------------------------------------------
# Connection
# ------------------------------------------------------------

def running_as_plugin():
	"""True if DSF installed this copy of the program as its plugin (only then is there plugin data to publish to)."""
	return os.path.realpath(__file__).startswith(DSF_PLUGIN_DIR)


def _apply_printer_settings():
	# A plugin is always on the same computer as its printer.  The password goes in a url, so it is encoded
	state.duet = '127.0.0.1' if state.plugin else (DUET.IP or '127.0.0.1')
	state.duet_port = DUET.PORT
	state.duet_password = urllib.parse.quote(DUET.PASSWORD, safe='')


def start_printer_monitor():
	"""Connect to the printer and keep its status up to date, in the background - the pages run with or without a printer."""
	state.plugin = running_as_plugin()
	state.pid = str(os.getpid())
	state.terminateState = -1
	state.connectionState = False
	state.urlHeaders = {}
	state.apiModel = ''
	state.lastStatusCall = 0
	state.lastMessageSeq = None
	_apply_printer_settings()
	duet_printer.onChange = _wake.set  # SBC - the WebSocket brought a change
	threading.Thread(name='printerMonitor', target=_monitor, daemon=True).start()


def printer_settings_changed():
	"""The printer settings were changed on the Configuration page - connect again with the new ones."""
	global _passwordRefused, _settingsChanges
	_apply_printer_settings()
	state.apiModel = ''
	_passwordRefused = False
	_settingsChanges += 1
	forgetPrinter()
	_set_status('disconnected', False, '')
	logger.info(f'Printer settings changed - connecting to {printerAddress()}')
	_wake.set()


def _set_status(status, connected, error=''):
	global _status, _connected, _error
	if connected != _connected:
		logger.info(f'Printer at {printerAddress()} ' + ('connected' if connected else 'is not responding'))
	if error != _error and error:
		logger.warning(error)
	_status, _connected, _error = status, connected, error


def _connect():
	global _passwordRefused
	changes = _settingsChanges
	model, code = loginPrinter()
	if changes != _settingsChanges:
		return  # The answer is from the old printer - the monitor connects again with the new settings
	if model == '':
		if code == 403:
			_passwordRefused = True
			_set_status('disconnected', False, f'The printer at {printerAddress()} did not accept the password')
		else:
			_set_status('disconnected', False, f'The printer at {printerAddress()} is not responding')
		return
	state.apiModel = model
	logger.info(f'Connected to printer at {printerAddress()} using {model} - firmware {getDuetVersion(model)}')
	_poll()


def _poll():
	global _passwordRefused
	status = getDuet(getStatus)[0]
	if status != 'disconnected':
		_set_status(status, True)
		return
	_set_status('disconnected', False, f'The printer at {printerAddress()} is not responding')
	model, code = loginPrinter(state.apiModel)  # A new session for when it answers again
	if code == 403:
		state.apiModel = ''
		_passwordRefused = True
		_set_status('disconnected', False, f'The printer at {printerAddress()} did not accept the password')


def _monitor():
	while True:
		try:
			if _passwordRefused:
				pass  # Trying again would not help - wait for the settings to change
			elif state.apiModel:
				_poll()
			else:
				_connect()
		except Exception as e:  # e.g. a printer address that can not be used - keep the thread going
			logger.warning(f'Could not check the printer at {printerAddress()}: {e}')
			_set_status('disconnected', False, f'Could not connect to the printer at {printerAddress()}: {e}')
		_wake.wait(None if _passwordRefused else (POLL_SECONDS if _connected else RECONNECT_SECONDS))
		_wake.clear()


def get_duet_printer_status():
	"""The printer status (e.g. 'idle', 'processing', 'paused'), or 'disconnected'.  Never waits for the printer."""
	return _status


def printer_info():
	"""The connection, for the pages."""
	return {
		'status': _status,
		'connected': _connected,
		'address': printerAddress() if state.duet else '',
		'api': {'SBC': 'SBC', 'rr_model': 'standalone'}.get(state.apiModel, ''),
		'plugin': bool(state.plugin),
		'error': _error,
	}


# ------------------------------------------------------------
# Send Gcode command
# ------------------------------------------------------------

def _send_duet_code(command):
	"""Send a G/M-code to the printer."""
	if not state.apiModel:
		logger.error(f'Could not send {command} - the printer is not connected')
		return
	sendDuetGcode(state.apiModel, command)
	logger.debug(f'Sent {command} to the printer')


def _wait_for_status(wanted, timeout=STATUS_WAIT_SECONDS):
	"""Wait until the printer reports the wanted status. Returns False if it does not within timeout."""
	deadline = time.time() + timeout
	status = _status
	while time.time() < deadline:
		status = getStatus()[0]
		if status == wanted:
			return True
		time.sleep(0.5)
	logger.warning(f'Printer did not reach "{wanted}" within {timeout} seconds (status is "{status}")')
	return False


def _duet_pause():
	pause_command = 'M25'

	if ACTION.PAUSE != '':
		pause_command = ACTION.PAUSE

	msg = f'Pausing  print with command {pause_command}'
	_send_duet_code(f'''echo "{msg}"''')
	return _send_duet_code(pause_command)

def _duet_resume():
	resume_command = 'M24'

	if ACTION.RESUME != '':
		resume_command = ACTION.RESUME

	msg = f'Resuming print with command {resume_command}'
	_send_duet_code(f'''echo "{msg}"''')
	return _send_duet_code(resume_command)

def _duet_cancel():
	cancel_command = 'M2'  # Currently equivalent to M0

	if ACTION.CANCEL != '':
		cancel_command = ACTION.CANCEL

	msg = f'Cancelling print with command {cancel_command}'
	_send_duet_code(f'''echo "{msg}"''')
	return _send_duet_code(cancel_command)		


def suspend_print_job(action):
	"""Pause, resume or cancel the print. Blocking - call it from a thread (asyncio.to_thread).

	Commands are only sent if the printer is in the right state, so requests from more than
	one camera (or the UI) do not send the same command twice.
	"""
	status = getStatus()[0] if state.apiModel else 'disconnected'
	if status == 'disconnected':
		logger.error(f'Could not {action} - the printer is not connected')
		return
	if action == 'pause_print':
		if status == 'processing':
			_duet_pause()
			_send_duet_code('''M291 S1 T0 P"Paused Printing"''')
			_wait_for_status('paused')

	elif action == 'resume_print':
		if status == 'paused':
			_duet_resume()
			_send_duet_code('''M291 S1 T0 P"Resumed Printing"''')
			_wait_for_status('processing')

	elif action == 'cancel_print':
		if status == 'processing': # A print must be paused before it can be cancelled
			_duet_pause()
			if _wait_for_status('paused'):
				status = 'paused'
		if status == 'paused':
			_duet_cancel()
			_send_duet_code('''M291 S1 T0 P"Cancelled Printing"''')
	else:
		logger.critical(f'Unknown action {action}')


def duet_send_notification(alert):
	logger.debug(f'Defect notification {alert}')
	_send_macro(alert)
	_send_ntfy(alert)
	_send_pushover(alert)
	return True

# Retries for _urlCall - long enough to ride out a brief network drop-out (it runs in a background thread)
RETRY_DELAYS = (2, 5)  # seconds to wait before the 2nd and 3rd attempts
RETRY_STATUSES = (502, 503, 504)  # the server asks to try again later - the request was not processed
URL_TIMEOUT = (3, 10)  # seconds to connect, seconds to wait for the reply


def _urlCall(url, data=None, post=True, json_data=None, headers=None, timeout=URL_TIMEOUT):
	"""Make an HTTP request (POST, or GET when post is False), retrying when it may not have got through.

	data is sent as a form / raw body, json_data as a JSON body.
	Retried: connection errors, timeouts and 502 / 503 / 504. Not retried: any other error status - e.g.
	a bad token (4xx) or 429 (rate limit / quota), where asking again would get the same answer.
	A retry after a reply timeout can occasionally repeat a request that had arrived - for an alert, a
	duplicate is better than nothing.

	Returns (status_code, text) - status_code is 0 if no response was received.
	The request data is never logged, as it can contain credentials.
	"""
	method = 'POST' if post else 'GET'
	attempts = len(RETRY_DELAYS) + 1
	r = None
	for attempt in range(1, attempts + 1):
		r = None
		try:
			r = requests.request(method, url, data=data, json=json_data, headers=headers, timeout=timeout)
		except requests.exceptions.Timeout:
			logger.warning(f'{method} {url} timed out - the destination may be unreachable (attempt {attempt}/{attempts})')
		except requests.exceptions.ConnectionError as e:
			logger.warning(f'{method} {url} could not connect (attempt {attempt}/{attempts}): {e}')
		except requests.exceptions.RequestException as e:
			logger.warning(f'{method} {url} failed: {type(e).__name__}: {e}')
			break  # e.g. an invalid URL - retrying will not help
		else:
			if r.ok:
				return r.status_code, r.text or ''
			if r.status_code not in RETRY_STATUSES:
				break
			logger.warning(f'{method} {url} returned {r.status_code} (attempt {attempt}/{attempts})')
		if attempt < attempts:
			time.sleep(RETRY_DELAYS[attempt - 1])

	if r is not None:
		logger.info(f'{method} {url} failed with {r.status_code}: {r.text[:200]}')
		return r.status_code, r.text
	logger.info(f'{method} {url} failed - no response')
	return 0, ''


def reset_notification_counters():
	global MACRO_TIMES, NTFY_TIMES, PUSHOVER_TIMES
	MACRO_TIMES = 0
	NTFY_TIMES = 0
	PUSHOVER_TIMES = 0


def _send_macro(alert):
	global MACRO_TIMES
	try:
		if MACRO.MACRO != '':
			if MACRO_TIMES < MACRO.MAXTIMES:
				msg = f'M98 P"{MACRO.MACRO}"'
				_send_duet_code(msg)
				MACRO_TIMES += 1
				logger.info(f'MACRO {msg} sent {MACRO_TIMES} time(s)')	
	except Exception as e:
		logger.info(f'Error sending macro:  {e}')
	return True	



def _send_ntfy(alert):
	global NTFY_TIMES
	try:
		if NTFY.TOPIC != '': # OK to send
			if NTFY_TIMES < NTFY.MAXTIMES:		
				title = ''
				message = ''
				if NTFY.TITLE !='':
					title = NTFY.TITLE
				else:
					title = alert['title']

				if NTFY.MESSAGE !='':
					message = NTFY.MESSAGE
				else:
					message = alert['body']

				payload = {
					"topic": NTFY.TOPIC,
					"title": title,
					"priority": int(NTFY.PRIORITY),
					"message": message,
				}

				code, _ = _urlCall('https://ntfy.sh', json_data=payload)
				if 200 <= code < 300:
					NTFY_TIMES += 1
					logger.info(f'NTFY with title {title} sent {NTFY_TIMES} time(s)')	
					return True
				else:
					logger.info(f'NTFY send failed with code {code}')
					return False
	except Exception as e:
		logger.info(f'Error sending NTFY:  {e}')
	return True

	
def _send_pushover(alert):
	global PUSHOVER_TIMES
	try:
		if PUSHOVER.API != '' and PUSHOVER.USER != '': # OK to send
			if PUSHOVER_TIMES < PUSHOVER.MAXTIMES:
				title = ''
				message = ''
				if PUSHOVER.TITLE !='':
					title = PUSHOVER.TITLE
				else:
					title = alert['title']
				if PUSHOVER.MESSAGE !='':
					message = PUSHOVER.MESSAGE
				else:
					message = alert['body']

				logger.info(f'Sending PUSHOVER with title {title}')

				data = {
					"token": PUSHOVER.API,
					"user": PUSHOVER.USER,
					"title":title,
					"message": message,
					}

				code, _ = _urlCall("https://api.pushover.net/1/messages.json", data)
				if 200 <= code < 300:
					PUSHOVER_TIMES += 1
					logger.info(f'Pushover with title {title} sent {PUSHOVER_TIMES} time(s)')	
					return True
				else:
					logger.info(f'PUSHOVER send failed with code {code}')
					return False
	except Exception as e:
		logger.info(f'Error sending PUSHOVER:  {e}')
	return True
