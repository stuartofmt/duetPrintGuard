// visibility.visible is false while the browser tab is hidden or, inside DWC, while DWC shows a different
// page (DWC posts { source: 'duetPrintGuard', type: 'visibility', visible }). Pages close their camera
// streams and event connections while hidden - browsers only allow 6 connections to the plugin, shared
// by every tab, and further requests wait until one closes.
import { reactive } from "vue";
import { embedded } from "./pages.js";

export const visibility = reactive({ visible: !document.hidden });
let parentVisible = true;

function updateVisibility() {
	visibility.visible = !document.hidden && parentVisible;
}

document.addEventListener("visibilitychange", updateVisibility);
if (embedded) {
	window.addEventListener("message", (event) => {
		const msg = event.data;
		if (event.source === window.parent && msg?.source === "duetPrintGuard" && msg.type === "visibility") {
			parentVisible = Boolean(msg.visible);
			updateVisibility();
		}
	});
}
