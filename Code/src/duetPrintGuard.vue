<comment>
Displays an iFrame that is linked to the duetPrintGuard html Display
Polls the status of the sbcPlugin and terminates the DWC plugin if the sbcPlugin is terminated
Thanks to @MintyTrebor for all the help in getting this working
</comment>
<style scoped>
	.iframe-container {
		position: relative;
		background-color: transparent;
	}
	.iframe-container iframe {
	position: absolute;
		top: 0;
		left: 0;
	}			
</style>
 
<template>
		<div class="iframe_container">
			<iframe id="myiframe" :src= "myurl" width="100%" :height="tmpHeight" frameborder="0">
			</iframe>
		</div>
</template>
 
<script>
import Path from '@/utils/path';
import store from "@/store";
import { DisconnectedError, OperationCancelledError } from "@/utils/errors";

// <!-- Do not change
const pluginName = 'duetPrintGuard';
const configFile = pluginName + '/' + pluginName + '.config';
// -->
window.onmessage = function(event){
	if (event.data == 'reply') {
		console('Reply received!');
	}
};
export default {
	data() { 
		return{
			myurl: '',
			tmpHeight: "400px",
		}
	},
	methods: {		
		//Modified file load from @mintyTrebor 
		async loadSettingsFromFile() {
			let content ='';
			try {
				const setFileName = Path.combine(this.systemDirectory, configFile);
				const response = await store.dispatch("machine/download", { filename: setFileName, type: 'text', showSuccess: false, showError: false});
				content = await response;
			} catch (e) {
					if (!(e instanceof DisconnectedError) && !(e instanceof OperationCancelledError)) {
						console.warn(e);
						console.warn("File Does Not Exist or Network error");
					}
			}
			// Ini parser from https://gist.github.com/anonymous/dad852cde5df545ed81f1bc334ea6f72
			function parseINIString(data){
				var regex = {
					section: /^\s*\[\s*([^\]]*)\s*\]\s*$/,
					param: /^\s*([^=]+?)\s*=\s*(.*?)\s*$/,
					comment: /^\s*;.*$/
				};
				var value = {};
				var lines = data.split(/[\r\n]+/);
				var section = null;
				lines.forEach(function(line){
					if(regex.comment.test(line)){
						return;
					}else if(regex.param.test(line)){
						var match = line.match(regex.param);
						if(section){
							value[section][match[1]] = match[2];
						}else{
							value[match[1]] = match[2];
						}
					}else if(regex.section.test(line)){
						var match = line.match(regex.section);
						value[match[1]] = {};
						section = match[1];
					}else if(line.length == 0 && section){
						section = null;
					};
				});
				return value;
			}
		
			try {
				var data = content
				var javascript_ini = parseINIString(data);
				console.log(javascript_ini['DUET']);
				console.log(javascript_ini['DUET']['IP']);
				console.log(javascript_ini['UI']['PORT']);
				const ip = javascript_ini['DUET']['IP']
				const port = javascript_ini['UI']['PORT']

				this.myurl = 'http://' + ip + ':' + port;
				console.log('duetPrintGuard url is ' + this.myurl);

			} 
			catch(e) {
				console.log(e);
			}
		},
		// Set the screen height - from @MintyTrebor
		getAvailScreenHeight(){
		let tmpHeight = window.innerHeight - 90;
		if(window.document.getElementById("global-container")){
			tmpHeight = tmpHeight - window.document.getElementById("global-container").offsetHeight;
		}
		if(this.showBottomNavigation) {
			tmpHeight = tmpHeight - 56;
		}
		return tmpHeight;
		},
		// Check to see if the sbcExecutable is running - if not close the DWC side of the plugin
		checkExecutable() {
		let self = this;
		setInterval(function() {self.checkRunning();},5000); // Check every 5 seconds
		},
		checkRunning() {
		let self = this;
		if (self.isrunning()){
			return;
		}
		self.stopthePlugin();
		},
		async stopthePlugin() {
			// console.log('Stopping the plugin');
			store.dispatch("machine/unloadDwcPlugin", pluginName); // Unload the plugin
		},
		// sbc Executable is running if pid > 0
		isrunning() {
		const allplugins = store.state.machine.model.plugins;
		for (let [key, value] of allplugins) {
			//console.log(key, value);
			if (key == pluginName){
				//console.log('Pid = ' + value.pid);
				if (value.pid > 0){
					return true
				};
				return false;
			};
		};
		}
	},	
	// use computed instead of methods cuz we only want it to run once
	computed:{
		systemDirectory() {
			return store.state.machine.model.directories.system;
		},
		showBottomNavigation() {
		return this.$vuetify.breakpoint.mobile && !this.$vuetify.breakpoint.xsOnly && this.$store.state.settings.bottomNavigation;
		}
	},
	mounted() {
		this.loadSettingsFromFile();
		this.getAvailScreenHeight();
		this.checkExecutable();
	} 
}
</script>
 
