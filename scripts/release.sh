#!/bin/bash
# Release the plugin version that is in plugin.json (the first one found in the repository).
#
# This script does NOT change plugin.json. It:
#   1. reads "version" from plugin.json and works out the tag name: v<version> on the latest channel,
#      v<version>-dwc<dwcVersion> on a maintenance channel (set in scripts/release-channel.txt)
#   2. reports whether that tag has already been used (on this computer or on GitHub)
#   3. asks whether to release with this tag or create a new one:
#        - use this tag: pushes the branch, creates the tag and pushes it on its own
#        - new tag:      tells you to update and commit plugin.json first, then exits
#
# Pushing the tag starts the Release workflow (.github/workflows/release.yml). Approve the run in the
# repository's Actions tab when it pauses at dwc-release-approval.
#
# Run from VS Code's terminal (so the GitHub sign-in is available):  ./scripts/release.sh

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Use the first plugin.json found: the repository root first, then the shallowest subfolder (skipping
# .git, node_modules and venv). The Release workflow stops if there is more than one, so warn about that.
MANIFESTS=$(find . \( -name .git -o -name node_modules -o -name venv \) -prune -o -type f -name plugin.json -print \
	| awk -F/ '{ print NF "\t" $0 }' | sort -n -k1,1 -k2 | cut -f2- | sed 's|^\./||')
[ -n "$MANIFESTS" ] || { echo "Error: no plugin.json found in this repository."; exit 1; }
MANIFEST=$(echo "$MANIFESTS" | head -n1)
if [ "$(echo "$MANIFESTS" | wc -l)" -gt 1 ]; then
	echo "Warning: more than one plugin.json found - using $MANIFEST. Others:"
	echo "$MANIFESTS" | tail -n +2 | sed 's/^/  /'
	echo "(The Release workflow stops if there is more than one plugin.json in subfolders.)"
	echo
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$MANIFEST")

# Release channel (scripts/release-channel.txt, default "latest"; same rules as scripts/manifest.mjs).
CHANNEL=""
[ -f scripts/release-channel.txt ] && CHANNEL=$(sed -e 's/#.*//' -e 's/[[:space:]]//g' scripts/release-channel.txt | grep -m1 . || true)
CHANNEL=${CHANNEL:-latest}
case "$CHANNEL" in
	latest) TAG="v$VERSION" ;;
	maintenance)
		DWC_VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['dwcVersion'])" "$MANIFEST")
		TAG="v$VERSION-dwc$DWC_VERSION"
		;;
	*) echo "Error: scripts/release-channel.txt must say \"latest\" or \"maintenance\", not \"$CHANNEL\"."; exit 1 ;;
esac

echo "Branch:       $BRANCH"
echo "Version:      $VERSION  (from $MANIFEST)"
echo "Channel:      $CHANNEL"
echo "Release tag:  $TAG"
echo

# --- Has this tag already been used? ---------------------------------------------------------------
USED_LOCAL=false
USED_REMOTE=false
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && USED_LOCAL=true
git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1 && USED_REMOTE=true

if $USED_LOCAL || $USED_REMOTE; then
	echo "Tag $TAG has ALREADY been used:"
	$USED_LOCAL  && echo "  - it exists on this computer"
	$USED_REMOTE && echo "  - it exists on GitHub"
else
	echo "Tag $TAG has not been used yet."
fi
echo

# --- Use this tag, or create a new one? ------------------------------------------------------------
echo "  1) Use tag $TAG"
echo "  2) Create a new tag"
read -rp "Choose 1 or 2: " CHOICE
echo

case "$CHOICE" in
	1) ;;
	2)
		echo "To use a new tag:"
		echo "  1. Change \"version\" in $MANIFEST to the new version number."
		echo "  2. Commit that change (and push it)."
		echo "  3. Run this script again."
		exit 0
		;;
	*)
		echo "Cancelled - nothing changed."
		exit 0
		;;
esac

# --- Checks before using the tag -------------------------------------------------------------------
if $USED_LOCAL || $USED_REMOTE; then
	echo "Cannot use $TAG because it already exists. Either choose a new tag (option 2), or delete"
	echo "the existing one first and run this script again:"
	$USED_REMOTE && echo "  git push origin --delete $TAG"
	$USED_LOCAL  && echo "  git tag -d $TAG"
	exit 1
fi

# The tag is put on the current commit, so plugin.json must be committed with this version.
if ! git diff --quiet HEAD -- "$MANIFEST"; then
	echo "Error: $MANIFEST has uncommitted changes. Commit it first, then run this script again."
	exit 1
fi

# --- Release ---------------------------------------------------------------------------------------
echo "This will:"
echo "  - push branch $BRANCH to GitHub"
echo "  - create tag $TAG on the current commit ($(git log -1 --format='%h %s'))"
echo "  - push tag $TAG (this starts the Release workflow)"
read -rp "Continue? [y/N] " ANSWER
[[ "$ANSWER" =~ ^[Yy]$ ]] || { echo "Cancelled - nothing changed."; exit 0; }

git push origin "$BRANCH"
git tag "$TAG"
git push origin "$TAG"

echo
echo "Done. Tag $TAG pushed - approve the Release run at:"
echo "  $(git remote get-url origin | sed 's/\.git$//')/actions"
