// Calls to the duetPrintGuard server. Each returns the parsed JSON (or null) or throws an Error whose message
// is the server's detail text; error.status and error.data hold the HTTP status and the parsed reply.

async function request(url, options) {
	const response = await fetch(url, options);
	let data = null;
	try {
		data = await response.json();
	} catch {
		// Some endpoints return nothing
	}
	if (!response.ok) {
		const error = new Error(data?.detail || response.statusText || `HTTP ${response.status}`);
		error.status = response.status;
		error.data = data;
		throw error;
	}
	return data;
}

export const api = {
	get: (url) => request(url),
	postJson: (url, body) => request(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	}),
	// For endpoints that take Form(...) fields
	postForm: (url, fields) => request(url, {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: new URLSearchParams(fields),
	}),
};
