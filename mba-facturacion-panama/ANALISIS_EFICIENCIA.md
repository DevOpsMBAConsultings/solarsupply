# Análisis de Eficiencia — mba-facturacion-panama (Odoo 18 CE)

**Alcance:** solo eficiencia (rendimiento, coste de I/O, escalabilidad, uso del ORM y de transacciones).
No se evalúa cumplimiento fiscal DGI, UX ni corrección funcional salvo cuando el diseño impacta el rendimiento.

**Base analizada:** 5.873 líneas Python / 1.369 XML en 7 módulos (`mba_pa_base`, `mba_pa_products`,
`mba_pa_edi`, `mba_pa_sale`, `mba_pa_pos`, `mba_pa_edi_hka`, `mba_pa_edi_digifact`),
contrastadas contra `odoo/addons/account`, `sale`, `point_of_sale` de Odoo 18.0 CE.

---

## 1. Veredicto ejecutivo

| Dimensión | Estado |
|---|---|
| Coste por documento (envío al PAC) | **Malo** — O(n) sobre `account_move` completo por cada factura |
| Integridad transaccional | **Malo** — `_cr.commit()` en el camino de escritura anula el rollback |
| Búsqueda de adjuntos | **Malo** — 9 `ILIKE '%...'` sobre `ir_attachment` donde el core ya expone el campo |
| Cálculo de impuestos | **Regular** — API legacy `compute_all()` en campo `store=True` |
| Modelo de datos (índices / constraints) | **Regular** — sin `_sql_constraints`, sin índice en el campo más filtrado |
| Concurrencia (numeración fiscal) | **Malo** — read-then-write sin bloqueo, race condition garantizada |
| Throughput en POS | **Crítico** — 3 llamadas HTTP síncronas + commit dentro del request de cobro |
| Modelado ORM básico (campos, `depends`, `filtered`) | **Bueno** |

El módulo funciona correctamente en volumen bajo (mono-usuario, decenas de facturas/mes). Los problemas
detectados son de **escalabilidad y concurrencia**: se degradan de forma no lineal con el histórico
acumulado y se rompen con más de un usuario facturando en paralelo.

---

## 2. Hallazgos críticos

### 2.1 `_pa_next_numero()` — escaneo completo de la tabla por cada factura

`mba_pa_edi/models/account_move.py:263-290`

```python
moves = self.sudo().search_read(domain, ['name'], order='id desc')   # ← sin limit
max_num = 0
for m in moves:
    digits = re.sub(r'\D', '', m['name'] or '')
    ...
```

Trae a memoria **todas** las facturas históricas de la compañía/diario que hayan tocado el PAC y calcula
el máximo en Python con una regex por fila.

Coste real:

| Facturas acumuladas | Filas materializadas | Regex ejecutadas |
|---|---|---|
| 1.000 | 1.000 | 1.000 |
| 50.000 | 50.000 | 50.000 |
| 500.000 | 500.000 | 500.000 |

El coste crece linealmente **para siempre**, y se paga en dos sitios calientes:
`ConfirmarEnviarWizard.default_get()` (cada apertura del wizard) y
`PosOrder._generate_pos_order_invoice()` (cada ticket del punto de venta).

Además el `domain` filtra por `l10n_pa_pac_status`, que **no tiene índice** — es un seq scan de
`account_move` con filtro en Python posterior.

**Cómo lo hace el core.** `odoo/addons/account/models/sequence_mixin.py:267` resuelve exactamente el
mismo problema en **una** consulta con `ORDER BY sequence_number DESC LIMIT 1`, apoyada en las columnas
almacenadas `sequence_prefix` / `sequence_number`:

```sql
SELECT name FROM account_move
WHERE ...
AND sequence_prefix = (SELECT sequence_prefix FROM account_move ... ORDER BY id DESC LIMIT 1)
ORDER BY sequence_number DESC
LIMIT 1
```

