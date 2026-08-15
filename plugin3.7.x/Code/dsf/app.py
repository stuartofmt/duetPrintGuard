
import asyncio
import threading
from logger_module import logger
import os
from contextlib import asynccontextmanager
import time
import json



from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from duet_config import (DUET, UI)

from utils.config import (get_prototypes_dir,
						   get_model_path, get_model_options_path,
						config_set_paths_and_initialize,DEVICE_TYPE, SUCCESS_LABEL, PRINTER_POLL_SECONDS)

global autostart_running
autostart_running = threading.Event()



def init_routes_and_modules():
	"""
	Import modules that may have dependency on config.py paths or values
	Initialize the API routes for the FastAPI application.
	Separating this from appstartup to allow for config file imports in route definitions.
	"""

	from utils.inference_lib import get_inference_engine

	from routes.routes import router as app_router


	@asynccontextmanager
	async def lifespan(app_instance: FastAPI):
		"""
		Lifespan event handler for FastAPI application.
		
		Initializes the device and model, sets up camera indices, and handles startup modes.
		"""

		inference_engine = get_inference_engine()

		logger.debug("Setting up device...")
		app_instance.state.device = inference_engine.setup_device(DEVICE_TYPE)
		logger.debug("Using device: %s", app_instance.state.device)
		try:
			logger.debug("Loading model...")
			app_instance.state.model, _ = inference_engine.load_model(get_model_path(),
													get_model_options_path(),
													app_instance.state.device)
			app_instance.state.transform = inference_engine.get_transform()
			logger.debug("Model loaded successfully.")
			logger.debug("Building prototypes...")
			try:
				prototypes, class_names, defect_idx = inference_engine.compute_prototypes(
					app_instance.state.model, get_prototypes_dir(), app_instance.state.transform,
					app_instance.state.device, SUCCESS_LABEL
				) # Last param optional use_cache defaults to True - tries to read model prototype from cache else download
				app_instance.state.prototypes = prototypes
				app_instance.state.class_names = class_names
				app_instance.state.defect_idx = defect_idx
				logger.debug("Prototypes built successfully.")
			except NameError:
				logger.warning("Skipping prototype building.")
			except ValueError as e:
				logger.error("Error building prototypes: %s", e)
		except RuntimeError as e:
			logger.error("Error during startup: %s", e)
			app_instance.state.model = None
			raise
		logger.debug("Camera indices set up successfully.")

		# Run autostart_detection in a background daemon thread
		# activate_autostart_detection()

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

	app.state.model = None
	app.state.transform = None
	app.state.device = None
	app.state.prototypes = None
	app.state.class_names = ['success', 'failure']
	app.state.defect_idx = -1
	app.state.alerts = {}
	app.state.outbound_queue = asyncio.Queue()
	app.state.polling_tasks = {}

	base_dir = os.path.dirname(__file__)
	static_dir = os.path.join(base_dir, "static")
	templates_dir = os.path.join(base_dir, "templates")
	app.mount("/static", StaticFiles(directory=static_dir), name="static")
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
	so this needs to be called to reset autostart 
	'''
	global autostart_running
	if not Enable: # Stop the thread if its running
		if autostart_running.is_set(): # stop the thread
			logger.debug('Autostart will be restarted')
			autostart_running.clear() # This will allow the thread to stop
		return
	
	if Enable:
		if autostart_running.is_set(): #Already running
			return
	# Need to start the thread
	from utils.config import CAMERA_SETTINGS # Need to import CAMERA_SETTINGS here to ensure it is initialized before use

	autostartCameras = {k:v for k,v in CAMERA_SETTINGS.items() if v.get('autostart', False)}
	if not autostartCameras:
		logger.info('Autostart not required')
		return
	
	def _run_autostart(cameras, app_state):
		try:
			asyncio.run(autostart_detection(cameras, app_state))
		except Exception as e:
			logger.error("Autostart detection background task failed: %s", e)
	logger.info('Starting Autostart')

	autostart_running.set() # Mark the thread as started
	threading.Thread(target=_run_autostart, args=(autostartCameras, app.state,), daemon=True).start()
	

async def autostart_detection(cameras, app_state):
	# Start detection when printer is processing
	# Stops detection when printer goes to idle after processing
	# Thread exits after idle state


	from duet_printer import get_duet_printer_status
	from utils.stream_utils import start_live_detection, stop_live_detection,save_app_state_request

	global autostart_running

	autostart_pending = True
	monitoring = True
	
	await send_autostart_running(True)
	while monitoring:
		logger.debug(f'Waiting for printer before autostarting detection loop for cameras: {list(cameras.keys())}')
		printer_status = get_duet_printer_status()
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
			finally:
				monitoring = False

		await asyncio.sleep(PRINTER_POLL_SECONDS)  # No need to poll to quickly
		if not autostart_running.is_set():
			break
	await send_autostart_running(False)
	autostart_running.clear() #Mark thread as finished
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
	config_set_paths_and_initialize()

	init_routes_and_modules()
	
	logger.info(f'duetPrintGuard can be accessed using one of the following:')
	logger.info(f'Control')
	logger.info(f'http://localhost:{UI.PORT}')
	logger.info(f'http://{DUET.IP}:{UI.PORT}')
	logger.info(f"Settings")
	logger.info(f'http://localhost:{UI.PORT}/settings')
	logger.info(f'http://{DUET.IP}:{UI.PORT}/settings')

	port = str(UI.PORT)  #unicorn looks for strings	

	logger.debug('Starting uvicorn')
	uvicorn.run(app,
				host=UI.HOST,
				port=port,
				log_config=None
				)
		# At this point we swtch to uvicorn world and never return until done
