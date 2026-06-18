# duetPrintGuard DWC Plugin

**Uses the detection engine developed by @oliverbravery**

duetPrintGuard offers local, **real-time print failure detection** for 3D printing on edge devices **(e.g. Rapberry Pi)** . It is self contained and does not require external connections or subscriptions.

It converts USB camera feeds to http streams which allows other applications access to the cameras.  For example - duetPrintGuard can simultaneously stream to (for example) duetLapse3. 

## Basic Operation
The plugin monitors one or more camera feeds looking for patterns that indicate a possible defect in printing.  During the monitoring, each feed reports either *success* or *failure* using a frame-by-frame analysis.

Each camera feed has separate settings to determine if there is sufficient evidence to report a *defect*.  If the number of continuous failure frames in a given number of frames exceeds the settings for that camera - a *defect* is declared. If one or all camera feeds (depending on settings) declare a defect then a countdown is started and notification(s) are send out.

At the end the countdown period, if the user does not intervene, the countdown action (Ignore, Pause, Cancel) is executed.  If the user does intervene then the users selected action is executed.



Primary configuration is through a file accesable from DWC that facilitates:
-- IP and port setting
-- Configurable actions when a defect is detected
-- several notofcation types ( Duet Macro, NTFY, Pusher)


**Instructions for installation and configuration are here:**
https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/Getting-Started.md

**Instructions for operation are here:**
https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/Basic-Operation.md


> _The origial project can be found here [here](https://github.com/oliverbravery/PrintGuard)._
