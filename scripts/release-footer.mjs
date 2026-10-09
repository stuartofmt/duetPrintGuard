#!/usr/bin/env node
/**
 * Print the static footer appended to every GitHub Release body: install instructions and the
 * DuetWebControl version the ZIP was built against.
 *
 * The plugin manifest path comes from MANIFEST (set by the release workflow; relative to the repository
 * root, default Code/plugin.json). The DWC details come from the CI build environment (the release
 * workflow sets these after it checks out DuetWebControl), so it also reads sensibly when run locally.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const manifestPath = join(here, "..", process.env.MANIFEST || "Code/plugin.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const pkgVersion = manifest.version;
const asset = `${manifest.id}-${pkgVersion}.zip`;

const dwcVersion = process.env.DWC_VERSION || "";

// Resolve the manifest's dwcVersion the same way DWC's build does ("auto" -> full DWC version,
// "auto-major" -> major.minor), so the metadata below matches the requirement DWC actually enforces
// at install. This is what the update checker compares the running DWC version against.
function resolveDwcRequirement(value, reference) {
	if (value === "auto") return reference;
	if (value === "auto-major") return reference.split(".").slice(0, 2).join(".");
	return value || "";
}
const requiredDwc = resolveDwcRequirement(manifest.dwcVersion, dwcVersion);
const dwcSha = process.env.DWC_SHA || "";
const dwcRef = process.env.DWC_REF || "next";
const dwcBuiltAgainst = dwcVersion
	? `**DuetWebControl ${dwcVersion}**${dwcSha ? ` (\`${dwcSha}\`, ref \`${dwcRef}\`)` : ` (ref \`${dwcRef}\`)`}`
	: `DuetWebControl (ref \`${dwcRef}\`)`;

const out = `
---

### 📦 Install
1. Download \`${asset}\` from the **Assets** below.
2. In DuetWebControl, go to **Settings → General → Plugins** and click **Install Plugin**.
3. Select the downloaded ZIP and accept the third-party-plugin prompt.
4. Reload DWC if asked.

See the [installation and configuration guide](${manifest.homepage ? `${manifest.homepage}/blob/${process.env.GITHUB_REF_NAME || "main"}/docs/Installation-Configuration.md` : "docs/Installation-Configuration.md"}) for setup details.

> 🔧 Built against ${dwcBuiltAgainst}. Requires DuetWebControl ${requiredDwc || dwcVersion || "(see plugin.json)"} on a Duet running in SBC mode.

<!-- dwc-plugin-update ${JSON.stringify({ version: pkgVersion, dwcVersion: requiredDwc, asset })} -->
`;

process.stdout.write(out.replace(/^\n/, ""));
