#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ANDROID_JAR="$APP_HOME/build-tools/android.jar"
KEYSTORE="$APP_HOME/build/nemotron-unrestricted.keystore"
SIGNING_PROPERTIES="$APP_HOME/build/signing.properties"
VERSION_CODE="9"
VERSION_NAME="1.8.0"
REPRODUCIBLE_ZIP_DATE="2008-01-01T00:00:00Z"
ARTIFACT="Nemotron-Unrestricted-$VERSION_NAME.apk"
OUTPUT="$APP_HOME/dist/$ARTIFACT"
DEBUG_ARTIFACT="Nemotron-Unrestricted-$VERSION_NAME-debug.apk"
DEBUG_OUTPUT="$APP_HOME/dist/$DEBUG_ARTIFACT"
EXPECTED_PACKAGE="com.michaelovsky.nemotronunrestricted.isolated"

"$APP_HOME/bootstrap-nemotron-runtime.sh"
python "$APP_HOME/tools/patch-codexapp-ui.py"
"$APP_HOME/sync-nemotron-web.sh"

if [ ! -f "$ANDROID_JAR" ] || [ ! -f "$KEYSTORE" ] || [ ! -f "$SIGNING_PROPERTIES" ]; then
  printf 'Required project-local build material is missing.\n' >&2
  exit 2
fi

for required_executable in \
	  "$APP_HOME/bootstrap-nemotron-runtime.sh" \
	  "$APP_HOME/validate-nemotron-sources.sh" \
	  "$APP_HOME/scan-nemotron-secrets.py" \
  "$APP_HOME/build-face-detector.sh" \
  "$APP_HOME/install-security-toolchain.sh" \
	  "$APP_HOME/generate-signing-key.sh" \
	  "$APP_HOME/bin/codex-install" \
	  "$APP_HOME/bin/codex-android" \
	  "$APP_HOME/bin/codex-download" \
	  "$APP_HOME/bin/codex-runtime-status" \
	  "$APP_HOME/bin/codex-exec" \
	  "$APP_HOME/bin/codex-doctor" \
	  "$APP_HOME/bin/codex-maintain" \
	  "$APP_HOME/bin/codex-automation" \
	  "$APP_HOME/bin/codex-boot" \
	  "$APP_HOME/bin/codex-storage" \
	  "$APP_HOME/bin/codex-battery" \
	  "$APP_HOME/bin/codex-task" \
	  "$APP_HOME/bin/codex-schedule" \
	  "$APP_HOME/bin/codex-pc" \
	  "$APP_HOME/bin/codex-pc-monitor" \
	  "$APP_HOME/bin/codex-pc-route" \
	  "$APP_HOME/bin/codex-inventory" \
	  "$APP_HOME/bin/codex-dashboard" \
	  "$APP_HOME/bin/codex-registry" \
	  "$APP_HOME/bin/codex-research" \
	  "$APP_HOME/bin/codex-browser-safe" \
	  "$APP_HOME/bin/codex-artifacts" \
	  "$APP_HOME/bin/codex-scaffold" \
	  "$APP_HOME/bin/codex-toolchain" \
	  "$APP_HOME/bin/codex-pipeline" \
	  "$APP_HOME/bin/codex-release" \
	  "$APP_HOME/bin/codex-intent" \
	  "$APP_HOME/bin/codex-ui-safe" \
	  "$APP_HOME/bin/codex-device" \
	  "$APP_HOME/bin/codex-trip" \
	  "$APP_HOME/bin/codex-deploy" \
	  "$APP_HOME/bin/codex-netdiag" \
	  "$APP_HOME/bin/codex-secrets" \
	  "$APP_HOME/bin/codex-security" \
	  "$APP_HOME/bin/codex-command" \
	  "$APP_HOME/bin/codex-files" \
	  "$APP_HOME/bin/codex-device-io" \
	  "$APP_HOME/bin/codex-care" \
	  "$APP_HOME/bin/codex-resilience" \
	  "$APP_HOME/bin/nemotron-runtime-capability" \
	  "$APP_HOME/bin/codex-job" \
	  "$APP_HOME/bin/codex-goal" \
	  "$APP_HOME/bin/codex-recover" \
	  "$APP_HOME/bin/codex-capability" \
	  "$APP_HOME/bin/codex-artifact" \
	  "$APP_HOME/bin/codex-verify" \
	  "$APP_HOME/bin/codex-browser" \
	  "$APP_HOME/bin/codex-ui" \
	  "$APP_HOME/bin/codex-network" \
	  "$APP_HOME/bin/codex-account" \
	  "$APP_HOME/bin/codex-entitlement" \
	  "$APP_HOME/bin/codex-pm" \
  "$APP_HOME/bin/codex-package" \
  "$APP_HOME/bin/codex-open-url" \
  "$APP_HOME/bin/codex-shizuku" \
  "$APP_HOME/bin/codex-uninstall" \
  "$APP_HOME/bin/codex-learn" \
  "$APP_HOME/bin/codex-lessons" \
  "$APP_HOME/bin/codex-win" \
  "$APP_HOME/bin/codex-github" \
  "$APP_HOME/bin/powershell" \
  "$APP_HOME/bin/pwsh" \
  "$APP_HOME/bin/rish" \
  "$APP_HOME/bin/nemotron-runtime-rish" \
  "$APP_HOME/bin/rg" \
  "$APP_HOME/bin/ripgrep" \
	  "$APP_HOME/bin/codex-pentest" \
	  "$APP_HOME/bin/codex-gallery" \
  "$APP_HOME/bin/codex-wifi-scan" \
  "$APP_HOME/bin/codex-lan-discover" \
  "$APP_HOME/bin/iwlist"; do
  if [ ! -x "$required_executable" ]; then
    printf 'Required capability executable is missing: %s\n' "$required_executable" >&2
    exit 2
  fi
