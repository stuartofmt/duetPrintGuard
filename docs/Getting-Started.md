# duetPrintGuard - Getting Started


## Table of Contents
- [Installation](#installation)
- [Configuration](#configuration)
- [Logging](#logging)
- [Camera Setup](#camera-setup)
- [Monitoring](#monitoring)


## Installation
duetPrintGuard is packaged as a DWC plugin and installed in the normal manner from the zip file.

## Configuration

During installation of the plugin, a template configuration file `duetPrintGuard.config.example` is placed in the `system/duetPrintGuard directory`.

The example should be copied or renamed to `duetPrintGuard.config` and configured to your system / needs.  The two main settings are:

In the [DUET] section:
-- IP ==> the IP address of the printer

In the [UI] section:
-- PORT ==> the port number for UI elements to access the settings and monitoring pages

[duetPrintGuard.config.example](../plugin3.6.x/Code/sd/sys/duetPrintGuard/duetPrintGuard.config.example)

## Logging

When the plugin is run, a log file `duetPrintGuard.log`  is placed in the `system/duetPrintGuard directory`.

## On initial startup
When the plugin is first accessed - the Detection page will display with a message stating that there are no cameras defined.  Press the "Settings" button to configure one or more cameras.


## Camera Setup

The camera settings page is accessible from the Detection page or via `http://localhost:<PORT>/settings` or `http://<IP>:<PORT>/settings`

Where IP is set in the [DUET] section of the configuration file and PORT is set in the [UI] section

This page allows you to configure the action to be taken on failure, camera settings and detection settings.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Setting1.png" style="width:50%; height:auto;">
  
### Adding Cameras

Multiple cameras can be configure, either serial (USB) or newtwork based.

EAch camera must have unique nickname and unique source.

This image shows the serial configuration UI.  The `Serial Device` box provides a dropdown of POSSIBLE serial cameras on your system. Most will not have a camera attached - so some trial and error is needed to find those that work.  The `Show Camera Preview` checkbox can be helful in this.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Setting2.png" style="width:50%; height:auto;">

This image shows the network camera UI.  Both HTTP and RTSP are supported.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Setting3.png" style="width:50%; height:auto;">


### Countdown Action

`Countdown Action` allows the selection of one of three actions that will occur when a Defect is detected.  These are Ignore, Pause and Cancel. If here is no manual override within the time set in `Countdown Time` then the selected action will be sent to the printer.

### Countdown Time

Specifies the maximum time from the occurrence of a failure (see detection setting below) before which the user can override the `Countdown Action` (using the UI --see Failure section below)

### Detection Setings

A failure is raised when the camera detects a series of anomolies that satisfy this rule:

More than "n" `Majority Vote Threshhold` anomolies during a window of "y" consecutive frames `Majority Vote Window`.

Optimal values for these settings depend on many factors such as the rate at which frames are recieved, the type and position of the camera, lighting conditions etc.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Setting4.png" style="width:50%; height:auto;">

## Monitoring

The monitoring page is accessible via `http://localhost:<PORT>/duetindex` or `http://<IP>:<PORT>/duetindex`  This is the page displayed in DWC

Where IP and PORT are set in the [DUET] section of the configuration file.

### No Failure

This image shows the main UI of duetPrintGuard on restart of the plugin.  Each configured camera is shown separately. Details for each camera are:
 -- The Camera nickname
 -- Current detection status [Detecting, Inactive]
 -- Current print state [Success, Failure] (If Detecting)
 -- The time detection was last Active
 -- The action associated with the camera if a failure exceeds the failure threshold
 -- A thumbnail image of the cameras view
 -- A button to toggle Detecting on and off

 <img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin1.png" style="width:50%; height:auto;">

 Once a camera is Detecting the `Last Active` field is updated regularly

 <img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin2.png" style="width:50%; height:auto;">
 
### Failure

 If a failure occurs - a popup will appear which allows the user to manually override the configured `Countdown Action`.  If the user does nothing within the configured `Countdown time` -- the `Countdown Action` will be sent to the printer (Dismiss does nothing).

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin3.png" style="width:50%; height:auto;">

If more then one camera detects a failure them multiple failure popups will be generated.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin4.png" style="width:50%; height:auto;">

  