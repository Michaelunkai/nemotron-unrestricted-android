#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
KEYSTORE="$APP_HOME/build/nemotron-unrestricted.keystore"
PROPERTIES="$APP_HOME/build/signing.properties"
ALIAS=nemotron-unrestricted

if [ -e "$KEYSTORE" ] || [ -e "$PROPERTIES" ]; then
  printf 'Refusing to overwrite existing signing material in %s/build\n' "$APP_HOME" >&2
  exit 77
fi

for command_name in keytool openssl; do command -v "$command_name" >/dev/null; done
umask 077
mkdir -p "$APP_HOME/build"
password=$(openssl rand -hex 24)
keytool -genkeypair -noprompt \
  -keystore "$KEYSTORE" \
  -storepass "$password" \
  -keypass "$password" \
  -alias "$ALIAS" \
  -keyalg RSA -keysize 3072 -validity 10000 \
  -dname 'CN=Nemotron Unrestricted Local Build,OU=Android,O=Local Developer,C=XX'
printf 'KEYSTORE_ALIAS=%s\nKEYSTORE_PASSWORD=%s\n' "$ALIAS" "$password" > "$PROPERTIES"
chmod 600 "$KEYSTORE" "$PROPERTIES"
unset password
printf 'Created private signing material at build/nemotron-unrestricted.keystore and build/signing.properties\n'
