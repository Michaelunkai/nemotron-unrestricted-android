#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ANDROID_JAR="$APP_HOME/build-tools/android.jar"
KEYSTORE="$APP_HOME/build/nemotron-unrestricted.keystore"
SIGNING_PROPERTIES="$APP_HOME/build/signing.properties"
VERSION_CODE="1"
VERSION_NAME="1.0.0"
ARTIFACT="Nemotron-Unrestricted-$VERSION_NAME.apk"
OUTPUT="$APP_HOME/dist/$ARTIFACT"
EXPECTED_PACKAGE="com.michaelovsky.nemotronunrestricted.isolated"

"$APP_HOME/bootstrap-nemotron-runtime.sh"
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
cleanup() {
  case "$WORK_DIR" in
    "$APP_HOME"/build/.compile.*) find "$WORK_DIR" -depth -delete ;;
    *) printf 'Refusing unsafe build cleanup path: %s\n' "$WORK_DIR" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM

mkdir -p "$WORK_DIR/gen" "$WORK_DIR/classes" "$WORK_DIR/dex"
aapt package -f -m -J "$WORK_DIR/gen" -M "$APP_HOME/AndroidManifest.xml" -S "$APP_HOME/res" -I "$ANDROID_JAR"
find "$APP_HOME/src" "$WORK_DIR/gen" -type f -name '*.java' -print0 \
  | sort -z \
  | xargs -0 javac -source 8 -target 8 -classpath "$ANDROID_JAR" -d "$WORK_DIR/classes"
jar cf "$WORK_DIR/classes.jar" -C "$WORK_DIR/classes" .
d8 --lib "$ANDROID_JAR" --min-api 23 --output "$WORK_DIR/dex" "$WORK_DIR/classes.jar"
aapt package -f -M "$APP_HOME/AndroidManifest.xml" -S "$APP_HOME/res" -I "$ANDROID_JAR" -F "$WORK_DIR/unsigned.apk"
jar uf "$WORK_DIR/unsigned.apk" -C "$WORK_DIR/dex" classes.dex
zipalign -f 4 "$WORK_DIR/unsigned.apk" "$WORK_DIR/aligned.apk"
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

zipalign -c 4 "$WORK_DIR/$ARTIFACT"
apksigner verify --verbose --print-certs "$WORK_DIR/$ARTIFACT" >/dev/null
aapt dump badging "$WORK_DIR/$ARTIFACT" | grep -q "package: name='$EXPECTED_PACKAGE' versionCode='$VERSION_CODE' versionName='$VERSION_NAME'"
"$APP_HOME/scan-nemotron-secrets.py" --current-only --apk "$WORK_DIR/$ARTIFACT"
cp "$WORK_DIR/$ARTIFACT" "$OUTPUT"
if [ -f "$WORK_DIR/$ARTIFACT.idsig" ]; then
  cp "$WORK_DIR/$ARTIFACT.idsig" "$OUTPUT.idsig"
fi
APK_SHA256=$(sha256sum "$OUTPUT" | awk '{print $1}')
printf '%s  %s\n' "$APK_SHA256" "$ARTIFACT" > "$OUTPUT.sha256"
printf '%s  %s\n' "$APK_SHA256" "$OUTPUT"
