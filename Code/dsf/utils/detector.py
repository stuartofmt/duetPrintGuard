"""
Spaghetti detection with the PrintGuard model - onnxruntime and numpy only (no torch).

The model (model/model.onnx) turns an image into an embedding: 1024 numbers that describe
what the image looks like. model/prototypes.npy holds the average embedding of upstream
PrintGuard's example images of each class (a "prototypical network"). A frame is classified
as the class whose prototype its embedding is nearest to.

The prototypes only match this model - if the model is replaced, the prototypes must be too.

The preprocessing reproduces the torchvision pipeline the model was trained with
(Resize(256), Grayscale(3), CenterCrop(224), ToTensor, Normalize) exactly - tested to give
bit-identical input, and so identical results, on real camera frames.
"""
import os

import numpy as np
import onnxruntime as ort
from PIL import Image

from logger_module import logger

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model")
MODEL_FILE = os.path.join(MODEL_DIR, "model.onnx")
PROTOTYPES_FILE = os.path.join(MODEL_DIR, "prototypes.npy")

# Order of the rows in prototypes.npy
CLASS_NAMES = ['failure', 'success']
DEFECT_IDX = CLASS_NAMES.index('failure')

# Per-camera sensitivity is a slider position from -SENSITIVITY_STEPS (less sensitive) to
# +SENSITIVITY_STEPS (more sensitive), 0 = normal. See sensitivity_factor().
SENSITIVITY_STEPS = 10

RESIZE = 256
CROP = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]


def preprocess(image: Image.Image) -> np.ndarray:
	"""Prepare an RGB image for the model: a (1, 3, 224, 224) float32 array."""
	# Resize the shorter side to 256 (the longer side is truncated, as torchvision does)
	width, height = image.size
	if width <= height:
		size = (RESIZE, int(RESIZE * height / width))
	else:
		size = (int(RESIZE * width / height), RESIZE)
	image = image.resize(size, Image.BILINEAR)
	# Grayscale, then crop the centre (torchvision rounds the offsets)
	image = image.convert('L')
	width, height = image.size
	top = int(round((height - CROP) / 2.0))
	left = int(round((width - CROP) / 2.0))
	image = image.crop((left, top, left + CROP, top + CROP))
	# Scale to 0..1, repeat the grey channel three times, normalise
	array = np.asarray(image, dtype=np.float32) / 255.0
	array = np.repeat(array[None, :, :], 3, axis=0)
	return ((array - MEAN) / STD)[None]


def sensitivity_factor(position: int) -> float:
	"""The factor for Detector.predict from a sensitivity slider position: 10 ** (position / 10).

	0 gives 1 (normal - the nearest prototype wins). Each step is about x1.26, so the ends are 0.1 and 10:
	far left, a frame must be 10 times closer to failure than to success to be a failure (almost
	nothing fails); far right, it is a failure unless it is over 10 times closer to success (almost
	everything fails - normal frames are typically 5 - 8 times closer to success).
	"""
	position = max(-SENSITIVITY_STEPS, min(SENSITIVITY_STEPS, int(position)))
	return 10 ** (position / SENSITIVITY_STEPS)


class Detector:
	"""Loads the model and prototypes once; predict() is safe to call from worker threads."""

	def __init__(self):
		options = ort.SessionOptions()
		options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
		options.execution_mode = ort.ExecutionMode.ORT_PARALLEL
		self.session = ort.InferenceSession(MODEL_FILE, sess_options=options, providers=['CPUExecutionProvider'])
		self.input_name = self.session.get_inputs()[0].name
		self.output_name = self.session.get_outputs()[0].name
		self.prototypes = np.load(PROTOTYPES_FILE)
		if self.prototypes.shape[0] != len(CLASS_NAMES):
			raise ValueError(f'{PROTOTYPES_FILE} has {self.prototypes.shape[0]} prototypes, expected {len(CLASS_NAMES)}')
		logger.info("Detection model loaded: %s (input %s), prototypes %s",
					os.path.basename(MODEL_FILE), self.session.get_inputs()[0].shape, self.prototypes.shape)

	def distances(self, image: Image.Image) -> np.ndarray:
		"""Distance from the image's embedding to each class prototype."""
		embedding = self.session.run([self.output_name], {self.input_name: preprocess(image)})[0].flatten()
		return np.linalg.norm(self.prototypes - embedding, axis=1)

	def predict(self, image: Image.Image, factor: float = 1.0) -> int:
		"""The class index (see CLASS_NAMES): failure if the distance to the failure prototype is at most
		factor x the distance to the success prototype, else success.

		factor 1 is plain nearest-prototype; below 1 fewer frames are failures, above 1 more (see sensitivity_factor).
		"""
		distances = self.distances(image)
		success_idx = 1 - DEFECT_IDX
		return DEFECT_IDX if distances[DEFECT_IDX] <= distances[success_idx] * factor else success_idx
