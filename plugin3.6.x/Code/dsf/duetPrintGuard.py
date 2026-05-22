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

# This is more-or-less a wrapper for the detection app PrintGuard.
# https://github.com/oliverbravery/PrintGuard
# This plugin modifies with UI changes and much code simplification
# to make it more suited to the DWC environment

"""
Version 1.0 - Initial release
"""

import sys
import os
import socket

sys.path.append(os.path.dirname(__file__))

from logger_module import (setup_logfile, set_log_level)
from duet_config import get_DWC_config

global progName, progVersion
progName = 'duetPrintGuard'
progVersion = '0.0.2'
# Min python version
pythonMajor = 3
pythonMinor = 8

CONFIGFILENAME = 'duetPrintGuard.config'
LOGFILENAME = 'duetPrintGuard.log'

def checkIP(ip_address, port):
    #  Check to see if the requested IP and Port are available for use
    this_ip_address = ''
    if port != 0:
        #  Get the local ip address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))  # doesn't even have to be reachable
            this_ip_address = s.getsockname()[0]
        except Exception as e:
            logger.warning(f'''Make sure IP address {ip_address} is reachable and unique''')
            logger.warning(f'''{e}''')
        finally:
            s.close()
            if ip_address != this_ip_address:
                logger.critical(f'''The ip address in the configuration file {ip_address}\ndoes not match the ip address of this machine {this_ip_address}''')
                force_quit(1)

        # Check that the port is available
        try:
            sock = socket.socket()
        except Exception as e:
            logger.critical(f'''Unknown error trying to open a socket''')
            logger.critical(f'''{e}''')
            force_quit(1)  
        finally:
            if sock.connect_ex((ip_address, port)) == 0:
                logger.critical(f'''Port {port} is already in use.''')
                force_quit(1)
    else:
        logger.critical('No port number was provided - terminating the program')
        force_quit(1)
    
    logger.info(f'''IP address {ip_address} with port {port} is available''')
    return ip_address

def force_quit(code):
    logger.critical(f'''Terminating the program with exit code {code}''')
    sys.exit(code)

def start(file_path):

    global logger

    # Create a logfile 
    logger = setup_logfile(file_path,LOGFILENAME,progName)
    # from logger_module import logger # Need to import after setup_logging is called
    logger.info(f'''{progName} -- {progVersion}''')

    if not get_DWC_config(file_path, CONFIGFILENAME,logger):
        print(f"Failed to load configuration from {file_path}. Please ensure the file exists and is properly formatted.")
        force_quit(1)

    # Can now get config parameters
    from duet_config import (DUET, LOGGING, UI)

    # Set logging level
    logger = set_log_level(LOGGING.LEVEL,logger)


    # Exit if valid Port is provided for UI
    # On this SBC
    checkIP(DUET.IP, UI.PORT)
 
    from app import appstartup
    appstartup()


if __name__ == '__main__':
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f'File path {file_path} could not be found - Exiting')
        sys.exit(1)
    start(file_path)