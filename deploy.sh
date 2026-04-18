#!/usr/bin/env bash
# deploy.sh — Déploie le module ibatix_calcul_cee sur le serveur Odoo
# Usage : ./deploy.sh [install|upgrade]  (défaut : upgrade)

set -e

ACTION="${1:-upgrade}"
MODULE="ibatix_calcul_cee"

source "$(dirname "$0")/../server.conf"
ADDON_PATH="${ADDONS_PATH}/${MODULE}"

echo "=== 1/3  Push vers GitHub ==="
git push -u origin main

echo "=== 2/3  Pull sur le serveur ==="
ssh "${SSH_TARGET}" "
  git config --global --add safe.directory ${ADDON_PATH} &&
  cd ${ADDON_PATH} && git pull origin main &&
  docker exec -u root ${DOCKER_CONTAINER} bash -c '
    find /opt/odoo/addons/${MODULE} -name \"*.pyc\" -delete 2>/dev/null
    rm -rf /opt/odoo/addons/${MODULE}/__pycache__
    chown -R odoo:odoo /opt/odoo/addons/${MODULE}
  ' &&
  docker restart ${DOCKER_CONTAINER}
"

echo "=== 3/3  ${ACTION} du module ==="
python3 - <<PYEOF
import xmlrpc.client, ssl, sys, time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url  = "${ODOO_URL}"
db   = "${ODOO_DB}"
user = "${ODOO_USER}"
pwd  = "${ODOO_PASS}"

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", context=ctx)
for i in range(12):
    try:
        uid = common.authenticate(db, user, pwd, {})
        if uid: break
    except Exception:
        pass
    time.sleep(5)
else:
    print("Timeout : Odoo ne répond pas"); sys.exit(1)

models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", context=ctx)
mod_ids = models.execute_kw(db, uid, pwd,
    'ir.module.module', 'search', [[['name', '=', '${MODULE}']]])

if "${ACTION}" == "install":
    models.execute_kw(db, uid, pwd,
        'ir.module.module', 'button_immediate_install', [mod_ids])
    print("Module installé avec succès.")
else:
    models.execute_kw(db, uid, pwd,
        'ir.module.module', 'button_immediate_upgrade', [mod_ids])
    print("Module mis à jour avec succès.")
PYEOF

echo ""
echo "Déploiement terminé."
