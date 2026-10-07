'use strict'

import { registerRoute } from 'DuetWebControl';
import duetPrintGuard from './duetPrintGuard.vue';

registerRoute(duetPrintGuard, {
  Plugins: {
    duetPrintGuard: {
      icon: 'mdi-transition',
      caption: 'duetPrintGuard',
      path: '/Plugins/duetPrintGuard',
    },
  },
});
