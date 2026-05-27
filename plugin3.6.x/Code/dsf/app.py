"""SRS
Refactored app.py to move all initialization into the appstartup function,
including config setup
Some imports and other sertup placed in explicit function to allow config to have been set first
This allows for better control of the application startup process
"""


import asyncio
from logger_module import logger
import os
from contextlib import asynccontextmanager



from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from duet_config import (DUET, UI)

from utils.config import (get_prototypes_dir,
						   get_model_path, get_model_options_path,
						config_set_paths_and_initialize,DEVICE_TYPE, SUCCESS_LABEL)


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

			if request.url.path == '/': #Calling at root
				return RedirectResponse(url="/index", status_code=308)  #Permanent redirect

			if request.url.path.startswith("/index"):
				logger.debug(f'Index connection recieved from {request.client}')
			elif request.url.path.startswith("/settings"):
				logger.debug(f'Settings connection recieved from {request.client}')

		response = await call_next(request)
		return response

		
def appstartup():
	'''
	Run the FastAPI application with uvicorn
	'''
	# pylint: disable=C0415
	import uvicorn

	# Allow config to first set paths for config file
	config_set_paths_and_initialize()

	init_routes_and_modules()
	
	logger.info(f'duetPrintGuard can be access using one of the following:')
	logger.info(f'Detection')
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
