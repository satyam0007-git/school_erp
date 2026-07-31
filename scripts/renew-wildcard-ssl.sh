#!/usr/bin/env bash
# Manually renew the Let's Encrypt wildcard certificate for Eduvault.
#
# Usage:
#   cd /home/ubuntu/school_erp
#   ./scripts/renew-wildcard-ssl.sh
#
# Certbot will print a temporary TXT value for _acme-challenge.eduvault.net.
# Add that value as an additional TXT record in Domain.com, wait until it has
# propagated, then return to this terminal and press Enter.  Do not delete
# existing TXT values while completing the validation.

set -Eeuo pipefail

readonly CERT_NAME='eduvault.net'
readonly ROOT_DOMAIN='eduvault.net'
readonly WILDCARD_DOMAIN='*.eduvault.net'

if [[ ${EUID} -eq 0 ]]; then
    SUDO=()
else
    SUDO=(sudo)
fi

echo 'Starting manual wildcard certificate renewal.'
echo 'When prompted, add the displayed TXT record in Domain.com and press Enter only after it is visible in DNS.'

"${SUDO[@]}" certbot certonly \
    --manual \
    --preferred-challenges dns \
    --manual-public-ip-logging-ok \
    --force-interactive \
    --force-renewal \
    --cert-name "$CERT_NAME" \
    -d "$ROOT_DOMAIN" \
    -d "$WILDCARD_DOMAIN"

"${SUDO[@]}" nginx -t
"${SUDO[@]}" systemctl reload nginx

echo
echo 'Certificate renewed and Nginx reloaded.'
"${SUDO[@]}" certbot certificates --cert-name "$CERT_NAME"
