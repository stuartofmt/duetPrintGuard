<!--
Displays an iFrame that is linked to the duetPrintGuard html Display
Polls the status of the sbcPlugin and displays a message if the sbcPlugin is terminated
Stops polling once the plugin has been detected as stopped
Adds ?mobile=true to the iframe URL when accessed from a mobile device
-->
<style scoped>
	.iframe_container {
		position: relative;
		background-color: transparent;
	}
	.iframe_container iframe {
		position: absolute;
		top: 0;
		left: 0;
	}
</style>
 
<template>
		<div class="iframe_container">
			<iframe
				v-if="!pluginStopped"
				id="myiframe"
				:src="myurl"
				width="100%"
				:height="tmpHeight"
				frameborder="0">
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
 
<script>
import { computed, defineComponent, getCurrentInstance, inject, onBeforeUnmount, onMounted, ref } from 'vue';
import { useMachineStore } from 'DuetWebControl';

// <!-- Do not change
const pluginName = 'duetPrintGuard';
const backgroundTask = true; // Only set true if background task can be manually terminated
// -->

export default defineComponent({
	name: pluginName,
	setup() {
		const machineStore = useMachineStore();
		const myurl = ref('');
		const tmpHeight = ref('400px');
		const pluginStopped = ref(false);
		const instance = getCurrentInstance();
		
		// Access Vuetify's display object through injection
		// This avoids bundling a second copy of Vuetify
		const display = inject(Symbol.for('vuetify:display'), null);
		let intervalId = null;

		if (typeof window !== 'undefined') {
			window.onmessage = function (event) {
				if (event.data == 'reply') {
					console.log('Reply received!');
				}
			};
		}

		const showBottomNavigation = computed(() => {
			return display?.mobile?.value === true &&
				display?.xs?.value !== true
		})

		const isMobile = () => {
			const userAgent = navigator.userAgent || navigator.vendor || window.opera || '';

			// Detect iPhone, iPad, Android and other mobile devices
			const isMobileUA = /android|iphone|ipod|ipad|mobile|phone/i.test(userAgent);

			// iPadOS 13+ can identify itself as Macintosh, so also check touch capability
			const isIPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;

			const result = isMobileUA || isIPadOS;

			return result;
		};

		const pluginData = () => {
			const plugins = machineStore.model.plugins;
			const plugin = plugins instanceof Map ? plugins.get(pluginName) : plugins?.[pluginName];
			return plugin?.data;
		};

		const getDataValue = (data, key) => (data instanceof Map ? data.get(key) : data?.[key]);

		// The plugin publishes its address a few seconds after it starts, so this is polled
		const updateUrl = () => {
			const data = pluginData();
			const ip = getDataValue(data, 'ip');
			const port = getDataValue(data, 'port');
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
			const mobileParameter = isMobile() ? '?mobile=true' : '';
			const url = `http://${ip}:${port}${mobileParameter}`;
			if (url !== myurl.value) {
				console.log(`ip = ${ip} and port = ${port}`);
				myurl.value = url;
			}
		};

		const getAvailScreenHeight = () => {
			let height = window.innerHeight - 90;

			if (window.document.getElementById('global-container')) {
				height -= window.document.getElementById('global-container').offsetHeight;
			}

			if (showBottomNavigation.value) {
				height -= 56;
			}

			tmpHeight.value = height + 'px';
			return tmpHeight.value;
		};
		
		const checkExecutable = () => {
			if (backgroundTask) {
				intervalId = setInterval(() => {
					checkRunning();
				}, 5000);
			}
		};

		const checkRunning = () => {
			if (isrunning()) {
				updateUrl();
				return;
			}

			console.warn(`${pluginName} plugin is no longer running`);

			// Stop polling because the plugin has stopped
			if (intervalId) {
				clearInterval(intervalId);
				intervalId = null;
			}

			// Replace the iframe with the stopped message
			pluginStopped.value = true;
		};

		// Not used when the plugin stops.
		// Kept here to avoid any other functional changes.
		const stopthePlugin = async () => {
			await machineStore.dispatch('machine/unloadDwcPlugin', pluginName);
		};

		const isrunning = () => {
			const allPlugins = machineStore.model.plugins;   // ObjectModel map, use .get(id) / .values()
			const entries = allPlugins instanceof Map ? allPlugins.entries() : Object.entries(allPlugins);

			for (const [key, value] of entries) {
				if (key === pluginName) {
					console.warn(`${pluginName} is running, pid = ${value?.pid}`);
					return Number(value?.pid ?? 0) > 0;
				}
			}

			return false;
		};

		onMounted(() => {
			updateUrl();
			getAvailScreenHeight();
			checkExecutable();  // Only runs if backgroundTask is true
		});

		onBeforeUnmount(() => {
			if (backgroundTask) {
				if (intervalId) {
					clearInterval(intervalId);
					intervalId = null;
				}
			}
		});

		return {
			pluginName,
			myurl,
			tmpHeight,
			pluginStopped,
			showBottomNavigation,
			getAvailScreenHeight,
			checkExecutable,
			checkRunning,
			stopthePlugin,
			isrunning
		};
	}
});
</script>