done

for required_capability in \
	  "$APP_HOME/capabilities/authorized-mobile-pentest/SKILL.md" \
	  "$APP_HOME/capabilities/android-autonomy/SKILL.md" \
	  "$APP_HOME/capabilities/CAPABILITY_CATALOG.md" \
	  "$APP_HOME/capabilities/NEMOTRON_AGENT_CONTRACT.md" \
	  "$APP_HOME/bin/nemotron_android_policy.py" \
	  "$APP_HOME/bin/nemotron_powershell_policy.py" \
	  "$APP_HOME/tools/NemotronFaceDetector.java" \
	  "$APP_HOME/tools/patch-codexapp-ui.py" \
	  "$APP_HOME/tools/render-offdevice-ui.py" \
	  "$APP_HOME/tools/render-icon.py" \
  "$APP_HOME/toolchain/termux-packages.txt" \
  "$APP_HOME/toolchain/python-requirements.txt"; do
  if [ ! -f "$required_capability" ]; then
    printf 'Required capability payload is missing: %s\n' "$required_capability" >&2
    exit 2
  fi
done

"$APP_HOME/validate-nemotron-sources.sh"
"$APP_HOME/scan-nemotron-secrets.py" --current-only
"$APP_HOME/build-face-detector.sh" >/dev/null

