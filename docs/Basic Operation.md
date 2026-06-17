# duetPrintGuard - Basic Operation


The main page is accessible via `http://localhost:<PORT>` or `http://<IP>:<PORT>`  This is the page displayed in DWC

IP and PORT are set in the [DUET] section of the configuration file.

Broadly, there are three main states
-- Not Detecting
-- Detecting - No Defect
-- Detecting - Defect

### Not Detecting

This image shows the main UI of duetPrintGuard comprisiong three sections.
-- top control section
-- middle camera section
-- bottom cootrol section

The top control section provided printer control and displays countdown information

In the middle section: configured camera is shown separately with the following details:
 -- The Camera nickname
 -- Current detection status [Inactive]
 -- Current print state [Blank]
 -- The time of the last update [Blank]
 -- A thumbnail image of the cameras view
 -- A button to toggle Detecting on and off [Start Detection]

 Note that the clicking on a camera thumbnail will open a live view in a separate tab.

 <img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin1.png" style="width:50%; height:auto;">

 ### Detecting - No Defect

 Once a camera is detecting the display is updated regularly with

 -- Current detection status [Detecting]
 -- Current print state [success, failure]
 -- The time of the last update [time]
 -- A button to toggle Detecting on and off [Stop Detection]

 <img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin2.png" style="width:50%; height:auto;">
 
### Detecting - Defect

 If a failure occurs several things happen:
On the top control section:
A countdown timner starts and the `Countdown Action` button flashes

The camera is updated
 -- Current detection status [Detecting]
 -- Current print state [DEFECT]
 -- The time of the last update [time]
 -- A button to toggle Detecting on and off [Stop Detection]

 If the user does nothing within the configured `Countdown time` -- the `Countdown Action` will be sent to the printer as follows:

Ignore - does nothing
Pause - pauses the priter and changes the action to resume
Cancel - cancels the print job
 

<img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin4.png" style="width:50%; height:auto;">

### Bottom Control section
 The bottom control section allows the UI to be switched to the settings page.  If any cameras are set to allow autostart, the autostart button will be displayed.

 If auto start is enabled, detection will commence once a print job has started and will stop when the print job is complete.  This allows duetPrintGuard to run in the background but note: Once a print job has completed, autostart needs to be reenabled.  This was an implementationdecision to avoid constant use of cpu between print jobs.

 <img src="https://github.com/stuartofmt/duetPrintGuard/blob/main/docs/media/images/Plugin5.png" style="width:50%; height:auto;">