**Recomendación.** Reemplazar por SQL directo:

```python
self.env.cr.execute("""
    SELECT COALESCE(MAX(NULLIF(regexp_replace(name, '\\D', '', 'g'), '')::bigint), 0)
      FROM account_move
     WHERE company_id = %s AND journal_id = %s
       AND move_type IN ('out_invoice','out_refund')
       AND l10n_pa_pac_status IN ('sent','accepted','cancelled','error')
       AND name NOT IN ('/', '')
""", (self.company_id.id, self.journal_id.id))
return str((self.env.cr.fetchone()[0] or 0) + 1).zfill(10)
```

O, preferible, apoyarse en `sequence_mixin` y dejar que Odoo gestione el correlativo.

Impacto: de O(n) filas + O(n) regex a **una fila**, constante en el tiempo.

---

### 2.2 `_cr.commit()` dentro del envío al PAC — rompe la atomicidad y alarga los locks

`mba_pa_edi_hka/models/account_move.py:48, 61, 75, 87` y `mba_pa_edi_digifact/models/account_move.py:49, 104`

Hay hasta **4 commits** en un solo `action_l10n_pa_send_to_pac()`. Consecuencias medibles:

1. **Contradice la garantía documentada.** `confirmar_enviar_wizard.py:107-110` afirma:
   > *"Si falla → UserError → rollback → número libre, factura en borrador"*

   Falso. `move.write({'name': num})` ocurre en la línea 141, y el primer `_cr.commit()` del cliente PAC
   (línea 48) lo persiste. Si el PAC rechaza después, el número **ya está quemado** en base de datos y el
   rollback no lo devuelve. Esto es la causa raíz de huecos en la numeración fiscal.

2. **Coste transaccional.** Cada commit fuerza flush del ORM + fsync de WAL. Con 4 commits se paga 4 veces
   el coste de durabilidad de una sola factura, y se pierde el batching de escrituras del ORM.

3. **Ventana de locks ampliada.** Entre commits, la fila de `account_move` queda liberada y vuelta a
   bloquear, abriendo ventanas donde otra sesión puede tomar el mismo número (ver 2.3).

4. **Bloquea el cursor durante la latencia de red.** El `requests.post(..., timeout=30)` está dentro de la
   transacción. Peor: el flujo HKA hace **3 peticiones** (`/Enviar`, `/Descarga` pdf, `/Descarga` xml),
   cada una con timeout de 30 s → hasta **90 s** de transacción abierta con locks vivos sobre la factura,
   por documento.

**Cómo lo hace el core.** `account_move_send.py:610` expone `_can_commit()`, que devuelve `False` durante
tests y sólo permite commit en puntos controlados del flujo batch, no dentro del handler del web service.

**Recomendación.**
- Eliminar los `_cr.commit()`. Si se necesita persistir el payload aun tras un fallo, usar un cursor
  independiente: `with self.pool.cursor() as new_cr: ...` — así el log sobrevive sin comprometer la
  transacción principal.
- Mover las descargas de PDF/XML fuera del envío: no son parte de la certificación, se pueden diferir a
  `ir.cron` o al primer acceso (lazy). Esto recorta la transacción de ~90 s a ~30 s de golpe.

---

### 2.3 Numeración fiscal: race condition sin bloqueo

`mba_pa_edi/wizard/confirmar_enviar_wizard.py:123-141`

```python
existing = self.env['account.move'].search([...('name','=',num)], limit=1)   # lectura
if existing: raise UserError(...)
move.write({'name': num})                                                    # escritura
```

Patrón *check-then-act* sin `SELECT ... FOR UPDATE` ni constraint única. Dos cajeros que abran el wizard en
la misma ventana obtienen el mismo `num` de `_pa_next_numero()`, ambos pasan la comprobación, ambos
escriben. Con los commits de 2.2 en medio, uno de los dos queda persistido con número duplicado ante la
DGI.

