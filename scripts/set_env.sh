#!/usr/bin/env bash
# .env'i guvenli doldurur: degerler ekrana yazilmaz, kabuk gecmisine dusmez.
# Bos birakilan alan mevcut degerini korur.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=".env"
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"

set_key() {
  local key="$1" label="$2" current="" input=""
  current="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [ -n "$current" ]; then
    printf '%s (mevcut: %s…%s) — degistirmek icin yeni degeri yapistir, atlamak icin Enter: ' \
      "$label" "${current:0:4}" "${current: -4}"
  else
    printf '%s — degeri yapistir (Enter ile atla): ' "$label"
  fi
  read -r -s input; echo
  [ -z "$input" ] && { echo "  → atlandi"; return; }
  input="$(printf '%s' "$input" | tr -d '[:space:]')"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    /usr/bin/sed -i '' "s|^${key}=.*|${key}=${input}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$input" >> "$ENV_FILE"
  fi
  echo "  → yazildi (${#input} karakter)"
}

echo "=== .env doldurma — girdiginiz degerler ekranda gorunmez ==="
set_key ANTHROPIC_API_KEY "1/3  Anthropic API key"
set_key PRODUCTHUNT_TOKEN "2/3  Product Hunt Developer Token"
set_key TWITTERAPI_KEY    "3/3  TwitterAPI.io key"
echo
echo "=== .env durumu ==="
while IFS='=' read -r k v; do
  case "$k" in ''|\#*) continue;; esac
  if [ -n "$v" ]; then echo "  $k: dolu (${#v} karakter, ${v:0:4}…${v: -4})"; else echo "  $k: BOS"; fi
done < "$ENV_FILE"
