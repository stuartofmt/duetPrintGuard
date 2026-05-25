import asyncio
import time


from fastapi import APIRouter, Body, Request


from logger_module import logger


from utils.stream_utils import start_live_detection, stop_live_detection, save_request

router = APIRouter()


# detection_routes.py
@router.post("/detect/live/start")
async def starting_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
	"""Start continuous live detection on a specified camera."""
	try:
		save_request(request)
		await start_live_detection(camera_uuid)
	except Exception as e:
		logger.error("Error starting live detection for camera %s: %s", camera_uuid, e)
		return {"success": False, "message": f"Failed to start live detection for camera {camera_uuid}"}

	return {"success": True, "message": f"Live detection started for camera {camera_uuid}"}


@router.post("/detect/live/stop")
async def stopping_detection(request: Request, camera_uuid: str = Body(..., embed=True)):
	"""Stop continuous live detection on a specified camera."""
	try:
		await stop_live_detection(camera_uuid)
	except Exception as e:
			logger.error("Error stopping live detection task for camera %s: %s", camera_uuid, e)

	return {"message": f"Live detection stopped for camera {camera_uuid}"}
