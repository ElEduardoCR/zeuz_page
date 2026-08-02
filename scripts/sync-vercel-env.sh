#!/usr/bin/env bash
#
# Sube las variables de .env a Vercel.
#
# Lee los valores de tu archivo .env local y los empuja al proyecto con la
# CLI de Vercel, autenticada con tu propio login de navegador. No hace falta
# generar ni pegar ningun token en ningun lado: la sesion vive en tu maquina.
#
#   ./scripts/sync-vercel-env.sh                 # -> production
#   ./scripts/sync-vercel-env.sh preview         # -> preview
#   ./scripts/sync-vercel-env.sh production --dry-run
#
# El script NUNCA imprime los valores, solo los nombres y cuantos caracteres
# tiene cada uno, para que puedas verificar que subio lo correcto sin que la
# llave acabe en el scrollback de tu terminal.

set -euo pipefail

cd "$(dirname "$0")/.."

TARGET="${1:-production}"
DRY_RUN=""
for arg in "$@"; do
  [ "$arg" = "--dry-run" ] && DRY_RUN="1"
done

# Variables que la app espera. Las que esten vacias en .env se saltan, para
# que puedas correr esto varias veces conforme vayas consiguiendo llaves.
VARS=(
  DATABASE_URL
  STRIPE_SECRET_KEY
  STRIPE_PUBLISHABLE_KEY
  STRIPE_WEBHOOK_SECRET
  MP_ACCESS_TOKEN
  MP_PUBLIC_KEY
  MP_ENV
  ADMIN_PASSWORD
  NOTIFY_EMAIL
  NOTIFY_FROM
  RESEND_API_KEY
  PUBLIC_BASE_URL
  SUPPORT_EMAIL
  APP_STORE_URL
  FLASK_SECRET
  FLASK_DEBUG
)

# --- Comprobaciones previas -------------------------------------------------

if ! command -v vercel >/dev/null 2>&1; then
  echo "Falta la CLI de Vercel. Instalala con:"
  echo "  npm i -g vercel"
  exit 1
fi

if [ ! -f .env ]; then
  echo "No encuentro .env. Copia .env.example a .env y llenalo primero."
  exit 1
fi

if ! vercel whoami >/dev/null 2>&1; then
  echo "No hay sesion de Vercel. Abriendo el navegador para que entres..."
  vercel login
fi

if [ ! -f .vercel/project.json ]; then
  echo "Este directorio no esta ligado a un proyecto de Vercel."
  echo "Corriendo 'vercel link' (elige el proyecto zeuz_page)..."
  vercel link
fi

echo "Cuenta: $(vercel whoami)"
echo "Entorno destino: $TARGET"
[ -n "$DRY_RUN" ] && echo "MODO PRUEBA: no se sube nada."
echo

# --- Sincronizacion ---------------------------------------------------------

read_env_value() {
  # Toma la ultima definicion de la variable en .env y le quita comillas
  # envolventes si las trae.
  local name="$1"
  local line
  line="$(grep -E "^${name}=" .env | tail -n 1 || true)"
  [ -z "$line" ] && return 0
  local value="${line#*=}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

subidas=0
saltadas=0

for name in "${VARS[@]}"; do
  value="$(read_env_value "$name")"

  if [ -z "$value" ]; then
    printf '  · %-26s (vacia en .env, se salta)\n' "$name"
    saltadas=$((saltadas + 1))
    continue
  fi

  if [ -n "$DRY_RUN" ]; then
    printf '  → %-26s subiria %d caracteres\n' "$name" "${#value}"
    subidas=$((subidas + 1))
    continue
  fi

  # 'vercel env add' falla si la variable ya existe, asi que la quitamos
  # antes. El '|| true' cubre el caso de que todavia no estuviera.
  vercel env rm "$name" "$TARGET" --yes >/dev/null 2>&1 || true

  if printf '%s' "$value" | vercel env add "$name" "$TARGET" >/dev/null 2>&1; then
    printf '  ✓ %-26s %d caracteres\n' "$name" "${#value}"
    subidas=$((subidas + 1))
  else
    printf '  ✗ %-26s FALLO\n' "$name"
  fi
done

echo
echo "Listas: $subidas · Saltadas por vacias: $saltadas"

if [ -z "$DRY_RUN" ]; then
  echo
  echo "Las variables solo aplican a despliegues NUEVOS."
  echo "Vuelve a desplegar para que surtan efecto:"
  echo "  vercel --prod        (o haz push a main)"
fi
