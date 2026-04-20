#!/usr/bin/env bash
# deploy.sh — Déploie le module ibatix_calcul_cee sur le serveur Odoo
# Usage : ./deploy.sh [install|upgrade]  (défaut : upgrade)
#
# IMPORTANT : n'utilise PAS XML-RPC pour la migration.
# La migration tourne via --stop-after-init directement dans le
# container Docker (synchrone, sans timeout HTTP).

set -e

ACTION="${1:-upgrade}"
MODULE="ibatix_calcul_cee"

source "$(dirname "$0")/../server.conf"
ADDON_PATH="${ADDONS_PATH}/${MODULE}"

echo "=== 1/3  Push vers GitHub ==="
git push -u origin main

echo "=== 2/3  Pull + nettoyage sur le serveur ==="
ssh "${SSH_TARGET}" "
  git config --global --add safe.directory ${ADDON_PATH} &&
  cd ${ADDON_PATH} && git pull origin main &&
  docker exec -u root ${DOCKER_CONTAINER} bash -c '
    find /opt/odoo/addons/${MODULE} -name \"*.pyc\" -delete 2>/dev/null || true
    find /opt/odoo/addons/${MODULE} -name \"__pycache__\" -type d -exec rm -rf {} + 2>/dev/null || true
    chown -R odoo:odoo /opt/odoo/addons/${MODULE}
  '
"

echo "=== 3/3  Migration (--stop-after-init) + redémarrage ==="
ssh "${SSH_TARGET}" "
  echo 'Lancement de la migration...' &&
  docker exec ${DOCKER_CONTAINER} python3 ${ODOO_BIN} \
    -c ${ODOO_CONF} \
    -d ${ODOO_DB} \
    -u ${MODULE} \
    --stop-after-init --no-http 2>&1 | grep -E '(ERROR|WARNING|Module|migration|Done|Modules)' || true &&
  echo 'Migration terminée. Redémarrage du container...' &&
  docker restart ${DOCKER_CONTAINER} &&
  echo 'Redémarrage OK.'
"

echo ""
echo "Déploiement de ${MODULE} terminé."
