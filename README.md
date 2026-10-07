# duetPrintGuard DWC Plugin

**Uses the detection engine developed by @oliverbravery**

duetPrintGuard offers local, **real-time print failure detection** for 3D printing on edge devices **(e.g. Rapberry Pi)** . It is self contained and does not require external connections or subscriptions.

It converts USB camera feeds to http streams which allows other applications access to the cameras.  For example - duetPrintGuard can simultaneously stream to (for example) duetLapse3. 

## Basic Operation
The plugin monitors one or more camera feeds looking for patterns that indicate a possible defect in printing.  During the monitoring, each feed reports either *success* or *failure* using a frame-by-frame analysis.

Each camera feed has separate settings to determine if there is sufficient evidence to report a *defect*.  If the number of continuous failure frames in a given number of frames exceeds the settings for that camera - a *defect* is declared. If one or all camera feeds (depending on settings) declare a defect then a countdown is started and notification(s) are send out.

At the end the countdown period, if the user does not intervene, the countdown action (Ignore, Pause, Cancel) is executed.  If the user does intervene then the users selected action is executed.



## Choosing a release

Each release is kept on its own branch. Use the one that matches your DWC / DSF version:

| DWC / DSF version | Release | Configuration |
| --- | --- | --- |
| 3.7.x | [3.7.x branch](../../tree/3.7.x) | Through a Configuration page in the plugin UI |
| 3.6.x | [3.6.x branch](../../tree/3.6.x) | Through a `duetPrintGuard.config` file accessible from DWC |

Both releases provide configurable actions when a defect is detected and several notification types (Duet Macro, ntfy, Pushover).

**The plugin zip file and the instructions for installation, configuration and operation (in the `docs` folder) are on the branch for your release.**


> _The origial project can be found here [here](https://github.com/oliverbravery/PrintGuard)._
