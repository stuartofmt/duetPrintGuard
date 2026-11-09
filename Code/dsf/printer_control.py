"""
What duetPrintGuard does with the printer: keeps the connection and status up to date, pauses / resumes /
cancels the print, and sends the defect notifications.

There are three ways to reach the printer, found out when connecting:
  plugin            the printer's SBC is this computer - DSF's socket, with dsf-python (dsf_printer.py)
  remoteSBC         an SBC on another computer - the /machine http api and WebSocket (duet_printer.py)
  remoteStandalone  a standalone board - the rr_ http api, polled (duet_printer.py, as used by duetLapse3)
"""

import os
import socket
import threading
import time
import urllib.parse

import requests

import dsf_printer
import duet_printer
import state  # Shared state - always use state.<name>
from duet_printer import forgetPrinter, getDuet, getDuetVersion, getStatus, loginPrinter, printerAddress, sendDuetGcode
from logger_module import logger
from messages import Message, coded
from duet_config import ACTION, DUET, MACRO, NTFY, PUSHOVER, UI
from alert_text import alert_text

global MACRO_TIMES, NTFY_TIMES, PUSHOVER_TIMES
MACRO_TIMES = 0
NTFY_TIMES = 0
PUSHOVER_TIMES = 0

POLL_SECONDS = 5  # Between status checks - a standalone board drops a session after 8 seconds with no requests
RECONNECT_SECONDS = 10  # Between attempts to connect
STATUS_WAIT_SECONDS = 60  # How long to wait for the printer to reach a state after a pause / resume (e.g. finishing the current move)
DSF_PLUGIN_DIR = '/opt/dsf/plugins/'
DSF = 'DSF'  # state.apiModel for the plugin mode - duet_printer uses 'SBC' and 'rr_model'
MODES = {DSF: 'plugin', 'SBC': 'remoteSBC', 'rr_model': 'remoteStandalone'}

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
    duet_printer.onChange = _wake.set  # remoteSBC - the WebSocket brought a change
    dsf_printer.onChange = _wake.set  # plugin - the status changed, or DSF was lost
    threading.Thread(name='printerMonitor', target=_monitor, daemon=True).start()


def printer_settings_changed():
    """The printer settings were changed on the Configuration page - connect again with the new ones."""
    global _passwordRefused, _settingsChanges
    _apply_printer_settings()
    state.apiModel = ''
    _passwordRefused = False
    _settingsChanges += 1
    forgetPrinter()
    dsf_printer.disconnect()
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


def _is_this_computer(host):
    """True if host is an address of this computer."""
    if host in ('', 'localhost'):
        return True
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    local = {'::1', UI.IP}
    try:
        local |= {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None)}
    except OSError:
        pass
    return any(address.startswith('127.') or address in local for address in addresses)


def _login():
    """Log in - through DSF if the printer is this computer (plugin), otherwise over the network. Returns (model, code)."""
    if _is_this_computer(state.duet):
        try:
            dsf_printer.connect()
            return DSF, 200
        except Exception as e:  # e.g. not an SBC, or no permission to use DSF's socket
            logger.info(f'Could not connect to DSF on this computer ({e}) - trying the network')
    return loginPrinter()


def _connect():
    global _passwordRefused
    changes = _settingsChanges
    model, code = _login()
    if changes != _settingsChanges:
        if model == DSF:
            dsf_printer.disconnect()
        return  # The answer is from the old printer - the monitor connects again with the new settings
    if model == '':
        if code == 403:
            _passwordRefused = True
            _set_status('disconnected', False, Message('printerPassword', f'The printer at {printerAddress()} did not accept the password', printer=printerAddress()))
        else:
            _set_status('disconnected', False, Message('printerNotResponding', f'The printer at {printerAddress()} is not responding', printer=printerAddress()))
        return
    state.apiModel = model
    version = dsf_printer.getVersion() if model == DSF else getDuetVersion(model)
    logger.info(f'Connected to printer at {printerAddress()} as {MODES[model]} - firmware {version}')
    _poll()


