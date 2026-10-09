// =========================
// Server-Sent Events from /sse
// =========================
// PG.connectSSE(handlers) opens the event stream and calls handlers[eventName](data) with the parsed
// payload of each event (countdown_time, camera_updated, autostart_updated, autostart_running).
// Returns a function that closes the connection.

(function () {
	'use strict';

	function parse(data) {
		return typeof data === 'string' ? JSON.parse(data) : data;
	}

	function connectSSE(handlers) {
		let source;
		try {
			source = new EventSource('/sse');
		} catch (error) {
			console.error('Failed to create EventSource', error);
			return () => {};
		}

		source.onopen = () => console.info('SSE connection opened');
		source.onerror = (err) => console.error('SSE error', err, 'readyState=', source.readyState);

		function dispatch(event, data) {
			const handler = handlers[event];
			if (!handler) {
				return;
			}
			try {
				handler(parse(data));
			} catch (error) {
				console.error(`Error handling SSE ${event} event:`, error, data);
			}
		}

		for (const event of Object.keys(handlers)) {
			source.addEventListener(event, (e) => dispatch(event, e.data));
		}

		// Unnamed messages wrap the event: { data: { event, data } }
		source.onmessage = (e) => {
			try {
				const packet = parse(e.data)?.data;
				if (packet?.event) {
					dispatch(packet.event, packet.data);
				}
			} catch (error) {
				console.error('Error processing SSE message:', error);
			}
		};

		return () => source.close();
	}

	window.PG.connectSSE = connectSSE;
})();