python - \
  "$APP_HOME/bin/nemotron_android_policy.py" \
  "$APP_HOME/bin/nemotron_powershell_policy.py" \
  "$APP_HOME/bin/codex-android" \
  "$APP_HOME/bin/codex-download" \
  "$APP_HOME/bin/codex-runtime-status" \
  "$APP_HOME/bin/codex-doctor" \
  "$APP_HOME/bin/codex-maintain" \
  "$APP_HOME/bin/codex-automation" \
  "$APP_HOME/bin/codex-boot" \
  "$APP_HOME/bin/codex-storage" \
  "$APP_HOME/bin/codex-battery" \
  "$APP_HOME/bin/codex-task" \
  "$APP_HOME/bin/codex-schedule" \
  "$APP_HOME/bin/codex-pc" \
  "$APP_HOME/bin/codex-pc-monitor" \
  "$APP_HOME/bin/codex-pc-route" \
  "$APP_HOME/bin/codex-inventory" \
  "$APP_HOME/bin/codex-dashboard" \
  "$APP_HOME/bin/codex-registry" \
  "$APP_HOME/bin/codex-research" \
  "$APP_HOME/bin/codex-browser-safe" \
  "$APP_HOME/bin/codex-artifacts" \
  "$APP_HOME/bin/codex-scaffold" \
  "$APP_HOME/bin/codex-toolchain" \
  "$APP_HOME/bin/codex-pipeline" \
  "$APP_HOME/bin/codex-release" \
  "$APP_HOME/bin/codex-intent" \
  "$APP_HOME/bin/codex-ui-safe" \
  "$APP_HOME/bin/codex-device" \
  "$APP_HOME/bin/codex-trip" \
  "$APP_HOME/bin/codex-deploy" \
  "$APP_HOME/bin/codex-netdiag" \
  "$APP_HOME/bin/codex-secrets" \
  "$APP_HOME/bin/codex-security" \
  "$APP_HOME/bin/codex-command" \
  "$APP_HOME/bin/codex-files" \
  "$APP_HOME/bin/codex-device-io" \
  "$APP_HOME/bin/codex-care" \
  "$APP_HOME/bin/codex-resilience" \
  "$APP_HOME/bin/nemotron-runtime-capability" \
  "$APP_HOME/bin/nemotron_automation.py" \
  "$APP_HOME/bin/codex-install" \
  "$APP_HOME/bin/codex-package" \
  "$APP_HOME/bin/codex-gallery" \
  "$APP_HOME/bin/codex-pm" \
  "$APP_HOME/bin/codex-shizuku" \
  "$APP_HOME/bin/codex-uninstall" \
  "$APP_HOME/bin/codex-win" \
  "$APP_HOME/bin/codex-github" \
  "$APP_HOME/bin/powershell" <<'PY'
import pathlib
import sys

for source_name in sys.argv[1:]:
    source = pathlib.Path(source_name)
    compile(source.read_text(encoding="utf-8"), str(source), "exec")
PY

bash -n \
  "$APP_HOME/build-face-detector.sh" \
  "$APP_HOME/bin/codex-job" \
  "$APP_HOME/bin/codex-goal" \
  "$APP_HOME/bin/codex-recover" \
  "$APP_HOME/bin/codex-capability" \
  "$APP_HOME/bin/codex-artifact" \
  "$APP_HOME/bin/codex-verify" \
  "$APP_HOME/bin/codex-browser" \
  "$APP_HOME/bin/codex-ui" \
  "$APP_HOME/bin/codex-network" \
  "$APP_HOME/bin/codex-account" \
  "$APP_HOME/bin/codex-entitlement" \
  "$APP_HOME/bin/rish" \
  "$APP_HOME/bin/nemotron-runtime-rish" \
  "$APP_HOME/bin/pwsh" \
  "$APP_HOME/bin/rg" \
  "$APP_HOME/bin/ripgrep"
grep -Fq 'exec /data/data/com.termux/files/usr/bin/rg "$@"' "$APP_HOME/bin/rg"
if grep -Eq 'codexsubscription|codex-subscription|codexnvidia|nvidia-isolated' "$APP_HOME/bin/nemotron-runtime-rish"; then
  printf 'Protected sibling path leaked into the isolated runtime rish launcher.\n' >&2
  exit 2
fi

for command_name in aapt javac jar d8 zipalign apksigner; do
  command -v "$command_name" >/dev/null
done

set -a
. "$SIGNING_PROPERTIES"
set +a
umask 077
WORK_DIR=$(mktemp -d "$APP_HOME/build/.compile.XXXXXXXX")
FRONTEND_ASSET="$APP_HOME/vendor/codexapp-native-npm/node_modules/codexapp/dist/assets/index-BjdL8GKN.js"
FRONTEND_ASSET_NAME="index-BjdL8GKN.js"
FRONTEND_SERVED_ASSET="$FRONTEND_ASSET"
THREAD_ASSET="$APP_HOME/vendor/codexapp-native-npm/node_modules/codexapp/dist/assets/ThreadConversation-BjC7GMPc.js"
THREAD_ASSET_NAME="ThreadConversation-BjC7GMPc.js"
cmp -s "$FRONTEND_ASSET" "$FRONTEND_SERVED_ASSET"
grep -Fq 'src="/assets/index-BjdL8GKN.js"' \
  "$APP_HOME/vendor/codexapp-native-npm/node_modules/codexapp/dist/index.html"
