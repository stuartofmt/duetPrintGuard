# duetPrintGuard - Getting Started


## Table of Contents
- [Installation](#installation)
- [Configuration](#configuration)
- [Logging](#logging)
- [Camera Setup](#camera-setup)


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

When the plugin is run, a log file `duetPrintGuard.log`  is created in the `system/duetPrintGuard directory`.

## On initial startup
When the plugin is first accessed - the Detection page will display with a message stating that there are no cameras defined.  Press the "Settings" button to configure one or more cameras.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin0.png" style="width:50%; height:auto;">

## Camera Setup

The camera settings page is accessible from the Detection page or via `http://localhost:<PORT>/settings` or `http://<IP>:<PORT>/settings`

Where IP is set in the [DUET] section of the configuration file and PORT is set in the [UI] section

This page allows you to configure the action to be taken on failure, camera settings and detection settings.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Setting1.png" style="width:50%; height:auto;">
  
### Adding Cameras

Multiple cameras can be configure, either serial (USB) or newtwork based.

Each camera must have unique nickname and unique source.

This image shows the serial configuration UI.  The `Serial Device` box provides a dropdown of POSSIBLE serial cameras on your system. Most will not have a camera attached - so some trial and error is needed to find those that work.  The `Show Camera Preview` checkbox can be helful in this.

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/AddCamera1.png" style="width:50%; height:auto;">

This image shows the network camera UI.  Both HTTP and RTSP are supported.


<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/AddCamera2.png" style="width:50%; height:auto;">


## Camera Controls


<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Setting2.png" style="width:50%; height:auto;">

### Defect Settings

A DEFECT is raised when the camera detects a series of failure frames that satisfy this rule:

If: There are more than "x" failure frames during a window of "y" consecutive frames.
x == `Majority Vote Threshhold`
y == `Majority Vote Window`

Optimal values for these settings depend on many factors such as the type and position of the camera, lighting conditions, nature and shape of the failure etc.


### Camera Image Settings



## Defect Action

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Setting3.png" style="width:50%; height:auto;">

`Countdown Action` allows the selection of one of three actions that will occur when a Defect is detected.  These are Ignore, Pause and Cancel. If here is no manual override within the time set in `Countdown Time` then the selected action will be sent to the printer.


### Countdown Time

Specifies the maximum time from the occurrence of a failure (see detection setting below) before which the user can override the `Countdown Action` (using the UI --see Failure section below)

### Which Cameras

