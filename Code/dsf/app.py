
import asyncio
from logger_module import logger
import os
from contextlib import asynccontextmanager
import json



from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from duet_config import UI

from utils.config import init_config, PRINTER_POLL_SECONDS

# The autostart monitor - a task in uvicorn's event loop, so the detection it starts shares that loop
# (and the SSE connections) with the rest of the app
_autostart_task = None


class RevalidatedStaticFiles(StaticFiles):
	"""Static files the browser must revalidate (a quick 304 if unchanged) before using a cached copy.

	Without Cache-Control the browser may keep using old JavaScript after the plugin is updated.
	"""
	async def get_response(self, path, scope):
		response = await super().get_response(path, scope)
		response.headers['Cache-Control'] = 'no-cache'
		return response



def init_routes_and_modules():
	"""
	Import modules that may have dependency on config.py paths or values
	Initialize the API routes for the FastAPI application.
	Separating this from appstartup to allow for config file imports in route definitions.
	"""

	from utils.detector import Detector

	from routes.routes import router as app_router


	@asynccontextmanager
	async def lifespan(app_instance: FastAPI):
		"""
		Lifespan event handler for FastAPI application.
		
		Loads the detection model at startup and releases camera streams on shutdown.
		"""

		try:
			app_instance.state.detector = Detector()
		except Exception as e: # Missing or unreadable model / prototypes - the UI still runs, detection reports the problem
			logger.error("Could not load the detection model - detection will not work: %s", e)
			app_instance.state.detector = None

		yield
		logger.debug("Cleaning up resources on shutdown...")
		try:
			from utils.shared_video_stream import get_shared_stream_manager
			manager = get_shared_stream_manager()
			manager.cleanup_all()
			logger.debug("Cleaned up camera resources successfully.")
		except Exception as e:
			logger.error("Error during cleanup: %s", e)

	global app
	app = FastAPI(
		title="PrintGuard",
		description="Real-time Defect Detection on Edge-devices",
		version="1.0.0",
		lifespan=lifespan,
	)

	app.add_middleware(
		CORSMiddleware,
		allow_origins=["*"],
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)

	app.state.detector = None
	app.state.alerts = {}
	app.state.outbound_queue = asyncio.Queue()
	app.state.polling_tasks = {}

	base_dir = os.path.dirname(__file__)
	static_dir = os.path.join(base_dir, "static")
	templates_dir = os.path.join(base_dir, "templates")
	app.mount("/static", RevalidatedStaticFiles(directory=static_dir), name="static")
	global templates
	templates = Jinja2Templates(directory=templates_dir)

	app.include_router(app_router)


	@app.middleware("http")
	async def http_redirect_middleware(request: Request, call_next):
		"""
		Middleware to handle HTTP requests
		Defaults to index.html
		Currently just used for initial connection logging
		"""
		if request.url.scheme == "http":

			if request.url.path == '/':
				query = f'?{request.url.query}' if request.url.query else ''
				return RedirectResponse(url=f"/index{query}", status_code=308)

			if request.url.path.startswith("/index"):
				logger.debug(f'Index connection recieved {request.url}{request.url.query} from {request.client}')
				logger.debug (f'Query parameters: {request.query_params}')
			elif request.url.path.startswith("/settings"):
				logger.debug(f'Settings connection recieved {request.url} from {request.client}')

		response = await call_next(request)
		return response
	

def activate_autostart_detection(Enable):
	'''
	If one or more cameras have autostart enabled the start the background poll
	polling stops after the printer goes from processing to idle
	so this needs to be called to reset autostart.
	Must be called from the event loop (e.g. a route handler).
	'''
	global _autostart_task
	running = _autostart_task is not None and not _autostart_task.done()
	if not Enable: # Stop monitoring - detection that autostart has started keeps running
		if running:
			logger.debug('Autostart will be restarted')
			_autostart_task.cancel()
		return

	if running: #Already running
		return

	from utils.config import CAMERA_SETTINGS # Need to import CAMERA_SETTINGS here to ensure it is initialized before use

	autostartCameras = {k:v for k,v in CAMERA_SETTINGS.items() if v.get('autostart', False)}
	if not autostartCameras:
		logger.info('Autostart not required')
		return

	logger.info('Starting Autostart')
	_autostart_task = asyncio.get_running_loop().create_task(autostart_detection(autostartCameras, app.state))


