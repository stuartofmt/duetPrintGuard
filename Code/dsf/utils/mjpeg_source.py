"""
Helpers for HTTP cameras that serve MJPEG streams and JPEG snapshots.

The camera already delivers JPEG images, so these pass the bytes through
without decoding or re-encoding them. Only detection needs a decoded image,
and it gets that from the snapshot URL once per detection interval.

RTSP cameras still go through the shared video stream (OpenCV / FFmpeg).
"""
import asyncio
import io
import time
from typing import AsyncIterator, Iterator, Optional

import requests
from PIL import Image

from logger_module import logger

JPEG_START = b'\xff\xd8'
JPEG_END = b'\xff\xd9'
READ_CHUNK_SIZE = 16384
MAX_BUFFER_BYTES = 4 * 1024 * 1024  # Safety limit if no frame end is found


def is_http_source(source: Optional[str]) -> bool:
	return bool(source) and source.lower().startswith(('http://', 'https://'))


def fetch_snapshot_bytes(snapshot_url: str, timeout: float = 5) -> Optional[bytes]:
	"""Fetch a JPEG from a camera's snapshot URL. Returns None on failure."""
	try:
		r = requests.get(snapshot_url, timeout=timeout)
		r.raise_for_status()
		if not r.content.startswith(JPEG_START):
			logger.warning("Snapshot URL %s did not return a JPEG image", snapshot_url)
			return None
		return r.content
	except requests.exceptions.RequestException as e:
		logger.warning("Failed to fetch snapshot from %s: %s", snapshot_url, e)
		return None


def fetch_snapshot_image(snapshot_url: str) -> Optional[Image.Image]:
	"""Fetch a snapshot and decode it to an RGB PIL image for detection."""
	data = fetch_snapshot_bytes(snapshot_url)
	if data is None:
		return None
	try:
		return Image.open(io.BytesIO(data)).convert('RGB')
	except OSError as e:
		logger.warning("Could not decode snapshot from %s: %s", snapshot_url, e)
		return None


def iter_mjpeg_frames(stream_url: str, max_fps: float = 0, holder: Optional[dict] = None) -> Iterator[bytes]:
	"""Proxy an HTTP MJPEG stream as multipart JPEG parts, without re-encoding.

	Frames are found by their JPEG start / end markers, so this works whatever
	boundary string the camera uses. If max_fps is set, frames arriving faster
	than that are read and dropped so the output stays current.

	If holder is given, holder['response'] is set so another thread can close
	the connection (see stream_mjpeg).
	"""
	min_interval = 1.0 / max_fps if max_fps and max_fps > 0 else 0
	last_sent = 0.0
	try:
		with requests.get(stream_url, stream=True, timeout=(5, 10)) as r:
			if holder is not None:
				holder['response'] = r
			r.raise_for_status()
			buffer = b''
			for chunk in r.iter_content(chunk_size=READ_CHUNK_SIZE):
				buffer += chunk
				while True:
					start = buffer.find(JPEG_START)
					if start == -1:
						buffer = b''
						break
					end = buffer.find(JPEG_END, start + 2)
					if end == -1:
						buffer = buffer[start:]  # Wait for the rest of this frame
						if len(buffer) > MAX_BUFFER_BYTES:
							logger.warning("MJPEG frame too large from %s - discarding", stream_url)
							buffer = b''
						break
					frame = buffer[start:end + 2]
					buffer = buffer[end + 2:]
					now = time.time()
					if now - last_sent >= min_interval:
						last_sent = now
						yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
	except Exception as e: # Includes the errors raised when stream_mjpeg closes the connection
		if holder is not None and holder.get('closed'):
			logger.debug("MJPEG stream %s closed by viewer", stream_url)
		else:
			logger.warning("MJPEG stream %s ended: %s", stream_url, e)


def check_mjpeg_stream(stream_url: str) -> bool:
	"""Return True if at least one JPEG frame can be read from an HTTP MJPEG stream."""
	frames = iter_mjpeg_frames(stream_url)
	try:
		return next(frames, None) is not None
	finally:
		frames.close() # Closes the camera connection


async def stream_mjpeg(stream_url: str, max_fps: float = 0) -> AsyncIterator[bytes]:
	"""Async version of iter_mjpeg_frames for StreamingResponse.

	Starlette does not close a sync generator when the viewer disconnects, which
	would leave the camera connection open (and the camera streaming) forever.
	Here the camera connection is closed as soon as the viewer goes away.
	"""
	holder = {}
	frames = iter_mjpeg_frames(stream_url, max_fps, holder)
	try:
		while True:
			frame = await asyncio.to_thread(next, frames, None)
			if frame is None:
				break
			yield frame
	finally:
		holder['closed'] = True
		response = holder.get('response')
		if response is not None:
			response.close() # Unblocks the read in the worker thread, which then exits
