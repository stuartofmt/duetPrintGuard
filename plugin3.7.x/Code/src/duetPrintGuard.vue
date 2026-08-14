<!--
Displays an iFrame that is linked to the duetPrintGuard html Display
Polls the status of the sbcPlugin and terminates the DWC plugin if the sbcPlugin is terminated
Thanks to @MintyTrebor for all the help in getting this working
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
			<iframe id="myiframe" :src="myurl" width="100%" :height="tmpHeight" frameborder="0">
			</iframe>
		</div>
</template>
 
<script>
import { computed, defineComponent, getCurrentInstance, inject, onBeforeUnmount, onMounted, ref } from 'vue';
import Path from '@/utils/path';
import { useMachineStore } from 'DuetWebControl';

// <!-- Do not change
const pluginName = 'duetPrintGuard';
const configFile = `${pluginName}/${pluginName}.config`;
const backgroundTask = true; // Only set true is background task can be manually terminated
// -->

export default defineComponent({
	name: 'DuetPrintGuard',
	setup() {
		const machineStore = useMachineStore();
		const myurl = ref('');
		const tmpHeight = ref('400px');
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

		const systemDirectory = computed(() => machineStore.model.directories.system);

		const showBottomNavigation = computed(() => {
			return display?.mobile?.value === true &&
				display?.xs?.value !== true
		})

		const parseINIString = (data) => {
			const regex = {
				section: /^\s*\[\s*([^\]]*)\s*\]\s*$/,
				param: /^\s*([^=]+?)\s*=\s*(.*?)\s*$/,
				comment: /^\s*;.*$/
			};
			const value = {};
			const lines = data.split(/[\r\n]+/);
			let section = null;

			lines.forEach((line) => {
				if (regex.comment.test(line)) {
					return;
				}

				if (regex.param.test(line)) {
					const match = line.match(regex.param);
					if (section) {
						value[section][match[1]] = match[2];
					} else {
						value[match[1]] = match[2];
					}
					return;
				}

				if (regex.section.test(line)) {
					const match = line.match(regex.section);
					value[match[1]] = {};
					section = match[1];
					return;
				}

				if (line.length === 0 && section) {
					section = null;
				}
			});

			return value;
		};

		const loadSettingsFromFile = async () => {
			let content = '';
			try {
				const setFileName = Path.combine(systemDirectory.value, configFile);
				console.warn('Loading settings from ' + setFileName);
				const response = await machineStore.download ({
					filename: setFileName,
					type: 'text',
					showSuccess: false,
					showError: false
				});
				content = await response;
			} catch (e) {
				console.warn(e);
				console.warn('File Does Not Exist or Network error');
			}

			try {
				const javascript_ini = parseINIString(content);
				const ip = javascript_ini.DUET?.IP;
				const port = javascript_ini.UI?.PORT;

				if (ip && port) {
					myurl.value = `http://${ip}:${port}`;
					console.log('duetPrintGuard url is ' + myurl.value);
				}
			} catch (e) {
				console.log(e);
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
				return;
			}
			console.warn('Stopping duetPrintGuard plugin because the background task is not running');
			stopthePlugin();
		};

		// Not sure if this is the right syntax
		const stopthePlugin = async () => {
			await machineStore.dispatch('machine/unloadDwcPlugin', pluginName);
		};

		const isrunning = () => {
			const allPlugins = machineStore.model.plugins;   // ObjectModel map, use .get(id) / .values()
			const entries = allPlugins instanceof Map ? allPlugins.entries() : Object.entries(allPlugins);
			for (const [key, value] of entries) {
				if (key === pluginName) {
					console.warn('duetPrintGuard is running, pid = ' + value?.pid);
					return Number(value?.pid ?? 0) > 0;

				}
			}
			return false;
			
		};

		onMounted(() => {
			loadSettingsFromFile();
			getAvailScreenHeight();
			checkExecutable();  // Only runs if backgroundTask is true
		});

		onBeforeUnmount(() => {
			if (backgroundTask) {
				if (intervalId) {
					clearInterval(intervalId);
				}
			}
		});

		return {
			myurl,
			tmpHeight,
			systemDirectory,
			showBottomNavigation,
			loadSettingsFromFile,
			getAvailScreenHeight,
			checkExecutable,
			checkRunning,
			stopthePlugin,
			isrunning
		};
	}
});
</script>
 
