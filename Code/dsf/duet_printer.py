"""
Sends actions to duet printer and calls the configuration service
"""

import time
import requests
import threading

from logger_module import logger
from duet_config import ACTION, MACRO, NTFY, PUSHOVER

global MACRO_TIMES, NTFY_TIMES, PUSHOVER_TIMES
MACRO_TIMES = 0
NTFY_TIMES  = 0
PUSHOVER_TIMES = 0

global PRINTER_STATUS
PRINTER_STATUS = 'idle' # Default state is idle

from dsf.connections import SubscribeConnection, SubscriptionMode, CommandConnection

# ------------------------------------------------------------
# Callback for Poll object model
# ------------------------------------------------------------


def handle_change(*, key, data, indices):
	global PRINTER_STATUS
	logger.debug(f' dsf-python object model change: {key} , {data} , {indices}')

	if key == 'state.status':
		PRINTER_STATUS = data


# ------------------------------------------------------------
# Poll object model
# ------------------------------------------------------------

subscription = SubscribeConnection(SubscriptionMode.PATCH)
subscription.connect()
object_model = subscription.get_object_model()
# handle_change only sees later changes, so start from the current status (e.g. started mid-print)
PRINTER_STATUS = getattr(object_model.state.status, 'value', object_model.state.status)

# get_object_model() applies the patches DSF has queued (without blocking) and runs handle_change.
# It is called from several threads, so it is serialised.
_object_model_lock = threading.Lock()

unsubscribe = subscription.subscribe_to_keys(
	["state.status"],
	handle_change,
)


def _refresh_object_model():
	with _object_model_lock:
		return subscription.get_object_model()


def _drain_object_model():
	"""Keep applying patches so they do not pile up between status checks."""
	while True:
		try:
			_refresh_object_model()
		except Exception as e:
			logger.warning(f'Could not update the printer object model: {e}')
		time.sleep(1)

# ------------------------------------------------------------
# Send Gcode command
# ------------------------------------------------------------

def _send_duet_code(command):
	"""Send a G/M-code to the printer and return its reply ('' if it could not be sent)."""
	command_connection = CommandConnection()
	try:
		command_connection.connect()
		res = command_connection.perform_simple_code(command)
		logger.debug(f'Response from {command} was: {res}')
		return res
	except Exception as e:
		logger.error(f'Could not send {command} to the printer: {e}')
		return ''
	finally:
		command_connection.close()

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


def publish_ui_address(ip, port):
	# The DWC page reads these from the object model to build its iframe url
	command_connection = CommandConnection()
	try:
		command_connection.connect()
		command_connection.set_plugin_data('duetPrintGuard', 'ip', ip)
		command_connection.set_plugin_data('duetPrintGuard', 'port', port)
		logger.info(f'Published UI address {ip}:{port} to plugin data')
	except Exception as e:
		logger.warning(f'Could not publish UI address to plugin data: {e}')
	finally:
		command_connection.close()


def _loginPrinter():
	logger.info('Logging in')
	object_model = _refresh_object_model()
	if object_model.state.status.value == 'disconnected':
		return False
	threading.Thread(target=_drain_object_model, daemon=True).start()
	return True

		
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


def duet_send_notification(alert):
	logger.debug(f'Defect notification {alert}')
	_send_macro(alert)
	_send_ntfy(alert)
	_send_pushover(alert)
	return True

# How long to wait for the printer to reach a state after a pause / resume (e.g. finishing the current move)
STATUS_WAIT_SECONDS = 60


def get_duet_printer_status():
	"""Return the printer status (e.g. 'idle', 'processing', 'paused'), applying any queued changes first."""
	try:
		_refresh_object_model()
	except Exception as e:
		logger.warning(f'Could not update the printer status: {e}')
	return PRINTER_STATUS


def _wait_for_status(wanted, timeout=STATUS_WAIT_SECONDS):
	"""Wait until the printer reports the wanted status. Returns False if it does not within timeout."""
	deadline = time.time() + timeout
	while time.time() < deadline:
		if get_duet_printer_status() == wanted:
			return True
		time.sleep(0.5)
	logger.warning(f'Printer did not reach "{wanted}" within {timeout} seconds (status is "{PRINTER_STATUS}")')
	return False


def suspend_print_job(action):
	"""Pause, resume or cancel the print. Blocking - call it from a thread (asyncio.to_thread).

	Commands are only sent if the printer is in the right state, so requests from more than
	one camera (or the UI) do not send the same command twice.
	"""
	status = get_duet_printer_status()
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




