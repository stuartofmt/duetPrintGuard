# Release notes


## 1.0.0
- Completely refactored html pages to better suit Duet3d DWC
- Changed UI model to allow multiple instances of UI with parallel control
- Added autostart autostop of detection based on printer state
- Added extensive configuration through config file
- Failure detection simplified to all / any if multiple cameras
- Many performance improvements to basic operation to reduce CPU load 
- Camera feeds can be accessed for other applications e.g. used for timelapse etc
- Added direct printer control to facilitate remote use (e.g. using Tailscale)

## 0.0.3 (not release)
- There appears to be little benefit from checking too often
since printer activity does not hapen that quickly
    -- Max FPS set to 5 frames per second (done)
    -- Max detection interval set to 5 per second (done)
- Added version number to logs -- fetched from duet installation file
- Fixed out of sync detection settings when page displayed in multiple browser instances

## 0.0.2
Initial Beta