def _current_status():
    """The printer's status now, asked for (or from the subscription / WebSocket) - 'disconnected' if it does not answer."""
    if state.apiModel == DSF:
        return dsf_printer.getStatus()[0]
    if state.apiModel:
        return getStatus()[0]
    return 'disconnected'


def _poll():
    global _passwordRefused
    status = dsf_printer.getStatus()[0] if state.apiModel == DSF else getDuet(getStatus)[0]
    if status != 'disconnected':
        _set_status(status, True)
        return
    _set_status('disconnected', False, Message('printerNotResponding', f'The printer at {printerAddress()} is not responding', printer=printerAddress()))
    if state.apiModel == DSF:
        state.apiModel = ''  # Connect again from the start
        return
    model, code = loginPrinter(state.apiModel)  # A new session for when it answers again
    if code == 403:
        state.apiModel = ''
        _passwordRefused = True
        _set_status('disconnected', False, Message('printerPassword', f'The printer at {printerAddress()} did not accept the password', printer=printerAddress()))


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
            _set_status('disconnected', False, Message('printerCannotConnect', f'Could not connect to the printer at {printerAddress()}: {e}',
                                                       printer=printerAddress(), error=e))
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
            'mode': MODES.get(state.apiModel, ''),
            'plugin': bool(state.plugin),
            'error': _error,
            'errorCode': coded(_error),  # So the page can show it in its language
            'retrying': not _passwordRefused,  # False - no more tries until the printer settings change
            'ip': DUET.IP,  # The printer settings, for the page's connect form (not the password)
            'port': DUET.PORT,
    }


# ------------------------------------------------------------
# Send Gcode command
# ------------------------------------------------------------

def _send_duet_code(command):
    """Send a G/M-code to the printer."""
    if not state.apiModel:
        logger.error(f'Could not send {command} - the printer is not connected')
        return
    if state.apiModel == DSF:
        dsf_printer.sendGcode(command)
    else:
        sendDuetGcode(state.apiModel, command)
    logger.debug(f'Sent {command} to the printer')


def _wait_for_status(wanted, timeout=STATUS_WAIT_SECONDS):
    """Wait until the printer reports the wanted status. Returns False if it does not within timeout."""
    deadline = time.time() + timeout
    status = _status
    while time.time() < deadline:
        status = _current_status()
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
    status = _current_status()
    if status == 'disconnected':
        logger.error(f'Could not {action} - the printer is not connected')
        return
    if action == 'pause_print':
        if status == 'processing':
            _duet_pause()
            _send_duet_code(f'M291 S1 T0 P"{alert_text("printerPaused", "Paused Printing")}"')
            _wait_for_status('paused')

    elif action == 'resume_print':
        if status == 'paused':
            _duet_resume()
            _send_duet_code(f'M291 S1 T0 P"{alert_text("printerResumed", "Resumed Printing")}"')
            _wait_for_status('processing')

    elif action == 'cancel_print':
        if status == 'processing':  # A print must be paused before it can be cancelled
            _duet_pause()
            if _wait_for_status('paused'):
                status = 'paused'
        if status == 'paused':
            _duet_cancel()
            _send_duet_code(f'M291 S1 T0 P"{alert_text("printerCancelled", "Cancelled Printing")}"')
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
        if NTFY.TOPIC != '':  # OK to send
            if NTFY_TIMES < NTFY.MAXTIMES:
                title = ''
                message = ''
                if NTFY.TITLE != '':
                    title = NTFY.TITLE
                else:
                    title = alert['title']

                if NTFY.MESSAGE != '':
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
        if PUSHOVER.API != '' and PUSHOVER.USER != '':  # OK to send
            if PUSHOVER_TIMES < PUSHOVER.MAXTIMES:
                title = ''
                message = ''
                if PUSHOVER.TITLE != '':
                    title = PUSHOVER.TITLE
                else:
                    title = alert['title']
                if PUSHOVER.MESSAGE != '':
                    message = PUSHOVER.MESSAGE
                else:
                    message = alert['body']

                logger.info(f'Sending PUSHOVER with title {title}')

                data = {
                        "token": PUSHOVER.API,
                        "user": PUSHOVER.USER,
                        "title": title,
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