async def autostart_detection(cameras, app_state):
	# Start detection when printer is processing
	# Stops detection when printer goes to idle after processing
	# Finishes after idle state (or when cancelled by activate_autostart_detection(False))

	from duet_printer import get_duet_printer_status
	from utils.stream_utils import start_live_detection, stop_live_detection,save_app_state_request

	autostart_pending = True

	await send_autostart_running(True)
	try:
		while True:
			logger.debug(f'Waiting for printer before autostarting detection loop for cameras: {list(cameras.keys())}')
			printer_status = await asyncio.to_thread(get_duet_printer_status)
			if printer_status == 'processing' and autostart_pending:
				try:
					logger.info(f'Autostarting detection loop for cameras: {list(cameras.keys())}')
					for camera_uuid in cameras.keys():
						save_app_state_request(app_state)
						await start_live_detection(camera_uuid)
					autostart_pending = False
				except Exception as e:
					logger.error(f'Error auto starting detection loop for cameras: {list(cameras.keys())}: {e}')
			elif printer_status == 'idle' and not autostart_pending:
				try:
					logger.debug(f'Autostopping detection loop for cameras: {list(cameras.keys())} as printer is not processing')
					for camera_uuid in cameras.keys():
						await stop_live_detection(camera_uuid)
				except Exception as e:
					logger.error(f'Error auto stopping detection loop for cameras: {list(cameras.keys())}: {e}')
				break

			await asyncio.sleep(PRINTER_POLL_SECONDS)  # No need to poll to quickly
	finally:
		await send_autostart_running(False)
		logger.info('Autostart Stopped')

async def send_autostart_running(state):
	"""Send a direct autostart state SSE event to the browser.

	This bypasses the ALERT model and the alert queueing path.
	Only the camera state payload is sent to the SSE client.
	"""
	try:
		from routes.routes import managerSSE
		payload = {
			"event": "autostart_running",
			"data": json.dumps({
				"state": state
			})
		}
		await managerSSE.broadcast(payload)
		logger.debug(f"Broadcast autostart_running to {state}")
	except Exception as e:
		logger.error("Failed to broadcast autostart_running SSE event =  %s: %s", state, e)
	
		
def appstartup():
	'''
	Run the FastAPI application with uvicorn
	'''
	# pylint: disable=C0415
	import uvicorn


	# Allow config to first set paths for config file
	init_config()

	init_routes_and_modules()
	
	logger.info(f'duetPrintGuard can be accessed using one of the following:')
	logger.info(f'Control')
	logger.info(f'http://localhost:{UI.PORT}')
	logger.info(f'http://{UI.IP}:{UI.PORT}')
	logger.info(f"Settings")
	logger.info(f'http://localhost:{UI.PORT}/settings')
	logger.info(f'http://{UI.IP}:{UI.PORT}/settings')
	logger.info(f"Configuration")
	logger.info(f'http://localhost:{UI.PORT}/config')
	logger.info(f'http://{UI.IP}:{UI.PORT}/config')

	port = str(UI.PORT)  #unicorn looks for strings	

	logger.debug('Starting uvicorn')
	uvicorn.run(app,
				host=UI.HOST,
				port=port,
				log_config=None,
				# SSE and stream connections never finish on their own - without this, shutdown
				# waits for them forever and DSF has to kill the plugin
				timeout_graceful_shutdown=2
				)
		# At this point we swtch to uvicorn world and never return until done
