"""
Shared globals across modules
Used for duet3d version
useage:
from (.)duet import duet
 then reference variables with dot notation
 duet.<variable name>

"""
### ---------- ONLY CHANGE ENTRIES BETWEEN { and } -----------###
"""
duet = {
<values go in here>
}
"""

duet = {
"CONFIG_VERSION" : "1.0.0", #Do not change this
"DWC" : True, # Don't change this
"HOST" : "0.0.0.0", # Usually unchanged
"PORT" : 8001, # Cannot conflict with other apps / plugins
"countdown_time": 60.0,
"countdown_action": "dismiss",
"majority_vote_threshold": 2,
"majority_vote_window": 5,
"printer_id": None,
"printer_config": None # last entry - no comma !
}

### ------------ DO NOT CHANGE BELOW HERE ------  ###

### ---------DO NOT CHANGE -------------------###
class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

duet = dotdict(duet)





