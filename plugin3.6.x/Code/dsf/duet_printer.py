"""
Sends actions to duet printer and calls the configuration service
"""

import time
import requests
import json
import time
import sys

global MACRO_TIMES, NTFY_TIMES, PUSHOVER_TIMES
MACRO_TIMES = 0
NTFY_TIMES  = 0
PUSHOVER_TIMES = 0

global PRINTER_STATUS
PRINTER_STATUS = 'idle' # Default state is idle

def _urlCall(url, cmd, post):
	# Makes all the calls to the printer
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
			if post is False:
				# msg = f'''Connection attempt: {loop} url: {url} post:{post}'''
				# logger.debug(msg)
				r = requests.get(url, timeout=timelimit) # if using rr_ API
			else: #post includes the http command type in the url
				# msg = f'''Connection attempt {loop} url: {url} cmd: {cmd} post:{post}'''
				# logger.debug(msg)
				r = requests.post(url, timeout=timelimit, data=cmd)

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
		msg = f'''Error - Printer connection attempt failed'''
		logger.info(msg)
		return 0, ''

def _send_duet_code(command):
	global printerUrl
	# send a gcode command to Duet
	command = f'''/rr_gcode?gcode={command}'''  #Post includes command type in url
	code, _ = _urlCall(printerUrl, command, False) # Post form - sent blindly
	if code in [200,204]: #Ignore 204 as some commands do not return content
		pass
	else:
		logger.warning(f'Duet send failed with code {code}')
		logger.debug(f'{command}')
		
	return code
		
def _loginPrinter(printerUrl,duetPassword): #logon and get key parameters
	global PRINTER_STATUS
	cmd = (f'''/rr_connect?sessionKey=yes&password={duetPassword}''') # using rr_ API
	code, _ = _urlCall(printerUrl, cmd, False)
	if code in [200,204]:
		PRINTER_STATUS = get_duet_printer_status() or 'idle' # Get current printer status or default to idle
		return True
	elif code == 403:
		msg = 'Password is invalid'
	elif code == 503:
		msg = 'No more connections available'
	elif code == 502:
		msg = 'Incorrect DCS version'
	else:
		msg = f'''Is the Printer turned on?.'''
	
	msg = f'''Login issue: {msg} code = {code}'''
	logger.debug(msg)
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


def duet_send_notification(alert):
	logger.debug(f'Defect notification {alert}')
	_send_macro(alert)
	_send_ntfy(alert)
	_send_pushover(alert)
	return True

def get_duet_printer_status():
	'''
	Polled by UI and updates PRINTER_STATUS which is used
	by the suspend_print_job
	returns false if cannot get status from printer
	'''
	global PRINTER_STATUS
	cmd = f'''/rr_model?key=state'''
	code , state = _urlCall(printerUrl, cmd, False)
	if code == 200:
		j = json.loads(state)
		status = j['result']['status']
		if status != PRINTER_STATUS:
			logger.info(f'Printer status changed from {PRINTER_STATUS} to {status}')
			PRINTER_STATUS = status
		return status
	elif code == 204:
		logger.warning('No content returned when getting printer status')
		return False
	else:
		logger.critical(f'Failed to get printer status with code {code}')
		return False # Default to idle if cannot get status


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
			while PRINTER_STATUS == 'processing':
				PRINTER_STATUS = get_duet_printer_status() or 'paused' # get_duet_printer_status returns false if disconnected

	elif action  == 'resume_print':
		if PRINTER_STATUS  == 'paused':
			_duet_resume()
			_send_duet_code(f'''M291 S1 T0 P"Resumed Printing"''')
			while PRINTER_STATUS == 'paused':
				PRINTER_STATUS = get_duet_printer_status() or 'processing'

	elif action  == 'cancel_print':
		if PRINTER_STATUS =='processing': # pause the printer first
			_duet_pause()
			while PRINTER_STATUS == 'processing':
				PRINTER_STATUS = get_duet_printer_status() or 'paused'

		if PRINTER_STATUS =='paused':
			_duet_cancel()
			_send_duet_code(f'''M291 S1 T0 P"Cancelled Printing"''')
			PRINTER_STATUS = 'cancelled' # No more commands job cancelled
	else:
		logger.critical(f'Unknown action {action}')


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

if __name__ == "__main__":    # Test setup
	import os
	sys.path.append(os.path.dirname(__file__))
	from logger_module import (setup_logfile, set_log_level)
	from duet_config import get_DWC_config
	
	global logger
	file_path = sys.argv[1]
	LOGFILENAME = 'test.log'
	progName = 'test'
	CONFIGFILENAME = 'duetPrintGuard.config'

	# Create a logfile 
	logger = setup_logfile(file_path,LOGFILENAME,progName)
	# from logger_module import logger # Need to import after setup_logging is called
	logger.info(f'''{progName}''')

	if not get_DWC_config(file_path, CONFIGFILENAME,logger):
		print(f"Failed to load configuration from {file_path}. Please ensure the file exists and is properly formatted.")
		sys.exit(1)

	# Can now get config parameters
	from duet_config import DUET,LOGGING, ACTION,MACRO,NTFY,PUSHOVER

	# Set logging level
	logger = set_log_level(LOGGING.LEVEL,logger)

	printerUrl = f'http://{DUET.IP}:{DUET.PORT}'

	_loginPrinter(printerUrl,DUET.PASSWORD)

	class test:
		title = 'test'
		body = 'test body'

	duet_send_notification(test)
else:
	# This is used when running as module
	from duet_config import DUET,ACTION,MACRO,NTFY,PUSHOVER
	from logger_module import logger

	printerUrl = f'http://{DUET.IP}:{DUET.PORT}'
	
	if _loginPrinter(printerUrl,DUET.PASSWORD):
		logger.info(f'Successful login to printer at {printerUrl}')
	else:
		if DUET.POWERCHECK:
			logger.critical(f'Failed to login to printer at {printerUrl} - check printer is turned on')
			logger.critical(f'Failed to login to printer at {printerUrl} - check printer is turned on')
			sys.exit(1)


