"""
Logging module needs to be imported twice during startup
The first time imports the setup functions
After the setup functions have been called,
the logger can be imported

All other modules simply need to import the logger

"""
import logging
import sys
import os

global logger, file_path, logfilename


def current_func_name(n=0):
    return sys._getframe(n + 1).f_code.co_name


FILE_FORMAT = logging.Formatter("%(asctime)s %(module)s - %(funcName)s:[%(levelname)s] %(message)s", "%m-%d %H:%M:%S")
_startup_handler = None  # The <program name>.startup.log handler, until setup_logfile switches to the log file


def setup_console_logger(progName="duetPrintGuard"):
    """The logger used from the start of the program: the console, and <program name>.startup.log in the program
    folder - a new one at each start.  setup_logfile switches to the log file once its folder is known.
    Called again, it returns the same logger.
    """
    global logger, _startup_handler
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logger.propagate = False

        # set initial logging level
        logger.setLevel(logging.INFO)

        # Create handler for console output
        c_handler = logging.StreamHandler(sys.stdout)
        format = f'{progName} "%(asctime)s [%(levelname)s] %(message)s"'
        c_format = logging.Formatter(format)
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)

        startup_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'{progName}.startup.log')
        try:
            _startup_handler = logging.FileHandler(startup_log, mode='w', encoding='utf-8')
        except OSError as e:  # e.g. the program folder can not be written to - the console still works
            logger.warning(f'Could not create {startup_log} - startup messages go to the console only: {e}')
        else:
            _startup_handler.setFormatter(FILE_FORMAT)
            logger.addHandler(_startup_handler)
            logger.info(f'Startup logging started at {startup_log}')
    return logger


def setup_logfile(path, name, progName="duetPrintGuard"):
    """Switch from the startup log to the log file (path/name), starting it with what the startup log holds."""
    global logger, file_path, logfilename
    file_path = path
    logfilename = name

    # Create logger
    logger = setup_console_logger(progName)
    create_log_file(logger)
    return logger


def create_log_file(console_logger):
    global logger, file_path, logfilename, _startup_handler

    logfile = os.path.join(file_path, logfilename)
    if os.path.exists(logfile):
        console_logger.info(f'Removing old logfile {logfile}')
        os.remove(logfile)

    # The startup log is closed (it stays in the program folder until the next start) and copied to the log file
    startup_text = ''
    if _startup_handler is not None:
        console_logger.info(f'Switching logging to {logfile}')
        console_logger.removeHandler(_startup_handler)
        _startup_handler.close()
        try:
            with open(_startup_handler.baseFilename, encoding='utf-8') as f:
                startup_text = f.read()
        except OSError:
            pass
        _startup_handler = None
    with open(logfile, 'w', encoding='utf-8') as f:
        f.write(startup_text)

    # Create handler for logfile
    f_handler = logging.FileHandler(logfile, mode='a', encoding='utf-8')
    f_handler.setFormatter(FILE_FORMAT)
    console_logger.addHandler(f_handler)
    logger = console_logger

    logger.info(f'''Logging started at {logfile}''')

    return logger


def set_log_level(log_level, logger):
    logger.info(f'Log level changed to {log_level}')

    if log_level == 'DEBUG':
        logger.setLevel(logging.DEBUG)
    elif log_level == 'INFO':
        logger.setLevel(logging.INFO)
    else:  # warning
        logger.setLevel(logging.WARNING)

    return logger
