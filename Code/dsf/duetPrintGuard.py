"""
The she-bang is not required if called with fully qualified paths
The plugin manager does this.  Otherwise use ...
Standard python install e.g.
#!/usr/bin/python3 -u
Venv python install e.g.
#! <path-to-virtual-environment/bin>python -u
"""
# 3D Printer spaghetti detection

# Author Stuartofmt - chunks of code sourced from various internet examples
# Released under The MIT License. Full text available via https://opensource.org/licenses/MIT

# This is based on the app PrintGuard.
# https://github.com/oliverbravery/PrintGuard
# This plugin removed much of the code to streamline
# and make itmore suited to the DWC environment

"""
Version 1.0.0 - Initial release
"""

import sys
import os
import socket

sys.path.append(os.path.dirname(__file__))

from logger_module import (setup_logfile, set_log_level)
from duet_config import get_DWC_config

global progName, progVersion
progName = 'duetPrintGuard'
progVersion = '1.0.0'
# Min python version
pythonMajor = 3
pythonMinor = 9

LOGFILENAME = 'duetPrintGuard.log'


def port_in_use(ip_address, port):
	#  A successful connection means something is already listening there
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.settimeout(1)
		return sock.connect_ex((ip_address, port)) == 0


def validate_port(port=0, start_port=17800, max_tries=100):
	#  Get the local ip address
	this_ip_address = ''
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect(('10.255.255.255', 1))  # doesn't even have to be reachable
		this_ip_address = s.getsockname()[0]
	except Exception as e:
		logger.critical(f'''Unknown error trying to get the local IP address''')
		logger.critical(f'''{e}''')
		force_quit(1)
	finally:
		s.close()

	if port:
		#  A port was provided - check that it is available
		if port_in_use(this_ip_address, port):
			logger.warning(f'''Port {port} is already in use - falling back to searching from {start_port}''')
			port = 0
	else:
		logger.info(f'''No port number was provided - searching for a free port starting at {start_port}''')

	if not port:
		#  No usable port yet - search for one starting at start_port
		for candidate in range(start_port, start_port + max_tries):
			if not port_in_use(this_ip_address, candidate):
				port = candidate
				break
		else:
			logger.critical(f'''No free port found between {start_port} and {start_port + max_tries - 1}''')
			force_quit(1)

	logger.info(f'''IP address {this_ip_address} with port {port} is available''')
	return this_ip_address, port


def force_quit(code):
	logger.critical(f'''Terminating the program with exit code {code}''')
	sys.exit(code)

def start(file_path):

	global logger

	# Create a logfile 
	logger = setup_logfile(file_path,LOGFILENAME,progName)
	# from logger_module import logger # Need to import after setup_logging is called
	logger.info(f'''{progName} -- {progVersion}''')

	if not get_DWC_config(file_path, logger):
		print(f"Failed to load configuration from {file_path}.")
		force_quit(1)

	# Can now get config parameters
	from duet_config import (LOGGING, UI, save_ui_address)

	# Set logging level
	logger = set_log_level(LOGGING.LEVEL,logger)

	from duet_printer import _loginPrinter, publish_ui_address

	if _loginPrinter():
		logger.info(f'Successful login to printer')
	else:
		logger.critical(f'Failed to login to printer - check printer is turned on')
		force_quit(1)

	# Allocate a port on this SBC

	save_ui_address(*validate_port(UI.PORT))
	publish_ui_address(UI.IP, UI.PORT)
 
	from app import appstartup
	appstartup()


if __name__ == '__main__':
	file_path = sys.argv[1]
	if not os.path.exists(file_path):
		print(f'File path {file_path} could not be found - Exiting')
		sys.exit(1)
	start(file_path)