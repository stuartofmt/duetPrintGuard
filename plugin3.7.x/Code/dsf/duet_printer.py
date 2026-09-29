"""
Sends actions to duet printer and calls the configuration service
"""

import time
import requests
import json
import time
import threading
import asyncio

from logger_module import logger
from duet_config import ACTION, MACRO, NTFY, PUSHOVER

global MACRO_TIMES, NTFY_TIMES, PUSHOVER_TIMES
MACRO_TIMES = 0
NTFY_TIMES  = 0
PUSHOVER_TIMES = 0

global PRINTER_STATUS
PRINTER_STATUS = 'idle' # Default state is idle

from dsf.connections import SubscribeConnection, SubscriptionMode, CommandConnection
from dsf.object_model.inputs import inputs as _inputs
from dsf.object_model.job.gcode_fileinfo import GCodeFileInfo



# Workaround: dsf-python 3.7.0b1 rejects null entries in the inputs collection,
# but DSF reports unused input channels as null
_orig_inputs_init = _inputs.Inputs.__init__
def _inputs_init(self):
	_orig_inputs_init(self)
	self._allow_none = True
_inputs.Inputs.__init__ = _inputs_init

# Workaround: dsf-python 3.7.0b1 declares job.file.customInfo as non-nullable,
# but DSF patches it to null when there is no job file. Treat null as "clear"
_custom_info_prop = GCodeFileInfo.custom_info
def _set_custom_info(self, value):
	if value is None:
		self.custom_info.clear()
	else:
		_custom_info_prop.fset(self, value)
GCodeFileInfo.custom_info = _custom_info_prop.setter(_set_custom_info)

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


unsubscribe = subscription.subscribe_to_keys(
	["state.status"],
	handle_change,
)

async def duetStatus():
	while True:
		logger.debug('Checking object model')
		object_model = subscription.get_object_model()
		await asyncio.sleep(5)

# ------------------------------------------------------------
# Send Gcode command
# ------------------------------------------------------------

def _send_duet_code(command):
    command_connection = CommandConnection(debug=True)
    command_connection.connect()

    try:
        # res = command_connection.set_plugin_data("ExecOnMcode", "test", "1")
        # Perform a simple command and wait for its output
        res = command_connection.perform_simple_code("command")
        print(f'Response from {command} was: {res}')
    finally:
        command_connection.close()

def _urlCall(url, cmd, post):
	# If post is True then make a http post call
	# Get commands need a leading /
	# Set defaults for return codes
	code = 0
	error = ''

	timelimit = 5  # timout for call to return
	loop = 0
	limit = 2  # seems good enough to catch transients
	r = ''
	if post is False:
		url = url + cmd  # concatenate for GET
	while loop < limit:
		try:
			if post is False: # get includes the http command type in the url
				r = requests.get(url, timeout=timelimit) # if using rr_ API
			else: #post 
				r = requests.post(url, timeout=timelimit, data=cmd)

		except requests.exceptions.RequestException as e:
			logger.warning(f'''{type(e).__name__} , {e}''')		

		except requests.ConnectionError as e:
			msg = 'Cannot connect to url - maybe a network error'
			logger.warning(msg)
		except requests.exceptions.Timeout as e:
			msg = 'Timed out - Is the printer turned on?'
			logger.warning(msg)
		except Exception as e:
			logger.info(f'Connection failure this a valid url ==> {url}')
			logger.warning(e)
		finally:
			if r and r.status_code in [200,204]: #204 is no content e.g. disconnect
				return r.status_code, r.text or ''
			else:
				time.sleep(1)
				loop += 1 # Loop back and try again
	if r:
		msg = f'''Error - code = {r.status_code} payload = {r.text}'''
		logger.info(msg)
		return r.status_code, r.text
	else:
		msg = f'''Error - Printer connection attempt failed url = {url} cmd = {cmd} post = {post}'''
		logger.info(msg)
		return 0, ''


def _loginPrinter():
    logger.info('Logging in')
    object_model = subscription.get_object_model()
    if object_model.state.status.value == 'disconnected':
        return False
    threading.Thread(target=lambda: asyncio.run(duetStatus()), daemon=True).start()
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

def get_duet_printer_status():
	return PRINTER_STATUS


def suspend_print_job(action):
	global PRINTER_STATUS	
	# Use of PRINTER_STATUS is to account for request from more than one camera
	# Do not want to send multiple commands of the same type
	# Need to allow for cancellation of request from one or other camera
	# States are 'idle' ==> 'processing' ==> 'paused' ==> 'cancelled' after which no more commands sent
	# or 'idle' ==> 'processing' ==> 'paused' ==> resumed ==> 'cancelled' ==> 'idle'

	get_duet_printer_status() # Updates PRINTER_STATUS
	if action  == 'pause_print':
		if PRINTER_STATUS  == 'processing':
			_duet_pause()
			_send_duet_code(f'''M291 S1 T0 P"Paused Printing"''')
			# There is possibility of UI calling get_duet_status
			# which changes PRINTER_STATUS before we get here
			while PRINTER_STATUS != 'paused':
				PRINTER_STATUS = get_duet_printer_status() or 'paused' # get_duet_printer_status returns false if disconnected

	elif action  == 'resume_print':
		if PRINTER_STATUS  == 'paused':
			_duet_resume()
			_send_duet_code(f'''M291 S1 T0 P"Resumed Printing"''')
			while PRINTER_STATUS != 'processing':
				PRINTER_STATUS = get_duet_printer_status() or 'processing'

	elif action  == 'cancel_print':
		if PRINTER_STATUS =='processing': # pause the printer first
			_duet_pause()
			while PRINTER_STATUS != 'paused':
				PRINTER_STATUS = get_duet_printer_status() or 'paused'

		if PRINTER_STATUS =='paused':
			_duet_cancel()
			_send_duet_code(f'''M291 S1 T0 P"Cancelled Printing"''')
			# Actual printer status will go to 'idle'
			# but we set to cancelled to stop any more commands being sent
			PRINTER_STATUS = 'cancelled' 
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
	print(f'{NTFY_TIMES=}')
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

				data=json.dumps({
					"Topic": NTFY.TOPIC,
					"Title": title,
					"Priority": int(NTFY.PRIORITY),
					"Message": message,
					})
				
			
				code, _ = _urlCall('https://ntfy.sh', data, True)
				if code in [200,204]:
					NTFY_TIMES += 1
					logger.info(f'NTFY with title {title} sent {NTFY_TIMES} time(s)')	
					return True
				else:
					logger.info(f'NTFY send failed with code {code}')
					logger.debug(f'\n{data}\n')
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

				code, _ = _urlCall("https://api.pushover.net/1/messages.json", data, True)
				if code in [200,204]:
					PUSHOVER_TIMES += 1
					logger.info(f'Pushover with title {title} sent {PUSHOVER_TIMES} time(s)')	
					return True
				else:
					logger.info(f'PUSHOVER send failed with code {code}')
					logger.debug(f'\n{data}\n')
					return False
	except Exception as e:
		logger.info(f'Error sending PUSHOVER:  {e}')
	return True




