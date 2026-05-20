import configparser
import os
import sys

global DUET, UI, LOGGING, ACTION, MACRO, NTFY, PUSHOVER

# From https://gist.github.com/laywill/63d75b53e8a7a801d77f0dd2b97de54d
class DictToClass:
    def __init__(self, dictionary):
        for key, value in dictionary.items():
            if isinstance(value, dict):
                value = DictToClass(value)
            setattr(self, key, value)

def get_DWC_config(file_path,file_name,logger):
    global DUET, UI, LOGGING, ACTION, MACRO, NTFY, PUSHOVER
    config_file = os.path.join(file_path, file_name)
    logger.debug(f"Looking for config file at {config_file}")

    if os.path.exists(config_file):
        config = configparser.ConfigParser()
        config.read(config_file)

        # Convert to dict
        # Source - https://stackoverflow.com/a/28990982
        config_dict = {s:dict(config.items(s)) for s in config.sections()}

        # Get the various sections
        duet_section = config_dict["DUET"]
        ui_section = config_dict["UI"]
        logging_section = config_dict["LOGGING"]
        action_section = config_dict["ACTION"]
        macro_section = config_dict["MACRO"]
        ntfy_section = config_dict["NTFY"]
        pushover_section = config_dict["PUSHOVER"]

        #Change the keys to UPPER
        config_dict_duet = {k.upper():v for k,v in duet_section.items()}
        config_dict_ui = {k.upper():v for k,v in ui_section.items()}
        config_dict_logging = {k.upper():v for k,v in logging_section.items()}
        config_dict_action = {k.upper():v for k,v in action_section.items()}
        config_dict_macro = {k.upper():v for k,v in macro_section.items()}
        config_dict_ntfy = {k.upper():v for k,v in ntfy_section.items()}
        config_dict_pushover = {k.upper():v for k,v in pushover_section.items()}

        #Convert to dot dict
        DUET = DictToClass(config_dict_duet)
        UI = DictToClass(config_dict_ui)
        LOGGING = DictToClass(config_dict_logging)
        ACTION = DictToClass(config_dict_action)
        MACRO = DictToClass(config_dict_macro)
        NTFY = DictToClass(config_dict_ntfy)
        PUSHOVER = DictToClass(config_dict_pushover)

        # Adjust types and values
        # DUET
        if not hasattr(DUET,'IP') :
            logger.critical('DUET section required IP')
            sys.exit(1)
        if not hasattr(DUET,'PORT') : DUET.PORT = 80
        if not hasattr(DUET,'PASSWORD') : DUET.PASSWORD = 'reprap'
        if not hasattr(DUET,'POWERCHECK') : DUET.POWERCHECK = True
        if DUET.POWERCHECK.lower() in ['true', '1', 't', 'y', 'yes']:
            DUET.POWERCHECK = True
        else:
            DUET.POWERCHECK = False
        DUET.DWC = True
        DUET.FILE_PATH = file_path

        # UI
        if not hasattr(UI,'PORT'):
            logger.critical('UI section must have a PORT specified')
            sys.exit(1)

        UI.HOST = '0.0.0.0'
        UI.PORT = int(UI.PORT)

        # LOGGING
        if not hasattr(LOGGING,'LEVEL') : LOGGING.LEVEL = 'INFO'        

        # ACTION
        if not hasattr(ACTION,'PAUSE') : ACTION.PAUSE = ''
        if not hasattr(ACTION,'CANCEL') : ACTION.CANCEL = ''

        # MACRO
        if not hasattr(MACRO,'MACRO'): MACRO.MACRO = ''

        # NTFY
        if not hasattr(NTFY,'TOPIC'): NTFY.TOPIC = ''
        if not hasattr(NTFY,'TITLE'): NTFY.TITLE = ''
        if not hasattr(NTFY,'MESSAGE'): NTFY.MESSAGE = ''
        if not hasattr(NTFY,'PRIORITY'): NTFY.PRIORITY = ''
        
        #PUSHOVER
        if not hasattr(PUSHOVER,'API') : PUSHOVER.API = ''
        if not hasattr(PUSHOVER,'USER') : PUSHOVER.USER = ''
        if not hasattr(PUSHOVER,'TITLE') : PUSHOVER.TITLE = ''
        if not hasattr(PUSHOVER,'MESSAGE') : PUSHOVER.MESSAGE = ''
        

        """  template for booleans 
        if DUET.DEBUG.lower() in ['true', '1', 't', 'y', 'yes']:
            DUET.DEBUG = True
        else:
            DUET.DEBUG = False
        """


        return True
    
    return False
