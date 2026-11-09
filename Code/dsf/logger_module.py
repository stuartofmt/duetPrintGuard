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


def setup_console_logger(progName="duetPrintGuard"):
    """The logger with only console output - usable before the settings folder is known. Called again, it returns the same logger."""
    global logger
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logger.propagate = False

        # set initial logging level
        logger.setLevel(logging.INFO)

        # Create handler for console output - file output handler is created by create_log_file
        c_handler = logging.StreamHandler(sys.stdout)
        format = f'{progName} "%(asctime)s [%(levelname)s] %(message)s"'
        c_format = logging.Formatter(format)
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)
    return logger


def setup_logfile(path, name, progName="duetPrintGuard"):
    global logger, file_path, logfilename
    file_path = path
    logfilename = name

    # Create logger
    logger = setup_console_logger(progName)
    create_log_file(logger)
    return logger


def create_log_file(console_logger):
    global logger, file_path, logfilename

    logfile = os.path.join(file_path, logfilename)
    if os.path.exists(logfile):
        console_logger.info(f'Removing old logfile {logfile}')  # Console only - the log file is not open yet
        os.remove(logfile)

    # Create handler for logfile
    f_handler = logging.FileHandler(logfile, mode='w', encoding='utf-8')
    f_format = logging.Formatter("%(asctime)s %(module)s - %(funcName)s:[%(levelname)s] %(message)s", "%m-%d %H:%M:%S")
    f_handler.setFormatter(f_format)
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
