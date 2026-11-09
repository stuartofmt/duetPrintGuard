// Display text for the pages, from a file per language in locales/ (en.json, de.json, ...) - the same scheme as duetLapse3.
//   The language: ?lang=<code> in the url, otherwise the first of the browser's languages that has a file, otherwise English.
//   A language file only needs the texts it translates - anything it doesn't have is shown in English.
//   A new locales/<code>.json is included automatically when the pages are built.
//   t("detection.pause"), t("settings.removed", { name }) - {name} in the text is replaced by the value.
//   A text with "one" and "other" forms picks one by the value n, e.g. t("x", { n: 3 }).
//   values: the values duetPrintGuard reports (e.g. a detection result, the printer status).
//   server: duetPrintGuard's own messages, by the code it sends with them (see Code/dsf/messages.py).
// Anything missing from English too falls back to its own name, or to the text duetPrintGuard sent.
import { query } from "./pages.js";

const files = import.meta.glob("./locales/*.json", { eager: true, import: "default" });
const locales = Object.fromEntries(Object.entries(files).map(([path, data]) => [path.match(/([\w-]+)\.json$/)[1].toLowerCase(), data]));

// The first wanted language with a file: de-CH is tried as de-ch, then de
function pickLanguage() {
	const wanted = [query.get("lang"), ...(navigator.languages ?? [navigator.language])].filter(Boolean);
	for (const code of wanted.map((c) => c.toLowerCase())) {
		for (const tryCode of [code, code.split("-")[0]]) {
			if (locales[tryCode]) {
				return tryCode;
			}
		}
	}
	return "en";
}

// The language's texts laid over English, so English fills any gaps
function merge(base, over) {
	const result = { ...base };
	for (const [key, value] of Object.entries(over ?? {})) {
		const isGroup = value && typeof value === "object" && !Array.isArray(value);
		result[key] = isGroup && base[key] && typeof base[key] === "object" ? merge(base[key], value) : value;
	}
	return result;
}

export const language = pickLanguage();
const messages = language === "en" ? locales.en : merge(locales.en, locales[language]);
document.documentElement.lang = language;  // For the browser - e.g. spell checking, screen readers

const fill = (text, params) => text.replace(/\{(\w+)\}/g, (match, name) => String(params[name] ?? match));

export function t(path, params = {}) {
	let text = path.split(".").reduce((node, key) => node?.[key], messages);
	if (text && typeof text === "object") {
		text = params.n === 1 ? text.one : text.other;
	}
	return typeof text === "string" ? fill(text, params) : path;
}

// A value duetPrintGuard reports, e.g. valueText("result", "success") - unknown values are shown as they are
export const valueText = (group, value) => messages.values?.[group]?.[value] ?? value;

// A message from duetPrintGuard: text is its English, coded is the { code, params } sent with it (or null)
export function serverText(text, coded) {
	const known = coded && messages.server?.[coded.code];
	if (!known) {
		return text ?? "";
	}
	return fill(known, { ...coded.params });
}

// An error from api.js: the server's message in this language, or the error's own text
export const errorText = (err) => serverText(err?.data?.detail ?? err?.data?.message ?? err?.message, err?.data?.code);

// A text that may not be there (e.g. a setting with no hint) - "" if missing
export function optional(path, params = {}) {
	const text = t(path, params);
	return text === path ? "" : text;
}
