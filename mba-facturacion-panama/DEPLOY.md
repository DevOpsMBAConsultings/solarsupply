# Deployment Guide — mba_l10n_panama

## Convención del servidor (aplica para cualquier versión)

| Parámetro | Versión 18 | Patrón general |
|-----------|-----------|----------------|
| Servicio | `odoo18` | `odoo{VERSION}` |
| Config | `/etc/odoo18.conf` | `/etc/odoo{VERSION}.conf` |
| Base de datos | `odoo18` | `odoo{VERSION}` |
| Python bin | `/opt/odoo/odoo18/venv/bin/python3` | `/opt/odoo/odoo{VERSION}/venv/bin/python3` |
| Odoo bin | `/opt/odoo/odoo18/odoo/odoo-bin` | `/opt/odoo/odoo{VERSION}/odoo/odoo-bin` |
| Addons | `/opt/odoo/custom-addons/mba_l10n_panama` | igual |

---

## Comandos de Deploy

### 1. Pull + Restart simple
> Usar cuando solo se modifican archivos Python o vistas XML **ya existentes**.
```bash
sudo bash -c 'cd /opt/odoo/custom-addons/mba_l10n_panama && git pull origin 18.0 && systemctl restart odoo18'
```

### 2. Pull + Upgrade de módulo + Restart
> **OBLIGATORIO** cuando se agregan nuevas vistas XML (`<record>`), nuevos campos o nuevos modelos.
```bash
sudo bash -c 'cd /opt/odoo/custom-addons/mba_l10n_panama && git pull origin 18.0' && \
sudo systemctl stop odoo18 && \
sudo -u odoo /opt/odoo/odoo18/venv/bin/python3 /opt/odoo/odoo18/odoo/odoo-bin \
  -c /etc/odoo18.conf -u mba_pa_edi -d odoo18 --stop-after-init && \
sudo systemctl start odoo18
```

### 3. Upgrade de múltiples módulos
```bash
sudo -u odoo /opt/odoo/odoo18/venv/bin/python3 /opt/odoo/odoo18/odoo/odoo-bin \
  -c /etc/odoo18.conf \
  -u mba_pa_edi,mba_pa_edi_hka,mba_pa_sale,mba_pa_base \
  -d odoo18 --stop-after-init && \
sudo systemctl restart odoo18
```

---

## Regla de oro

| Cambio | Comando |
|--------|---------|
| Solo `.py` | **1** — restart |
| Vista XML existente modificada | **1** — restart |
| Nueva `<record>` en XML | **2** — upgrade |
| Nuevo campo en modelo | **2** — upgrade |
| Nuevo modelo | **2** — upgrade |

---

## Módulos del Proyecto

| Módulo | Propósito |
|--------|-----------|
| `mba_pa_base` | Campos geográficos PA (Provincia, Distrito, Corregimiento) |
| `mba_pa_edi` | Lógica agnóstica de FE (campos DGI, wizard, validaciones) |
| `mba_pa_edi_hka` | Conector HKA (The Factory HKA) |
| `mba_pa_sale` | Integración cotizaciones → facturas FE |

---

## Repositorio
- **URL:** `https://github.com/DevOpsMBAConsultings/mba-facturacion-panama`
- **Branch:** `18.0`
