#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE="$APP_HOME/tools/NemotronFaceDetector.java"
ANDROID_JAR="$APP_HOME/build-tools/android.jar"
OUTPUT="$APP_HOME/runtime/.codex/tools/nemotron-face-detector.jar"

test -s "$SOURCE"
test -s "$ANDROID_JAR"
if [ -s "$OUTPUT" ] && [ "$OUTPUT" -nt "$SOURCE" ]; then
  printf '%s\n' "$OUTPUT"
  exit 0
fi

umask 077
WORK_DIR=$(mktemp -d "$APP_HOME/build/.face-detector.XXXXXXXX")
cleanup() {
  case "$WORK_DIR" in
    "$APP_HOME"/build/.face-detector.*) find "$WORK_DIR" -depth -delete ;;
    *) printf 'Refusing unsafe face-detector cleanup path: %s\n' "$WORK_DIR" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM
mkdir -p "$WORK_DIR/classes" "$WORK_DIR/dex" "$(dirname "$OUTPUT")"
javac -source 8 -target 8 -classpath "$ANDROID_JAR" -d "$WORK_DIR/classes" "$SOURCE"
jar cf "$WORK_DIR/classes.jar" -C "$WORK_DIR/classes" .
d8 --lib "$ANDROID_JAR" --min-api 23 --output "$WORK_DIR/dex" "$WORK_DIR/classes.jar"
jar cf "$WORK_DIR/nemotron-face-detector.jar" -C "$WORK_DIR/dex" classes.dex
mv "$WORK_DIR/nemotron-face-detector.jar" "$OUTPUT"
chmod 600 "$OUTPUT"
printf '%s\n' "$OUTPUT"
