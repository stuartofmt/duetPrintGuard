# duetPrintGuard web interface

The Detection, Settings, Configuration and camera stream pages, written as Vue 3 single-file components with Vuetify 4 and built with Vite (the same setup as multiCam's `ui/`).

`npm run build` writes the pages and their assets to `Code/dsf/static/app/`, which the plugin serves (`/index`, `/settings`, `/config`, `/stream/<nickname>`). The built files are committed, so the plugin needs no Node.js or internet access. **After changing anything in `ui/`, run `npm run build` and commit `Code/dsf/static/app/` with the change.**

## Building

```bash
cd ui
npm install      # once
npm run build    # writes Code/dsf/static/app
```

## Developing with live reload

Start duetPrintGuard (the plugin, or `./run.sh <folder>` from the repository), then:

```bash
npm run dev
```

and open http://localhost:5173/static/app/index.html. Changes show as soon as they are saved. API calls, events, snapshots and streams go to the running duetPrintGuard - `http://localhost:17800` unless `PRINTGUARD_URL` says otherwise, e.g. `PRINTGUARD_URL=http://192.168.1.20:17800 npm run dev`.

## Layout

| | |
|---|---|
| `index.html`, `settings.html`, `config.html`, `stream.html` | One entry per page |
| `src/detection/`, `src/settings/`, `src/config/`, `src/stream/` | Each page's component (`settings/CameraCard.vue` is one camera's card) |
| `src/components/PgPage.vue` | Layout shared by the pages: navigation tabs, the message bar and the confirm dialog |
| `src/vuetify.js` | Vuetify set up as DWC 3.7 does, and following DWC's theme when shown inside DWC |
| `src/visibility.js` | Whether the page is being shown - pages close their streams while hidden |
| `src/api.js`, `src/sse.js`, `src/notify.js`, `src/pages.js` | Server calls, live events, messages / confirm, and page links |
| `src/icons.js` | The icons used - only these are bundled (import new ones from `@mdi/js` here) |
| `src/app.css`, `src/fonts/` | Shared styles and the Roboto font DWC uses |