Adicionalmente esta `search()` sin índice compuesto en `(journal_id, company_id, name)` cuesta un scan
por validación, y se ejecuta **dos veces** por factura (`_onchange_numero_df` + `action_enviar_factura`).

**Recomendación.**
- Añadir constraint única real:
  `('unique_dgi_number', 'unique(company_id, journal_id, name)', 'El número fiscal ya existe')`.
  Es la única defensa correcta contra concurrencia; el chequeo Python queda como mensaje amigable.
- Serializar la asignación con `SELECT ... FROM account_journal WHERE id=%s FOR UPDATE` sobre el diario
  antes de calcular el siguiente número.

---

### 2.4 POS: 3 llamadas HTTP síncronas dentro del cobro

`mba_pa_pos/models/pos_order.py:123-162`

El bucle por orden ejecuta, dentro del request del frontend POS:

```
_pa_next_numero()             → escaneo O(n) de account_move  (§2.1)
action_l10n_pa_send_to_pac()  → 3 × HTTP con timeout=30s + 4 × commit  (§2.2)
_post()                       → asientos contables
_apply_invoice_payments()     → conciliación
_generate_and_send()          → render PDF + envío de correo
```

En el peor caso el cajero espera **más de 90 segundos** con el cliente delante, y un timeout de red deja
la orden en estado inconsistente. Con 4 cajas concurrentes se saturan los workers de Odoo: cada una
retiene un worker durante toda la latencia del PAC.

Además `moves += new_move` dentro del bucle (línea 152) reconstruye el recordset en cada iteración — O(n²)
en el número de órdenes; menor, pero innecesario (acumular `ids` en lista y hacer un `browse` final).

**Recomendación.** Desacoplar. Emitir la factura en estado `sent` y certificar contra el PAC en `ir.cron`
(patrón `account.move.send` batch de Odoo 18 con `_call_web_service_before_invoice_pdf_render`, ver §3).
Si la normativa exige el CAFE en mostrador, al menos: reducir a **una** llamada (`/Enviar`), bajar el
timeout a 8-10 s, y diferir las descargas de PDF/XML.

---

### 2.5 `ILIKE '%_CAFE...'` — 9 búsquedas no indexables sobre `ir_attachment`

`mba_pa_edi_hka/models/account_move.py:220, 262, 308, 317, 362, 371`,
`account_move_send.py:21, 43`, `ir_actions_report.py:12`

```python
self.env['ir.attachment'].search([
    ('res_model','=','account.move'), ('res_id','=',move.id),
    ('name','ilike','%_CAFE.pdf'),
], limit=1)
```

Un patrón con comodín inicial **no puede usar índice B-tree**: PostgreSQL hace scan del subconjunto y
compara cada `name`. `ir_attachment` es de las tablas más grandes de una instalación madura (millones de
filas). Estas búsquedas se disparan en el render de cada PDF y en la apertura del wizard de correo.

**Lo más relevante:** *es innecesario*. El propio módulo crea el adjunto con
`res_field="invoice_pdf_report_file"` (`account_move.py:101`), es decir, ya lo está guardando exactamente
donde Odoo 18 lo espera. El core resuelve la misma búsqueda con un simple acceso a campo:

```python
# odoo/addons/account/models/account_move_send.py:246
def _get_invoice_extra_attachments(self, move):
    return move.invoice_pdf_report_id      # M2O calculado desde invoice_pdf_report_file
```

**Recomendación.** Sustituir las 9 búsquedas por `move.invoice_pdf_report_id`. Para el PDF anulado, añadir
un `Many2one` propio (`l10n_pa_cafe_anulado_attachment_id`) en vez de buscar por nombre. Coste: de scan a
lookup por PK.

Nota adicional en `ir_actions_report.py:12`: el override se ejecuta para **toda** llamada a
`_render_qweb_pdf`, incluida la impresión masiva, y sólo tiene efecto con `len(res_ids) == 1` — es decir,
paga el coste de la búsqueda también cuando no puede usarla.

