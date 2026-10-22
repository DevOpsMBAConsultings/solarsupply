# 📊 VALIDACIÓN DE SINCRONIZACIÓN - mba-facturacion-panama

**Fecha de generación:** 2026-07-28  
**Rama:** main  
**Versión de Odoo:** 18.0

---

## 📦 VERSIONES EN CÓDIGO (GitHub - FUENTE DE VERDAD)

| Módulo | Versión | Dependencias | Estado |
|--------|---------|--------------|--------|
| **mba_pa_base** | `18.0.1.0.2` | base, contacts | ✅ Core |
| **mba_pa_edi** | `18.0.1.0.3` | account, sale, mba_pa_base, mba_pa_products | ✅ Core |
| **mba_pa_products** | `18.0.1.0.0` | mba_pa_base, product | ✅ Core |
| **mba_pa_sale** | `18.0.1.0.11` | sale, mba_pa_base, mba_pa_edi | ✅ Core + **DGI Warning** |
| mba_pa_edi_hka | `18.0.1.0.5` | mba_pa_edi, mba_pa_sale | ⚙️ PAC Optional |
| mba_pa_edi_digifact | `18.0.1.0.1` | (ver repo) | ⚙️ PAC Optional |
| mba_pa_pos | `18.0.1.0.3` | (ver repo) | ⚙️ Optional |

---

## 🔍 ESTADO DE SINCRONIZACIÓN POR SERVIDOR

### **odoo18demo.mbaconsultings.com**

| Módulo | Código | Servidor | Sync | Acción |
|--------|--------|----------|------|--------|
| mba_pa_base | 18.0.1.0.2 | 18.0.1.0.2 | ✅ | — |
| **mba_pa_edi** | **18.0.1.0.3** | **18.0.1.0.2** | ❌ | 🔴 **ACTUALIZAR** |
| mba_pa_products | 18.0.1.0.0 | 18.0.1.0.0 | ✅ | — |
| mba_pa_sale | 18.0.1.0.11 | 18.0.1.0.11 | ✅ | — |
| mba_pa_edi_hka | 18.0.1.0.5 | 18.0.1.0.5 | ✅ | — |

**⚠️ RIESGO:** Funcionalidad DGI parcial. El warning en cotizaciones funciona, pero mba_pa_edi podría tener bugs corregidos.

---

### **demo-simplificati.mbaconsultings.com**

| Módulo | Código | Servidor | Sync | Acción |
|--------|--------|----------|------|--------|
| mba_pa_base | 18.0.1.0.2 | 18.0.1.0.2 | ✅ | — |
| mba_pa_edi | 18.0.1.0.3 | 18.0.1.0.3 | ✅ | — |
| mba_pa_products | 18.0.1.0.0 | 18.0.1.0.0 | ✅ | — |
| mba_pa_sale | 18.0.1.0.11 | 18.0.1.0.11 | ✅ | — |
| mba_pa_edi_hka | 18.0.1.0.5 | 18.0.1.0.5 | ✅ | — |

**✅ ESTADO:** Todo sincronizado. Funcionalidad DGI completa.

---

## 🚨 RESUMEN EJECUTIVO

| Servidor | Estado | Acción Requerida |
|----------|--------|-----------------|
| **odoo18demo** | ⚠️ DESINCRONIZADO | Actualizar mba_pa_edi a 18.0.1.0.3 |
| **demo-simplificati** | ✅ SINCRONIZADO | Ninguna |

---

## 📋 CAMBIOS EN mba_pa_edi 18.0.1.0.3

**Commit:** `fix(edi): hide dgi fe tab on non-sale journals`  
**Fecha:** 2 días atrás  
**Cambios:**
- Oculta la pestaña "Factura Electrónica DGI" en diarios que no son de ventas
- Corrección de UI para evitar confusiones

**Impacto:** 🔴 Bajo riesgo, pero recomendado actualizar

---

## ✅ VALIDACIÓN DE FUNCIONALIDAD DGI WARNING

**Módulo responsable:** mba_pa_sale (18.0.1.0.11)  
**Estado en ambos servidores:** ✅ Instalado  
**Funcionalidad:** ✅ Operativa en ambos

- ✅ Warning amarillo al seleccionar cliente sin validación DGI
- ✅ Warning amarillo al crear factura con cliente sin validación DGI
- ✅ Wizard "partner_dgi_warning_wizard" activado en mba_pa_base

---

## 🔧 CÓMO ACTUALIZAR odoo18demo

```bash
# SSH al servidor
ssh user@odoo18demo.mbaconsultings.com

# Ir al directorio de módulos
cd /path/to/odoo/addons/mba-facturacion-panama

# Actualizar repositorio
git pull origin main

# Reiniciar Odoo
sudo systemctl restart odoo

# En Odoo UI: Apps > Actualizar lista > Buscar mba_pa_edi > Actualizar módulo
```

O directamente en Odoo UI:
1. Ir a **Apps > Actualizar lista de aplicaciones**
2. Buscar "mba_pa_edi"
3. Presionar **Actualizar**

---

## 📈 Script de Validación Automática

```python
# validate_sync.py
modules = {
    "mba_pa_base": "18.0.1.0.2",
    "mba_pa_edi": "18.0.1.0.3",
    "mba_pa_products": "18.0.1.0.0",
    "mba_pa_sale": "18.0.1.0.11",
    "mba_pa_edi_hka": "18.0.1.0.5",
}

# Comparar con servidor via Odoo API
for module, expected_version in modules.items():
    actual = get_module_version(module)
    if actual != expected_version:
        print(f"❌ {module}: esperado {expected_version}, actual {actual}")
    else:
        print(f"✅ {module}: {actual}")
```

---

**Última actualización:** 2026-07-28  
**Próxima revisión recomendada:** 2026-08-04
