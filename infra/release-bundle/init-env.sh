#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ -e .env ]]; then
  echo 'Existing .env found. Keep its passwords and encryption secrets.' >&2
  exit 1
fi

umask 077
set -o noclobber
while IFS= read -r line || [[ -n "${line}" ]]; do
  case "${line}" in
    JWT_SECRET_KEY=*|AUTH_ENCRYPTION_SECRET=*|PLATFORM_ADMIN_PASSWORD=*|DEFAULT_USER_PASSWORD=*)
      value="$(openssl rand -base64 48)"
      printf '%s=%s\n' "${line%%=*}" "${value}"
      ;;
    POSTGRES_PASSWORD=*)
      value="$(openssl rand -hex 32)"
      printf 'POSTGRES_PASSWORD=%s\n' "${value}"
      ;;
    *) printf '%s\n' "${line}" ;;
  esac
done < .env.example > .env
echo 'Created .env. Read PLATFORM_ADMIN_PASSWORD there before signing in.'
