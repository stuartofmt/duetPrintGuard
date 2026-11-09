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

import sys
import os
import socket
import threading
import time
import webbrowser

sys.path.append(os.path.dirname(__file__))

from logger_module import (setup_console_logger, setup_logfile, set_log_level)
from duet_config import get_DWC_config

import json


def _plugin_version():
    """The version from the plugin manifest - installed by DSF as plugins/<id>.json, or plugin.json in the source tree."""
    here = os.path.dirname(os.path.abspath(__file__))
    for manifest in (os.path.join(here, '..', '..', 'duetPrintGuard.json'), os.path.join(here, '..', 'plugin.json')):
        try:
            with open(manifest, encoding='utf-8') as f:
                return json.load(f)['version']
        except (OSError, ValueError, KeyError):
            continue
    return 'unknown'


global progName, progVersion
progName = 'duetPrintGuard'
progVersion = _plugin_version()
# Min python version
pythonMajor = 3
pythonMinor = 12  # numpy in requirements.txt needs this

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


_folder_notes = []  # What default_folder found out, logged once the log is set up


def _packaged_python():
    """True on Windows if this Python runs as a packaged app (e.g. from the Microsoft Store, started through
    ...\\WindowsApps\\python.exe).  Windows then quietly redirects files it writes under AppData to a private folder of
    the package, which Explorer and other programs do not see."""
    if os.name != 'nt':
        return False
    try:
        import ctypes
        length = ctypes.c_uint32(0)
        # 15700 (APPMODEL_ERROR_NO_PACKAGE) = not packaged; 122 (ERROR_INSUFFICIENT_BUFFER) = packaged
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != 15700
    except (AttributeError, OSError):
        return False


def _writable(folder):
    try:
        test = os.path.join(folder, f'.{progName}-write-test')
        with open(test, 'w') as f:
            f.write('')
        os.remove(test)
        return True
    except OSError:
        return False


def default_folder():
    """The folder for the settings and log when none is given: this program's folder.  If it can not be written to
    (e.g. in Program Files) on Windows: the user's application data - or Documents\\duetPrintGuard with a packaged
    Python (Microsoft Store), which would hide files in application data.  The same as duetLapse3 and multiCam.
    No settings in the folder chosen = a new install: they are made from the defaults."""
    folder = os.path.dirname(os.path.abspath(__file__))
    if os.name != 'nt':
        return folder
    appdata = os.path.join(os.environ['APPDATA'], progName) if os.environ.get('APPDATA') else ''
    if not _writable(folder):
        if _packaged_python() or not appdata:
            folder = os.path.join(os.path.expanduser('~'), 'Documents', progName)
            _folder_notes.append('The program folder can not be written to, and this Python is a packaged app (e.g. from the '
                                 'Microsoft Store), which hides files in AppData from other programs - so ' + folder + ' is used')
        else:
            folder = appdata
            _folder_notes.append('The program folder can not be written to - so ' + folder + ' is used')
        os.makedirs(folder, exist_ok=True)
    return folder


BROWSER_WAIT_SECONDS = 30  # For the web server to start


def can_open_browser():
    """True if there is a desktop to open a browser on.  Without one (e.g. over ssh), Linux would use a text browser in the terminal."""
    if os.name == 'nt' or sys.platform == 'darwin':
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def open_browser_when_ready(port):
    """Open the pages in this computer's default browser, once the web server answers."""
    url = f'http://localhost:{port}'
    if not can_open_browser():
        logger.info(f'No desktop to open a browser on - open {url} (or this computer\'s address) in a browser')
        return

    def wait_and_open():
        deadline = time.time() + BROWSER_WAIT_SECONDS
        while not port_in_use('127.0.0.1', port):
            if time.time() > deadline:
                logger.warning(f'The web server did not start within {BROWSER_WAIT_SECONDS} seconds - not opening a browser')
                return
            time.sleep(0.5)
        try:
            opened = webbrowser.open(url)
        except Exception as e:  # e.g. no browser installed
            logger.debug(f'Could not open a browser: {e}')
            opened = False
        logger.info(f'Opened {url} in the default browser' if opened else f'Could not open a browser - open {url} in a browser')

    threading.Thread(name='openBrowser', target=wait_and_open, daemon=True).start()


def force_quit(code):
    logger.critical(f'''Terminating the program with exit code {code}''')
    sys.exit(code)


def start(file_path):

    global logger

    # Create a logfile
    logger = setup_logfile(file_path, LOGFILENAME, progName)
    # from logger_module import logger # Need to import after setup_logging is called
    logger.info(f'''{progName} -- {progVersion}''')
    logger.info(f'Settings and log folder: {file_path}')
    for note in _folder_notes:
        logger.info(note)

    if not get_DWC_config(file_path, logger):
        logger.info(f"Failed to load configuration from {file_path}.")
        force_quit(1)

    # Can now get config parameters
    from duet_config import (LOGGING, UI, save_ui_address)

    # Set logging level
    logger = set_log_level(LOGGING.LEVEL, logger)

    from dsf_printer import publishUiAddress
    from printer_control import running_as_plugin, start_printer_monitor

    # Allocate a port on this computer

    save_ui_address(*validate_port(UI.PORT))
    if running_as_plugin():
        publishUiAddress(UI.IP, UI.PORT)  # First, so the DWC page opens even if the printer can not be reached

    # Connects in the background, and keeps trying - the printer's address and password are set on the Configuration page
    start_printer_monitor()

    # Run by hand (remote SBC or standalone, or the SBC itself) - DWC shows the pages of the plugin
    if UI.OPENBROWSER and not running_as_plugin():
        open_browser_when_ready(UI.PORT)

    from app import appstartup
    appstartup()


if __name__ == '__main__':
    logger = setup_console_logger(progName)  # Console only until the settings folder is known - start() adds the log file
    if sys.version_info < (pythonMajor, pythonMinor):
        logger.info(f'{progName} needs Python {pythonMajor}.{pythonMinor} or later - this is {sys.version.split()[0]} - Exiting')
        sys.exit(1)
    # The folder for the settings and log: the plugin is given one
    file_path = sys.argv[1] if len(sys.argv) > 1 else default_folder()
    if not os.path.exists(file_path):
        logger.info(f'File path {file_path} could not be found - Exiting')
        sys.exit(1)
    start(file_path)
