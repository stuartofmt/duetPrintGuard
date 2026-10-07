'use strict'

// import { registerRoute } from '../../routes'
import { registerRoute } from '@/routes'

//import Vue from 'vue';
import duetPrintGuard from './duetPrintGuard.vue'


// Register a route via Plugins -> duetPrintGuard
registerRoute(duetPrintGuard, {
	Plugins: {
		duetPrintGuard: {
			icon: 'mdi-transition',
			caption: 'duetPrintGuard',
			path: '/duetPrintGuard'
		}
	}
});