for lazy_chunk in AutomationsPanel-CDzt9pHT.js DirectoryHub-DH7DfdjK.js \
  ReviewPane-cpiaeMip.js ThreadConversation-BjC7GMPc.js ThreadTerminalPanel-C5SwBPuk.js; do
  grep -Fq 'from"./index-BjdL8GKN.js"' \
    "$APP_HOME/vendor/codexapp-native-npm/node_modules/codexapp/dist/assets/$lazy_chunk"
done
cleanup() {
  case "$WORK_DIR" in
    "$APP_HOME"/build/.compile.*) find "$WORK_DIR" -depth -delete ;;
    *) printf 'Refusing unsafe build cleanup path: %s\n' "$WORK_DIR" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM

mkdir -p "$WORK_DIR/gen" "$WORK_DIR/classes" "$WORK_DIR/dex" "$WORK_DIR/apk-assets/runtime-contract"
cp "$APP_HOME/nemotron_unrestricted_proxy.py" \
  "$WORK_DIR/apk-assets/runtime-contract/nemotron_unrestricted_proxy.py"
cp "$APP_HOME/web/nemotron-autonomy-progress.js" \
  "$WORK_DIR/apk-assets/runtime-contract/nemotron-autonomy-progress.js"
cp "$FRONTEND_SERVED_ASSET" \
  "$WORK_DIR/apk-assets/runtime-contract/$FRONTEND_ASSET_NAME"
cp "$THREAD_ASSET" \
  "$WORK_DIR/apk-assets/runtime-contract/$THREAD_ASSET_NAME"
aapt package -f -m -J "$WORK_DIR/gen" -M "$APP_HOME/AndroidManifest.xml" -S "$APP_HOME/res" -I "$ANDROID_JAR"
find "$APP_HOME/src" "$WORK_DIR/gen" -type f -name '*.java' -print0 \
  | sort -z \
  | xargs -0 javac -source 8 -target 8 -classpath "$ANDROID_JAR" -d "$WORK_DIR/classes"
jar --create --file "$WORK_DIR/classes.jar" --date="$REPRODUCIBLE_ZIP_DATE" \
  -C "$WORK_DIR/classes" .
d8 --lib "$ANDROID_JAR" --min-api 23 --output "$WORK_DIR/dex" "$WORK_DIR/classes.jar"
aapt package -f -M "$APP_HOME/AndroidManifest.xml" -S "$APP_HOME/res" -A "$WORK_DIR/apk-assets" -I "$ANDROID_JAR" -F "$WORK_DIR/unsigned.apk"
jar --update --file "$WORK_DIR/unsigned.apk" --date="$REPRODUCIBLE_ZIP_DATE" \
  -C "$WORK_DIR/dex" classes.dex
zipalign -f 4 "$WORK_DIR/unsigned.apk" "$WORK_DIR/aligned.apk"
aapt package --debug-mode -f -M "$APP_HOME/AndroidManifest.xml" -S "$APP_HOME/res" -A "$WORK_DIR/apk-assets" -I "$ANDROID_JAR" -F "$WORK_DIR/unsigned-debug.apk"
jar --update --file "$WORK_DIR/unsigned-debug.apk" --date="$REPRODUCIBLE_ZIP_DATE" \
  -C "$WORK_DIR/dex" classes.dex
zipalign -f 4 "$WORK_DIR/unsigned-debug.apk" "$WORK_DIR/aligned-debug.apk"
apksigner sign \
  --ks "$KEYSTORE" \
  --ks-key-alias "$KEYSTORE_ALIAS" \
  --ks-pass env:KEYSTORE_PASSWORD \
  --key-pass env:KEYSTORE_PASSWORD \
  --v1-signing-enabled true \
  --v2-signing-enabled true \
  --v3-signing-enabled true \
  --v4-signing-enabled true \
  --out "$WORK_DIR/$ARTIFACT" \
  "$WORK_DIR/aligned.apk"
apksigner sign \
  --ks "$KEYSTORE" \
  --ks-key-alias "$KEYSTORE_ALIAS" \
  --ks-pass env:KEYSTORE_PASSWORD \
  --key-pass env:KEYSTORE_PASSWORD \
  --v1-signing-enabled true \
  --v2-signing-enabled true \
  --v3-signing-enabled true \
  --v4-signing-enabled true \
  --out "$WORK_DIR/$DEBUG_ARTIFACT" \
  "$WORK_DIR/aligned-debug.apk"

