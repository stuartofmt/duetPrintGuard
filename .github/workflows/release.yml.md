# Release workflow (`release.yml`)

These notes repeat the comments at the top of [`release.yml`](release.yml). If you change one, update the other.

## What this workflow does

It builds the installable plugin ZIP file on GitHub's servers, compiling the plugin against the DuetWebControl (DWC) source code. You do not need to build anything on your own computer.

The workflow can be started in two different ways, and they produce different results:

| | How it starts | What it produces | Use it to |
|---|---|---|---|
| **Automatic** | By itself, when you push a version tag (a tag whose name begins with `v`, e.g. `v1.2.3`) to GitHub | A public GitHub Release with the ZIP attached | Release a new version of the plugin |
| **Manual** | By you, from the GitHub website | A ZIP you can download and test. Nothing is published and no Release is created | Check that the plugin builds, or get a test ZIP |

## Automatic: how to publish a new release

> **Background:** a git tag is a label attached to one particular commit. This workflow does **not** create the tag for you. **You** create the tag, and pushing it to GitHub is what starts the workflow. The workflow then reads `plugin.json` and checks that the tag name matches the version number in it. If they do not match, the run stops with an error and nothing is released. (`package.json`'s version is not checked.)

### 1. Update the version in `plugin.json`

Open `plugin.json` and change the `"version"` value to the new version number, e.g. `"1.2.3"`. Commit this change and push it to the repository on GitHub.

### 2. Create and push the tag

Create a tag on that commit, named `v` followed by exactly the same version number, then push the tag to GitHub. From the repository folder on your computer run:

```bash
git tag v1.2.3
git push origin v1.2.3
```

Make sure the commit from step 1 is the one checked out when you run `git tag`, because the tag is attached to whatever commit you are currently on.

Alternatively, run `./scripts/release.sh`. It reads the version from `plugin.json`, reports whether that tag has already been used, and creates and pushes the tag for you. It never changes `plugin.json`.

> [!IMPORTANT]
> Do **not** create the tag or the Release using the **Releases** page on the GitHub website ("Draft a new release" / "Create a new release"). Doing that publishes a Release before this workflow runs, so the workflow will find an existing Release and ask you to approve overwriting it. Always create the tag with git as shown above and let this workflow create the Release.

> [!NOTE]
> Push one tag at a time. GitHub does not start workflows when more than three tags are pushed at once (e.g. with `git push --tags`).

### 3. Approve the run

Pushing the tag starts the workflow. It first checks the version and chooses which DWC version to build against, then **pauses** and waits for approval:

1. Go to the repository's **Actions** tab on GitHub and open the **Release** run for your tag.
2. Read the **Release preflight** summary. It shows the plugin version, the DWC version that will be used, and whether a Release already exists for this tag.
3. Click **Review deployments**, then **Approve and deploy** to continue, or **Reject** to stop.

- If a Release for this tag does not exist yet, approving creates it.
- If a Release for this tag **already** exists, approving **overwrites** its ZIP files, title and notes. Reject if you do not want that.

### 4. The Release is published

After approval the workflow builds the ZIP and publishes the GitHub Release automatically:

- **Title:** taken from `scripts/release-titles.txt`, using the version's position among all `v*` tags (just `vX.Y.Z` if there is no titles file).
- **Notes:** a list of changes generated from the commit messages since the previous tag (Conventional Commit messages such as `feat: …` and `fix: …` are grouped by type), plus install instructions.
- **Files:** the plugin ZIP (for DWC 3.7 and later also a small `-srcmap.zip` of source maps), plus any ZIP files in the `standalone-zip/` folder (renamed with a `standalone-` prefix).

No further action is needed. The Release is public as soon as the run finishes.

## Manual: how to make a test build without releasing anything

1. On GitHub, go to the **Actions** tab, select **Release** in the left-hand list, and click the **Run workflow** button.
2. In the **Use workflow from** drop-down, choose the **branch** you want to build (e.g. `3.7.x`). Do not choose a tag here (see the note below).
3. Optionally type a DWC version into the **dwc-ref** box (e.g. `v3.7.1`) to build against that exact DWC release. Leave it blank to use the default choice (see [Which DWC version is used](#which-dwc-version-is-used)). The version you type must still be compatible with `plugin.json`, or the run stops with an error.
4. Click **Run workflow**. The run pauses for approval just like the automatic one: open the run, click **Review deployments**, then **Approve and deploy**.
5. When the run finishes, scroll to the **Artifacts** section at the bottom of the run's page and download the ZIP. No Release is created, no tag is needed and the version is not checked.

> [!NOTE]
> If you choose a **tag** instead of a branch in step 2, the run is treated like an automatic one: it checks the tag against `plugin.json` and publishes (or overwrites) the GitHub Release for that tag, in addition to providing the downloadable ZIP.

The **Run workflow** button only appears if `release.yml` is also on the repository's default branch (`main`).

## Which DWC version is used

This applies to both automatic and manual runs. The `"dwcVersion"` value in `plugin.json` decides which DWC releases are compatible:

| `dwcVersion` | Allowed DWC releases |
|---|---|
| `"3.7"` | Any 3.7.x release. The first two numbers fix the series. |
| `"3.7.2"` | Only the 3.7.2 series: 3.7.2 and its pre-releases (e.g. `3.7.2-beta.1`, `3.7.2-rc.1`), but **not** 3.7.3 or later. |
| `"3.7.2-rc.2"` | The pre-release is the minimum within that series: `3.7.2-rc.2`, `3.7.2-rc.3`, … and 3.7.2, but not `3.7.2-rc.1` or 3.7.3. |

Unless you type a dwc-ref in a manual run, the newest compatible DWC release is used (pre-releases such as betas and release candidates are included).

## Where `plugin.json` can be

The workflow and the release scripts use the first `plugin.json` found: at the repository root, otherwise in a subfolder (e.g. `Code/plugin.json`). `.git`, `node_modules` and `venv` are skipped. If there is no `plugin.json` at the root and more than one in subfolders, the run stops with an error.

The scripts take the plugin's name, ZIP name and links from `plugin.json`, so they work unchanged for another plugin.

## Order the jobs run in

1. **resolve-dwc**: read `plugin.json`, check the tag matches its version, see if a Release already exists, and choose the DWC version.
2. **approval**: pause until someone approves at the `dwc-release-approval` environment.
3. **build**: download DWC and build the ZIP with DWC's `scripts/build-plugin.js`. DWC 3.7 and later write the ZIP next to `plugin.json`; earlier versions write it to DWC's `dist/` folder.
4. **output**: automatic: publish the GitHub Release. Manual: provide the ZIP as an artifact.

## One-time setup for a repository

- **Actions enabled:** Settings → Actions → General → "Allow all actions and reusable workflows". Forks have Actions turned off until you enable them.
- **Approval environment:** Settings → Environments → **New environment** named exactly `dwc-release-approval`. Tick **Required reviewers**, add yourself, leave **Prevent self-review** unticked, and save. Without required reviewers, runs do not pause.
