import asyncio
from logger_module import logger
import time

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

#from utils.camera_utils import get_camera_state, update_camera_state
from utils.config import CAMERA_STATES
#from utils.detection_utils import _live_detection_loop
from utils.stream_utils import _live_detection_loop

router = APIRouter()

@router.post("/detect/live/start")
async def start_live_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Start continuous live detection on a specified camera.

    Args:
        request (Request): The FastAPI request object containing app state.
        camera_uuid (str): UUID of the camera to start live detection on.

    Returns:
        dict: Message indicating whether live detection was started or already running.
    """
    global CAMERA_STATES
    #camera_state = await get_camera_state(camera_uuid)
    if CAMERA_STATES[camera_uuid]["live_detection_running"] == True:
        return {"success": True, "message": f"Live detection already running for camera {camera_uuid}"}
    else:
        CAMERA_STATES[camera_uuid] = {}
        '''
            "last_result": '----',
            "last_time": 0,
            "live_detection_running": '----',
            "live_detection_task": None
        }
        '''
    # await update_camera_state(camera_uuid, {
    try:
        print(f'attempting to create live detection loop for {camera_uuid}')
        print(f'with app.state {request.app.state}')
        task_id = asyncio.create_task(_live_detection_loop(request.app.state, camera_uuid))
        print(f'{task_id=}')
        CAMERA_STATES[camera_uuid] = {        
        "live_detection_running": True,
        "last_result": None,
        "last_time": time.time(),
        "live_detection_task": asyncio.create_task(_live_detection_loop(request.app.state, camera_uuid))
        }
    except Exception as e:
        logger.error("Error starting live detection for camera %s: %s", camera_uuid, e)
        return {"success": False, "message": f"Failed to start live detection for camera {camera_uuid}"}

    '''
    CAMERA_STATES[camera_uuid] = {        
        "start_time": time.time(),
        "live_detection_running": True,
        "live_detection_task": asyncio.create_task(
        _live_detection_loop(request.app.state, camera_uuid)
        )}
    '''
    return {"success": True, "message": f"Live detection started for camera {camera_uuid}"}

@router.post("/detect/live/stop")
async def stop_live_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
    """Stop continuous live detection on a specified camera.

    Args:
        request (Request): The FastAPI request object containing app state.
        camera_uuid (str): UUID of the camera to stop live detection on.

    Returns:
        dict: Message indicating whether live detection was stopped or not running.
    """
    global CAMERA_STATES
    #camera_state = await get_camera_state(camera_uuid)
    camera_state = CAMERA_STATES[camera_uuid]
    if not camera_state.live_detection_running:
        return {"message": f"Live detection not running for camera {camera_uuid}"}
    live_detection_task = camera_state.live_detection_task
    if live_detection_task:
        try:
            await asyncio.wait_for(live_detection_task, timeout=0.25)
            logger.debug("Live detection task for camera %s finished successfully.", camera_uuid)
        except asyncio.TimeoutError:
            logger.debug("Live detection task for camera %s did not finish in time.", camera_uuid)
            if live_detection_task:
                live_detection_task.cancel()
        except Exception as e:
            logger.error("Error stopping live detection task for camera %s: %s", camera_uuid, e)
        finally:
            live_detection_task = None
    #await update_camera_state(camera_uuid, {
    CAMERA_STATES[camera_uuid] = {    
        "start_time": None,
        "live_detection_running": False,
        "live_detection_task": None}
    
    return {"message": f"Live detection stopped for camera {camera_uuid}"}