zipalign -c 4 "$WORK_DIR/$ARTIFACT"
apksigner verify --verbose --print-certs "$WORK_DIR/$ARTIFACT" >/dev/null
aapt dump badging "$WORK_DIR/$ARTIFACT" | grep -q "package: name='$EXPECTED_PACKAGE' versionCode='$VERSION_CODE' versionName='$VERSION_NAME'"
zipalign -c 4 "$WORK_DIR/$DEBUG_ARTIFACT"
apksigner verify --verbose --print-certs "$WORK_DIR/$DEBUG_ARTIFACT" >/dev/null
aapt dump badging "$WORK_DIR/$DEBUG_ARTIFACT" | grep -q "package: name='$EXPECTED_PACKAGE' versionCode='$VERSION_CODE' versionName='$VERSION_NAME'"
aapt dump badging "$WORK_DIR/$DEBUG_ARTIFACT" | grep -q '^application-debuggable'
python - "$WORK_DIR/$ARTIFACT" "$WORK_DIR/$DEBUG_ARTIFACT" "$FRONTEND_ASSET_NAME" "$THREAD_ASSET_NAME" <<'PY'
import sys
import zipfile

frontend_entry = f"assets/runtime-contract/{sys.argv[3]}"
thread_entry = f"assets/runtime-contract/{sys.argv[4]}"
required = {
    "assets/runtime-contract/nemotron_unrestricted_proxy.py": (
        b"nvidia/nemotron-3-ultra-550b-a55b",
        b"MAX_REASONING_BUDGET = 128_000",
        b'EXACT_NEMOTRON_UPSTREAM_PROVIDER = "Together"',
        b"OPENROUTER_USAGE_URL",
        b"EXACT_NEMOTRON_ENDPOINTS_URL",
        b"credential_limit_exhausted",
        b"exactProviderVerified",
    ),
    frontend_entry: (
        b'label:"Max"',
        b"function nemotronCleanupConverge",
        b"nemotron-autonomy:sessions-deleted",
        b"],G=()=>{",
    ),
    thread_entry: (
        b'role:"status","aria-live":"polite","aria-atomic":"true"',
        b'U.humanizeCommand(i)',
        b'<code class="hljs"',
    ),
    "assets/runtime-contract/nemotron-autonomy-progress.js": (
        b"Clean sessions and threads",
        b"Delete all sessions and threads now",
        b"effectiveModel",
        b"One click immediately backs up, deletes, and verifies",
    ),
}
for apk_name in sys.argv[1:3]:
    with zipfile.ZipFile(apk_name) as apk:
        for entry, tokens in required.items():
            payload = apk.read(entry)
            for token in tokens:
                if token not in payload:
                    raise SystemExit(f"Missing packaged runtime contract {token!r} in {apk_name}:{entry}")
PY
"$APP_HOME/scan-nemotron-secrets.py" --current-only --apk "$WORK_DIR/$ARTIFACT"
"$APP_HOME/scan-nemotron-secrets.py" --current-only --apk "$WORK_DIR/$DEBUG_ARTIFACT"
cp "$WORK_DIR/$ARTIFACT" "$OUTPUT"
if [ -f "$WORK_DIR/$ARTIFACT.idsig" ]; then
  cp "$WORK_DIR/$ARTIFACT.idsig" "$OUTPUT.idsig"
fi
cp "$WORK_DIR/$DEBUG_ARTIFACT" "$DEBUG_OUTPUT"
if [ -f "$WORK_DIR/$DEBUG_ARTIFACT.idsig" ]; then
  cp "$WORK_DIR/$DEBUG_ARTIFACT.idsig" "$DEBUG_OUTPUT.idsig"
fi
APK_SHA256=$(sha256sum "$OUTPUT" | awk '{print $1}')
DEBUG_APK_SHA256=$(sha256sum "$DEBUG_OUTPUT" | awk '{print $1}')
printf '%s  %s\n' "$APK_SHA256" "$ARTIFACT" > "$OUTPUT.sha256"
printf '%s  %s\n' "$DEBUG_APK_SHA256" "$DEBUG_ARTIFACT" > "$DEBUG_OUTPUT.sha256"
printf '%s  %s\n' "$APK_SHA256" "$OUTPUT"
printf '%s  %s\n' "$DEBUG_APK_SHA256" "$DEBUG_OUTPUT"
