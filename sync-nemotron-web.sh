#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE="$PROJECT_ROOT/web/nemotron-autonomy-progress.js"
DIST_ROOT="$PROJECT_ROOT/vendor/codexapp-native-npm/node_modules/codexapp/dist"
TARGET="$DIST_ROOT/nemotron-autonomy-progress.js"
INDEX="$DIST_ROOT/index.html"
HTML_PREMOUNT_OVERLAY_TAG='<script src="/nemotron-autonomy-progress.js'
NVIDIA_SCRIPT_TAG='<script src="/nvidia-autonomy-progress.js"></script>'
APP_TITLE='Nemotron Unrestricted'

test -f "$SOURCE"
test -d "$DIST_ROOT"
asset_staging=""
index_staging=""
cleanup() {
  for temporary in "$asset_staging" "$index_staging"; do
    [ -n "$temporary" ] || continue
    case "$temporary" in
      "$DIST_ROOT"/.nemotron-autonomy-progress.*|"$DIST_ROOT"/.nemotron-index.*)
        test ! -e "$temporary" || find "$temporary" -delete
        ;;
      *) printf 'Refusing unsafe web asset cleanup: %s\n' "$temporary" >&2 ;;
    esac
  done
}
trap cleanup EXIT INT TERM

if ! cmp -s "$SOURCE" "$TARGET"; then
  asset_staging=$(mktemp "$DIST_ROOT/.nemotron-autonomy-progress.XXXXXXXX")
  cp "$SOURCE" "$asset_staging"
  chmod 0644 "$asset_staging"
  mv "$asset_staging" "$TARGET"
fi

cmp -s "$SOURCE" "$TARGET"
if grep -Fq "$HTML_PREMOUNT_OVERLAY_TAG" "$INDEX" \
  || ! grep -Fq '<meta name="apple-mobile-web-app-title" content="Nemotron Unrestricted" />' "$INDEX" \
  || ! grep -Fq '<title>Nemotron Unrestricted</title>' "$INDEX" \
  || grep -Fq "$NVIDIA_SCRIPT_TAG" "$INDEX"; then
  index_staging=$(mktemp "$DIST_ROOT/.nemotron-index.XXXXXXXX")
  sed \
    -e 's#<meta name="apple-mobile-web-app-title" content="[^"]*" />#<meta name="apple-mobile-web-app-title" content="Nemotron Unrestricted" />#' \
    -e 's#<title>[^<]*</title>#<title>Nemotron Unrestricted</title>#' \
    -e '\#<script src="/nemotron-autonomy-progress.js#d' \
    -e '\#<script src="/nvidia-autonomy-progress.js"></script>#d' \
    "$INDEX" > "$index_staging"
  ! grep -Fq "$HTML_PREMOUNT_OVERLAY_TAG" "$index_staging"
  grep -Fq '<meta name="apple-mobile-web-app-title" content="Nemotron Unrestricted" />' "$index_staging"
  grep -Fq '<title>Nemotron Unrestricted</title>' "$index_staging"
  ! grep -Fq "$NVIDIA_SCRIPT_TAG" "$index_staging"
  chmod 0644 "$index_staging"
  mv "$index_staging" "$INDEX"
fi
! grep -Fq "$HTML_PREMOUNT_OVERLAY_TAG" "$INDEX"
grep -Fq '<meta name="apple-mobile-web-app-title" content="Nemotron Unrestricted" />' "$INDEX"
grep -Fq '<title>Nemotron Unrestricted</title>' "$INDEX"
! grep -Fq "$NVIDIA_SCRIPT_TAG" "$INDEX"
printf 'NEMOTRON_WEB_ASSET_SYNCED\n'