---

## 3. Hallazgos de impacto medio

### 3.1 `compute_all()` en un campo `store=True` (sale.order)

`mba_pa_sale/models/sale_order.py:230-274`

```python
@api.depends("order_line.price_total", "order_line.price_subtotal", "order_line.tax_id", ...)
def _compute_dgi_totals(self):
    for order in self:
        for line in order.order_line:
            tax_res = taxes.compute_all(line.price_unit, ...)   # ← 1 llamada por línea
```

Dos problemas superpuestos:

1. **Granularidad.** `compute_all()` se invoca **por línea**. Un pedido de 40 líneas ejecuta 40 pasadas
   del motor de impuestos completo (resolución de jerarquías, repartition lines, redondeos).
2. **`store=True` + `depends` amplio.** El `depends` incluye `order_line.price_total`,
   `order_line.price_subtotal` y `order_line.tax_id`. Cualquier edición de cualquier línea dispara el
   recálculo completo del pedido y una escritura en 4 columnas. En importaciones masivas de pedidos esto
   multiplica el coste de forma notable.

**Cómo lo hace Odoo 18.** El core migró al motor de impuestos por lotes
(`odoo/addons/sale/models/sale_order.py:498`):

```python
base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
```

Una sola pasada para todas las líneas del pedido. `compute_all()` sigue existiendo en 18
(`account_tax.py:4177`) pero es una capa de compatibilidad que internamente construye base lines y las
convierte de vuelta (`# Convert to the 'old' compute_all api`, línea 4251) — se paga la conversión además
del cálculo.

**Recomendación.** Migrar a `_prepare_base_line_for_taxes_computation()` +
`_add_tax_details_in_base_lines()`. Y evaluar si estos totales necesitan ser `store=True`: son campos de
visualización para el vendedor; si no se filtra ni agrupa por ellos, `store=False` elimina las escrituras.

El mismo patrón aparece en `_fe_line_has_positive_tax()` (línea 290, un `compute_all` por línea en
`action_confirm`) y en `nuc_builder.py:817` (uno por línea al construir el XML). En el builder es aceptable
—es un one-shot por documento—; en `action_confirm` no, porque se ejecuta en confirmaciones masivas.

---

### 3.2 `search()` dentro de bucle en compute almacenado

`mba_pa_edi/models/account_move.py:154-209`

```python
def _compute_dgi_retention_auto(self):
    for move in self:
        ...
        ret = RetType.search([('code','=','1'), ('receptor_type','=','gobierno')], limit=1)
```

`dgi.retention.type` es un catálogo de una decena de filas, pero la búsqueda se repite **por cada move**.
En un recompute masivo (instalación del módulo, actualización de una posición fiscal que arrastra miles de
facturas en borrador) son N consultas para 3 valores fijos.

**Recomendación.** Precargar el catálogo fuera del bucle:

```python
ret_types = {(r.code, r.receptor_type): r
             for r in self.env['dgi.retention.type'].search([])}
for move in self: ...   # lookup en dict
```

El mismo patrón, más severo, en `res_partner.py:120-174`: `_dgi_payment_vals_from_payment_term()` hace
un `Method.search()` por cada rama del `if/elif` — 13 ramas, cada llamada emite una consulta. Debería ser
un dict `{code: id}` cacheado (`@tools.ormcache` o `_get_dgi_method_map()`).

---

### 3.3 Ausencia total de `_sql_constraints`

Grep en los 7 módulos: **cero** `_sql_constraints`. Las unicidades se implementan en Python:

```python
# mba_pa_products/models/dgi_unidad_medida.py:37
if self.search_count([("code","=",rec.code), ("id","!=",rec.id)]) > 0:
# mba_pa_edi/models/dgi_payment_method.py:30
if rec.code and self.search_count([("id","!=",rec.id), ("code","=",rec.code)]):
```

