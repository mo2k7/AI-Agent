#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${AI_AGENT_RUNTIME_DIR:-$HOME/Library/Application Support/AIAgent}"
TLS_DIR="${RUNTIME_DIR}/tls"
CERT_PATH="${TLS_DIR}/server.crt"
KEY_PATH="${TLS_DIR}/server.key"
RENEW_WINDOW_SECONDS=$((30 * 24 * 60 * 60))
TAILSCALE_APP_BIN="/Applications/Tailscale.app/Contents/MacOS/Tailscale"

mkdir -p "${TLS_DIR}"
chmod 700 "${RUNTIME_DIR}" "${TLS_DIR}" 2>/dev/null || true

resolve_tailscale_cli() {
  if command -v tailscale >/dev/null 2>&1; then
    command -v tailscale
    return 0
  fi
  if [[ -x "${TAILSCALE_APP_BIN}" ]]; then
    printf '%s\n' "${TAILSCALE_APP_BIN}"
    return 0
  fi
  return 1
}

is_tailscale_ip() {
  local ip="${1:-}"
  [[ "${ip}" =~ ^100\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
  local second_octet="${BASH_REMATCH[1]}"
  (( second_octet >= 64 && second_octet <= 127 ))
}

collect_tailscale_ips() {
  local line cli_path
  cli_path="$(resolve_tailscale_cli || true)"
  if [[ -n "${cli_path}" ]]; then
    while IFS= read -r line; do
      line="${line%%/*}"
      if is_tailscale_ip "${line}"; then
        printf '%s\n' "${line}"
      fi
    done < <("${cli_path}" ip -4 2>/dev/null || true)
  fi

  while IFS= read -r line; do
    if is_tailscale_ip "${line}"; then
      printf '%s\n' "${line}"
    fi
  done < <(/sbin/ifconfig 2>/dev/null | awk '/inet / { print $2 }')
}

collect_tailscale_dns_names() {
  local line cli_path
  cli_path="$(resolve_tailscale_cli || true)"
  [[ -n "${cli_path}" ]] || return 0

  while IFS= read -r line; do
    line="${line%.}"
    [[ "${line}" == *.ts.net ]] || continue
    printf '%s\n' "${line}"
  done < <("${cli_path}" status --json 2>/dev/null | sed -nE 's/^[[:space:]]*"DNSName"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -n 1)
}

required_ip_sans() {
  printf '%s\n' "127.0.0.1"
  collect_tailscale_ips
}

required_dns_sans() {
  printf '%s\n' "localhost"
  collect_tailscale_dns_names
}

cert_is_fresh() {
  [[ -f "${CERT_PATH}" ]] || return 1
  openssl x509 -checkend "${RENEW_WINDOW_SECONDS}" -noout -in "${CERT_PATH}" >/dev/null 2>&1
}

cert_covers_required_sans() {
  [[ -f "${CERT_PATH}" ]] || return 1
  local san_text
  san_text="$(openssl x509 -in "${CERT_PATH}" -noout -ext subjectAltName 2>/dev/null || true)"
  [[ -n "${san_text}" ]] || return 1

  local dns_name
  while IFS= read -r dns_name; do
    [[ -n "${dns_name}" ]] || continue
    if ! grep -Fq "DNS:${dns_name}" <<<"${san_text}"; then
      return 1
    fi
  done < <(required_dns_sans | awk '!seen[$0]++')

  local ip
  while IFS= read -r ip; do
    [[ -n "${ip}" ]] || continue
    if ! grep -Fq "IP Address:${ip}" <<<"${san_text}"; then
      return 1
    fi
  done < <(required_ip_sans | awk '!seen[$0]++')
}

generate_cert() {
  local config_file
  config_file="$(mktemp)"
  trap 'rm -f "${config_file}" "${CERT_PATH}.tmp" "${KEY_PATH}.tmp"' RETURN

  {
    printf '%s\n' '[req]'
    printf '%s\n' 'prompt = no'
    printf '%s\n' 'distinguished_name = dn'
    printf '%s\n' 'x509_extensions = v3_req'
    printf '%s\n' 'default_md = sha256'
    printf '%s\n' ''
    printf '%s\n' '[dn]'
    printf '%s\n' 'CN = AIAgentBackend'
    printf '%s\n' ''
    printf '%s\n' '[v3_req]'
    printf '%s\n' 'basicConstraints = critical,CA:false'
    printf '%s\n' 'keyUsage = critical,digitalSignature,keyEncipherment'
    printf '%s\n' 'extendedKeyUsage = serverAuth'
    printf '%s\n' 'subjectKeyIdentifier = hash'
    printf '%s\n' 'authorityKeyIdentifier = keyid,issuer'
    printf '%s\n' 'subjectAltName = @alt_names'
    printf '%s\n' ''
    printf '%s\n' '[alt_names]'
    local dns_index=1
    local dns_name
    while IFS= read -r dns_name; do
      [[ -n "${dns_name}" ]] || continue
      printf 'DNS.%d = %s\n' "${dns_index}" "${dns_name}"
      dns_index=$((dns_index + 1))
    done < <(required_dns_sans | awk '!seen[$0]++')

    local ip_index=1
    local ip
    while IFS= read -r ip; do
      [[ -n "${ip}" ]] || continue
      printf 'IP.%d = %s\n' "${ip_index}" "${ip}"
      ip_index=$((ip_index + 1))
    done < <(required_ip_sans | awk '!seen[$0]++')
  } > "${config_file}"

  openssl req \
    -x509 \
    -newkey rsa:2048 \
    -sha256 \
    -days 825 \
    -nodes \
    -keyout "${KEY_PATH}.tmp" \
    -out "${CERT_PATH}.tmp" \
    -config "${config_file}" >/dev/null 2>&1

  mv "${KEY_PATH}.tmp" "${KEY_PATH}"
  mv "${CERT_PATH}.tmp" "${CERT_PATH}"
  chmod 600 "${KEY_PATH}" "${CERT_PATH}"
}

if ! cert_is_fresh || ! cert_covers_required_sans; then
  generate_cert
fi

printf 'TLS_CERT_PATH=%s\n' "${CERT_PATH}"
printf 'TLS_KEY_PATH=%s\n' "${KEY_PATH}"
