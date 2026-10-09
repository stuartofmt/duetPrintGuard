<!--
Displays an iFrame that is linked to the duetPrintGuard html Display
Polls the status of the sbcPlugin and displays a message if the sbcPlugin is terminated
Stops polling once the plugin has been detected as stopped
Adds ?mobile=true to the iframe URL when accessed from a mobile device
Passes DWC's theme to the page: ?theme=dark|light in the URL, then the live theme colours by postMessage
-->
<style scoped>
	.iframe_container {
		position: relative;
		background-color: transparent;
	}
	.iframe_container iframe {
		display: block;
		border: 0;
	}
</style>

<template>
	<div ref="container" class="iframe_container">
		<iframe
			v-if="!pluginStopped"
			id="myiframe"
			ref="iframe"
			:src="myurl"
			width="100%"
			:height="iframeHeight"
			@load="sendTheme">
		</iframe>

		<v-alert
			v-else
			type="warning"
			variant="tonal"
			class="ma-4"
		>
			The {{ pluginName }} plugin has stopped.
		</v-alert>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useTheme } from 'vuetify';
import { useMachineStore } from 'DuetWebControl';

// <!-- Do not change
const pluginName = 'duetPrintGuard';
const backgroundTask = true; // Only set true if background task can be manually terminated
// -->

defineOptions({ name: pluginName });

const machineStore = useMachineStore();
const theme = useTheme();
// Only the starting theme goes in the URL, so a theme change does not reload the page
const initialTheme = theme.global.current.value.dark ? 'dark' : 'light';
const container = ref(null);
const iframe = ref(null);
const myurl = ref('');
const iframeHeight = ref('400px');
const pluginStopped = ref(false);
let intervalId = null;
let resizeObserver = null;

// Send DWC's current theme to the page so it matches, including plugin themes and later changes
const sendTheme = () => {
	const target = iframe.value?.contentWindow;
	if (!target || !myurl.value) {
		return;
	}
	const current = theme.global.current.value;
	target.postMessage({
		source: pluginName,
		type: 'theme',
		dark: current.dark,
		colors: JSON.parse(JSON.stringify(current.colors)) // plain copy - reactive proxies can't be posted
	}, new URL(myurl.value).origin);
};

watch(() => theme.global.current.value, sendTheme, { deep: true });

const onMessage = (event) => {
	if (event.data == 'reply') {
		console.log('Reply received!');
	} else if (event.source === iframe.value?.contentWindow && event.data?.source === pluginName && event.data.type === 'theme-request') {
		sendTheme();
	}
};

const isMobile = () => {
	const userAgent = navigator.userAgent || navigator.vendor || window.opera || '';

	// Detect iPhone, iPad, Android and other mobile devices
	const isMobileUA = /android|iphone|ipod|ipad|mobile|phone/i.test(userAgent);

	// iPadOS 13+ can identify itself as Macintosh, so also check touch capability
	const isIPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;

	return isMobileUA || isIPadOS;
};

// machineStore.model.plugins is an object model dictionary (a Map); plain objects are handled too
const getValue = (collection, key) => (collection instanceof Map ? collection.get(key) : collection?.[key]);

const pluginData = () => getValue(machineStore.model.plugins, pluginName)?.data;

// The plugin publishes its address a few seconds after it starts, so this is polled
const updateUrl = () => {
	const data = pluginData();
	const ip = getValue(data, 'ip');
	const port = getValue(data, 'port');
	if (!ip || !port) {
		const plugins = machineStore.model.plugins;
		console.log('ip and or port not found', {
			pluginsType: plugins?.constructor?.name,
			pluginKeys: plugins instanceof Map ? [...plugins.keys()] : Object.keys(plugins ?? {}),
			dataType: data?.constructor?.name,
			data: data instanceof Map ? Object.fromEntries(data) : data
		});
		return;
	}
	const query = new URLSearchParams({ theme: initialTheme });
	if (isMobile()) {
		query.set('mobile', 'true');
	}
	const url = `http://${ip}:${port}/?${query}`;
	if (url !== myurl.value) {
		console.log(`ip = ${ip} and port = ${port}`);
		myurl.value = url;
	}
};

// Fill the window below wherever DWC's layout puts the iframe (app bar, status panel, ...)
const updateHeight = () => {
	if (!container.value) {
		return;
	}
	const top = container.value.getBoundingClientRect().top + window.scrollY;
	iframeHeight.value = Math.max(window.innerHeight - top - 16, 200) + 'px';
};

const isRunning = () => Number(getValue(machineStore.model.plugins, pluginName)?.pid ?? 0) > 0;

const stopPolling = () => {
	if (intervalId) {
		clearInterval(intervalId);
		intervalId = null;
	}
};

const checkRunning = () => {
	if (isRunning()) {
		updateUrl();
		return;
	}

	console.warn(`${pluginName} plugin is no longer running`);

	// Stop polling because the plugin has stopped and replace the iframe with the stopped message
	stopPolling();
	pluginStopped.value = true;
};

onMounted(() => {
	window.addEventListener('message', onMessage);
	window.addEventListener('resize', updateHeight);

	// The status panel above the route can expand or collapse, which moves the iframe
	const main = container.value?.closest('.v-main');
	if (main && typeof ResizeObserver !== 'undefined') {
		resizeObserver = new ResizeObserver(updateHeight);
		resizeObserver.observe(main);
	}

	updateUrl();
	updateHeight();
	if (backgroundTask) {
		intervalId = setInterval(checkRunning, 5000);
	}
});

onBeforeUnmount(() => {
	window.removeEventListener('message', onMessage);
	window.removeEventListener('resize', updateHeight);
	resizeObserver?.disconnect();
	stopPolling();
});
</script>