Un `search_count` por registro en el constrain, frente a un índice único que PostgreSQL evalúa en el
propio `INSERT`. Al cargar los CSV de catálogos DGI (`data/dgi.unidad.medida.csv`, corregimientos, CPBS)
esto es O(n²): cada fila cuenta contra todas las anteriores. Y no protege contra concurrencia.

**Recomendación.** Migrar a `_sql_constraints = [('code_uniq', 'unique(code)', '...')]` en
`dgi.unidad.medida`, `dgi.payment.method`, `dgi.document.type`, `dgi.retention.type`, y añadir la
constraint de numeración fiscal de §2.3.

---

### 3.4 Índices faltantes

Presentes y correctos: `l10n_pa_cufe`, códigos de catálogos, campos de `digifact.log`.

**Faltan** en los campos realmente usados en dominios de búsqueda:

| Campo | Modelo | Usado en |
|---|---|---|
| `l10n_pa_pac_status` | `account.move` | `_pa_next_numero()` (§2.1), filtros de vista |
| índice compuesto `(company_id, journal_id, name)` | `account.move` | validación de duplicados (§2.3) |
| `l10n_pa_is_dgi_validated` | `res.partner` | filtros y validaciones repetidas |

`l10n_pa_pac_status` es un selection de baja cardinalidad — el índice idóneo es **parcial**:

```sql
CREATE INDEX account_move_pa_pac_pending_idx ON account_move (company_id, journal_id)
WHERE l10n_pa_pac_status IN ('sent','error');
```

---

### 3.5 Constrain de impuestos sobre `product.template`

`mba_pa_products/models/product_template.py:_check_taxes_assigned`

```python
@api.constrains("taxes_id", "sale_ok", "dgi_charge_type")
def _check_taxes_assigned(self):
    for rec in self:
        ...
        if not rec.taxes_id or all(is_retention(tax) for tax in rec.taxes_id):
```

`is_retention()` accede a `tax.tax_group_id.name` dentro del `all()`. Con prefetch del ORM el coste está
acotado, pero la constrain se dispara en **toda** escritura que toque `taxes_id` o `sale_ok` — incluidas
las actualizaciones masivas de precios/catálogo y la asignación masiva de impuestos.

Más relevante: la detección de retención se hace por **substring del nombre** (`"retenc" in name`), lo que
obliga a materializar `name` y `tax_group_id.name` de cada impuesto. El módulo ya define un campo booleano
`dgi_is_retention` (se consulta con `getattr` en la línea 1 de la función) — **usarlo como único criterio**
elimina los accesos a `tax_group_id` y hace la comprobación indexable.

---

## 4. Lo que está bien resuelto

Para calibrar: el módulo no es de baja calidad. Estos puntos están por encima de la media de localizaciones:

- **Uso de `filtered()` y `mapped()`** en lugar de bucles con `search()` en la construcción de payloads
  (`hka_client.py:38`, `nuc_builder.py:680-693`). Correcto y idiomático.
- **`@api.depends` bien razonados.** El comentario en `account_move.py:158-163` explicando por qué se
  depende de `partner_id.l10n_pa_receptor_tipo` y no sólo de `partner_id` en un campo almacenado
  demuestra comprensión real de la invalidación de caché del ORM.
- **Cacheo de tokens con margen de expiración** (`res_company.py:32-46` HKA,
  `digifact_client.py:187-192`). Evita un round-trip de autenticación por documento. Bien hecho.
- **Timeouts explícitos en todas las llamadas HTTP.** Ningún `requests` sin `timeout=`. Es el error más
  común en conectores PAC y aquí está cubierto.
- **Separación por capas** (`base` → `products` → `edi` → conectores `hka`/`digifact`). Permite instalar
  sólo un PAC y mantiene los conectores intercambiables.
- **`_get_placeholder_mail_attachments_data(**kwargs)`** con reenvío de kwargs a `super()`
  (`account_move_send.py:31-38`) — defensa deliberada contra cambios de firma entre versiones menores.

