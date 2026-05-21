"""
Sends actions to duet printer and calls the configuration service
"""

import time
import requests
import json
import time
import sys

def _urlCall(url, cmd, post):
	# Makes all the calls to the printer
	# If post is True then make a http post call
	# Get commands need a leading /
	# Set defaults for return codes
	code = 0
	error = 'Unknown'

	timelimit = 5  # timout for call to return
	loop = 0
	limit = 2  # seems good enough to catch transients
	r = ''
	if post is False:
		url = url + cmd  # concatenate for GET
	while loop < limit:
		try:
			if post is False:
				msg = f'''Connection attempt: {loop} url: {url} post:{post}'''
				logger.debug(msg)
				r = requests.get(url, timeout=timelimit) # if using rr_ API
			else: #post includes the http command type in the url
				msg = f'''Connection attempt {loop} url: {url} cmd: {cmd} post:{post}'''
				logger.debug(msg)
				r = requests.post(url, timeout=timelimit, data=cmd)

		except requests.ConnectionError as e:
			msg = 'Cannot connect to url - maybe a network error'
			logger.debug(msg)
		except requests.exceptions.Timeout as e:
			msg = 'Timed out - Is the printer turned on?'
			logger.debug(msg)
		except Exception as e:
			logger.info(f'Connection failure this a valid url ==> {url}')
			logger.debug(e)
		finally:
			if r and r.status_code in [200,204]: #204 is no content e.g. disconnect
				return r.status_code, r.text
			else:
				time.sleep(1)
				loop += 1 # Loop back and try again
	if r:
		msg = f'''Error - code = {r.status_code} payload = {r.text}'''
		logger.info(msg)
		return r.status_code, r.text
	else:
		msg = f'''Error - connection attempt failed'''
		logger.info(msg)
		return 0, ''

def _send_duet_code(command):
	# send a gcode command to Duet
	command = f'''/rr_gcode?gcode={command}'''  #Post includes command type in url
	code, _ = _urlCall(printerURL, command, False) # Post form - sent blindly
	if code in [200,204]:
		pass
	else:
		logger.info(f'Duet send failed with code {code}')
		logger.debug(f'{command}')
		
	return code
		
def _loginPrinter(printerUrl,duetPassword): #logon and get key parameters
	global suspend_status
	cmd = (f'''/rr_connect?sessionKey=yes&password={duetPassword}''') # using rr_ API
	code, _ = _urlCall(printerUrl, cmd, False)
	if code in [200,204]:
		suspend_status = 'running'
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

def get_printer_config(camera_uuid):
	return None


def suspend_print_job(action):
	global suspend_status
	logger.warning(f'Requested action {action} --- current status {suspend_status}')
	
	# Use of suspend_status is to account for request from more than one camera
	# Do not want to send multiple commands of the same type
	# Need to allow for cancellation of request from one or other camera
	# States are 'running' ==> 'paused' ==> 'cancelled' after which no more commands sent
	if action  == 'pause_print':
		if suspend_status  == 'running':
			suspend_status = 'paused'
			_duet_pause()
			_send_duet_code(f'''M291 S1 T0 P"Paused Printing"''')

	elif action  == 'cancel_print':
		if suspend_status =='running':
			suspend_status ='paused'
			_duet_pause()

		time.sleep(2) #  Allow any prior pause to settle	

		if suspend_status =='paused':
			suspend_status = 'cancelled' # No more requests to printer
			_duet_cancel()
			_send_duet_code(f'''M291 S1 T0 P"Cancelled Printing"''')
	else:
		logger.critical(f'Unknown action {action}')


def _send_macro(alert):
	if MACRO.MACRO != '':
		msg = f'M98 P"{MACRO.MACRO}"'
		logger.info(f'Sending macro {msg}')
		_send_duet_code(msg)


def _send_ntfy(alert):
	if NTFY.TOPIC != '':
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

		if NTFY.PRIORITY !='':
			priority = int(NTFY.PRIORITY)
		else:
			priority = 3

		logger.info(f'Sending NTFY with title {title}')	

		data=json.dumps({
			"Topic": NTFY.TOPIC,
			"Title": title,
			"Priority": priority,
			"Message": message,
			})
	
	code, _ = _urlCall('https://ntfy.sh', data, True)
	if code in [200,204]:
		return True
	else:
		logger.info(f'NTFY send failed with code {code}')
		logger.debug(f'\n{data}\n')
		return False
	
def _send_pushover(alert):
	if PUSHOVER.API != '':
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
			return True
		else:
			logger.info(f'PUSHOVER send failed with code {code}')
			logger.debug(f'\n{data}\n')
			return False	


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

	printerURL = f'http://{DUET.IP}:{DUET.PORT}'

	_loginPrinter(printerURL,DUET.PASSWORD)

	class test:
		title = 'test'
		body = 'test body'

	duet_send_notification(test)
else:
	# This is used when running as module
	from duet_config import DUET,ACTION,MACRO,NTFY,PUSHOVER
	from logger_module import logger

	printerURL = f'http://{DUET.IP}:{DUET.PORT}'
	
	if _loginPrinter(printerURL,DUET.PASSWORD):
		logger.info(f'Successful login to printer at {printerURL}')
	else:
		if DUET.POWERCHECK:
			logger.critical(f'Failed to login to printer at {printerURL} - check printer is turned on')
			logger.critical(f'Failed to login to printer at {printerURL}')
			sys.exit(1)