---

## 5. Plan de remediación priorizado

| # | Acción | Archivo | Esfuerzo | Ganancia |
|---|---|---|---|---|
| 1 | Sustituir `_pa_next_numero()` por SQL `MAX()` con índice | `mba_pa_edi/models/account_move.py:263` | 1 h | O(n) → O(1); la mayor de todas |
| 2 | Eliminar los 6 `_cr.commit()`; cursor aparte si hace falta log | `*_hka`, `*_digifact/account_move.py` | 3 h | Restaura atomicidad; −4 fsync/factura |
| 3 | Reemplazar los 9 `ILIKE '%_CAFE...'` por `invoice_pdf_report_id` | `mba_pa_edi_hka/*` | 2 h | Elimina scans de `ir_attachment` |
| 4 | `_sql_constraints` unique `(company_id, journal_id, name)` + `FOR UPDATE` en el diario | `mba_pa_edi/models/account_move.py` | 2 h | Cierra la race condition de numeración |
| 5 | Diferir descargas PDF/XML del PAC a `ir.cron` | `mba_pa_edi_hka/models/account_move.py:89-128` | 4 h | Transacción de 90 s → 30 s |
| 6 | Índice parcial en `l10n_pa_pac_status` | migración SQL | 1 h | Habilita (1) |
| 7 | Desacoplar POS del PAC (certificación asíncrona) | `mba_pa_pos/models/pos_order.py:123` | 1-2 d | Elimina el bloqueo de caja |
| 8 | Migrar `compute_all()` → `_add_tax_details_in_base_lines()` | `mba_pa_sale/models/sale_order.py:230` | 4 h | N llamadas → 1 por pedido |
| 9 | Precargar catálogos DGI en dict (retención, métodos de pago) | `account_move.py:154`, `res_partner.py:120` | 2 h | Elimina N+1 en recomputes |
| 10 | `_sql_constraints` unique en catálogos DGI | `mba_pa_products`, `mba_pa_edi` | 1 h | Carga de CSV O(n²) → O(n) |

Los puntos 1-4 son de bajo riesgo y alto retorno: recomendable abordarlos como un único bloque antes de
cualquier despliegue con volumen o multiusuario.

---

## 6. Cómo medirlo

Para validar las mejoras, no basta con el cronómetro:

```bash
odoo-bin --log-level=debug_sql          # contar consultas por operación
```

```python
# medir el coste real de _pa_next_numero antes/después
from odoo.tools.profiler import Profiler
with Profiler(collectors=['sql', 'traces_async']):
    move._pa_next_numero()
```

En PostgreSQL, confirmar los planes:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT name FROM account_move
WHERE company_id=1 AND journal_id=2 AND l10n_pa_pac_status IN ('sent','accepted');
-- antes:   Seq Scan  (rows=N)
-- después: Index Scan using account_move_pa_pac_pending_idx
```

Prueba de concurrencia para §2.3: dos sesiones ejecutando `action_enviar_factura` simultáneamente sobre
facturas distintas del mismo diario. Sin la constraint única, ambas obtienen el mismo número.

---

## 7. Referencias al core de Odoo 18.0 CE

| Tema | Ruta | Línea |
|---|---|---|
| Correlativo en una consulta | `addons/account/models/sequence_mixin.py` | 267 |
| Motor de impuestos por lotes | `addons/sale/models/sale_order.py` | 498 |
| `compute_all` como capa legacy | `addons/account/models/account_tax.py` | 4177, 4251 |
| Adjunto PDF de factura | `addons/account/models/account_move_send.py` | 246 |
| Hook batch de web service | `addons/account/models/account_move_send.py` | 617 |
| Control de commits | `addons/account/models/account_move_send.py` | 610 |
| Generación de PDF por lotes de 80 | `addons/account/models/account_move_send.py` | 655 |
