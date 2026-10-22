# Tablero de Issues — mba-facturacion-panama

Documento vivo. Se actualiza a mano conforme se decide, se ejecuta o se descarta cada punto.
No es un reporte cerrado — es un backlog de trabajo real.

**Cómo usarlo:** cambiar la columna **Estado** según avance. `Discutir` significa que antes de tocar
código hay una decisión de negocio o de alcance que solo Brooks puede tomar (prioridad, cliente
afectado, si aplica dado el PAC que use cada instalación, etc.).

**Estados posibles:** `Discutir` · `Aprobado` · `Diferido` · `En progreso` · `Hecho` · `Descartado`

---

## Listos para ejecutar ya (no tocan HKA, bajo riesgo)

| # | Módulo(s) | Descripción breve | Impacto | Discutir | Estado | Próximo paso |
|---|---|---|---|---|---|---|
| 1 | `mba_pa_edi` (security.xml), `mba_pa_sale` (sale_order_views.xml) | Los grupos de permisos del core (`group_digifact_user/manager/support`) llevan el nombre de un solo PAC aunque controlan acceso agnóstico. Se propaga a un `groups=` en `mba_pa_sale`. | Arquitectura / mantenibilidad | No | **Aprobado** | Confirmado por Brooks: hacerlo ya. Antes de tocar el XML, correr en la BD real el `SELECT` de `ir_model_data` para descartar referencias externas (Studio, otros módulos) no visibles en git. Renombrar vía `ir_model_data` (SQL), no editando el `id` del XML directo — evita que Odoo borre el grupo en el próximo `-u`. |

## Diferidos — mientras no haya trabajo activo de HKA

| # | Módulo(s) | Descripción breve | Impacto | Discutir | Estado | Próximo paso |
|---|---|---|---|---|---|---|
| 2 | `mba_pa_edi` (`account_move.py:263`) | `_pa_next_numero()` escanea sin límite todo el histórico de facturas y calcula el MAX en Python con regex por fila. Coste crece con el histórico; se paga en cada apertura del wizard y en cada ticket POS. | Rendimiento | No | Diferido | Reemplazar por `MAX()` en SQL directo, apoyado en `sequence_mixin` de Odoo si es viable. |
| 3 | `mba_pa_edi` (`account_move.py:282`) | El mismo regex de #2 no valida que `name` tenga formato de 10 dígitos puros. Un solo registro histórico con formato distinto (ej. importado, renombrado a mano) infla el MAX para siempre y contamina la numeración de todas las facturas futuras del diario. | Cumplimiento fiscal (correctness, no solo performance) | Sí — ¿hay ya algún `name` "raro" en el histórico de algún cliente? | Diferido | Auditar `account_move.name` de clientes en producción con `WHERE name !~ '^\d{10}$'` antes de decidir el fix. Se puede arreglar solo (regex anclado), independiente del fix de rendimiento de #2. |
| 4 | `mba_pa_edi_hka`, `mba_pa_edi_digifact` (`account_move.py`) | `_cr.commit()` dentro del envío al PAC (hasta 6 en total). Rompe la garantía de rollback documentada en el wizard: si el PAC rechaza después del primer commit, el número fiscal queda quemado en base de datos. | Cumplimiento fiscal + integridad transaccional | No | Diferido | Eliminar los commits intermedios; usar cursor aparte solo si se necesita persistir el log de un fallo. |
| 5 | `mba_pa_edi` (wizard) | Numeración fiscal: patrón check-then-act sin `SELECT FOR UPDATE` ni constraint única. Dos usuarios enviando en la misma ventana pueden obtener el mismo número. | Cumplimiento fiscal (duplicados ante DGI) | No | Diferido | Añadir `_sql_constraints` unique `(company_id, journal_id, name)`. |
| 6 | `mba_pa_pos` (`pos_order.py:123`) | El cobro en caja encadena: escaneo O(n) de #2 + hasta 3 llamadas HTTP síncronas al PAC + varios commits, todo dentro del request de cobro. Hasta ~90s de espera en el peor caso. | Rendimiento + UX del cajero | No | Diferido | Desacoplar certificación del cobro (cron / async) si el negocio lo permite. |
| 7 | `mba_pa_edi_hka` (`account_move.py`, `account_move_send.py`, `ir_actions_report.py`) | 9 búsquedas `ILIKE '%_CAFE...'` sobre `ir_attachment` para encontrar el PDF, cuando el adjunto ya se guarda en `res_field="invoice_pdf_report_file"` — el campo estándar `move.invoice_pdf_report_id` ya lo resuelve directo. | Rendimiento | No | Diferido | Sustituir las 9 búsquedas por acceso al campo. Cambio mecánico, bajo riesgo. |
| 8 | `mba_pa_sale` (`sale_order.py:230`) | `compute_all()` se llama por cada línea del pedido en un campo `store=True`; Odoo 18 migró al motor por lotes (`_add_tax_details_in_base_lines`). | Rendimiento | No | Diferido | Migrar al motor por lotes; evaluar si el campo necesita `store=True`. |
| 9 | `mba_pa_edi` (`account_move.py:154`), `mba_pa_edi` (`res_partner.py:120`) | `search()` de catálogos pequeños (tipos de retención, métodos de pago) repetido dentro de un bucle por factura/partner en vez de precargarse una vez. | Rendimiento | No | Diferido | Precargar en dict fuera del bucle. |
| 10 | Todo el repo | Cero `_sql_constraints` en los 7 módulos. Unicidades resueltas con `search_count` en el constrain (`dgi.unidad.medida`, `dgi.payment.method`, etc.) — no protege contra concurrencia y es O(n²) al cargar catálogos. | Rendimiento + integridad de datos | No | Diferido | Añadir `_sql_constraints` unique en catálogos DGI. |
| 11 | `mba_pa_edi` (`account_move.py`), `res_partner.py` | Falta índice en `l10n_pa_pac_status` (usado en dominios de búsqueda repetidos) y en `l10n_pa_is_dgi_validated`. | Rendimiento | No | Diferido | Índice parcial sobre `l10n_pa_pac_status`. |
| 12 | `mba_pa_products` (`product_template.py`) | La constrain de "producto debe tener impuesto no-retención" detecta retención por substring del nombre (`"retenc" in name`) en vez de usar el booleano dedicado `dgi_is_retention` que ya existe. | Rendimiento (accesos innecesarios a `tax_group_id`) | No | Diferido | Usar solo el booleano como criterio. |

## Requiere verificación empírica antes de decidir prioridad

| # | Módulo(s) | Descripción breve | Impacto | Discutir | Estado | Próximo paso |
|---|---|---|---|---|---|---|
| 13 | `mba_pa_edi_digifact` (`account_move.py`, `nuc_builder.py`) | Los campos `digifact_numero_df`, `digifact_codigo_seguridad` y `digifact_pto_fact_df` no los escribe ningún wizard/write en todo el repo. `nuc_builder.py:331-332` cae siempre al fallback fijo (`"0000000001"` / `"000000001"`) para toda factura posteada. Si esto es lo que corre en producción, cada factura Digifact llevaría el mismo NumeroDF y CodigoSeguridad — contradice la exigencia DGI de que el código de seguridad sea aleatorio y no repetible (Doc. NUC-XML v2.0.7, pág. 20). | Cumplimiento fiscal — potencialmente crítico | **Sí — confirmar si Digifact está realmente activo en algún cliente antes de priorizar** | Discutir | Revisar `digifact.log` / `l10n_pa_pac_response` de facturas reales en el cliente que use Digifact (si alguno lo usa hoy) para ver si el `NumeroDF`/`CodigoSeguridad` real varía entre facturas o si de verdad sale siempre igual. `validate_sync.py` ya muestra que `mba_pa_edi_digifact` aparece como no instalado en dos de los servidores listados — puede que hoy no esté en uso real en ningún cliente. |
| 14 | `mba_pa_edi_hka` (`hka_client.py:155,517`) | `tipoDocumento` enviado a HKA usa `invoice.dgi_document_type_id.code`, que vale strings tipo `"factura_operacion_interna"`, no el código numérico DGI (`"01"`). El mapeo numérico existe pero solo se usa en `name_get()` para las etiquetas del desplegable — nunca llega al payload. Toda factura con tipo de documento asignado manda un código inválido; solo "funciona" cuando el campo queda vacío y entra el fallback `"01"`. | Cumplimiento fiscal | Sí — confirmar si los clientes con HKA activo están asignando `dgi_document_type_id` manualmente o siempre queda vacío (lo que explicaría por qué no ha reventado en producción) | Discutir | Revisar en el cliente con HKA activo si el campo se usa. Si sí, es un fix urgente y aislado (mapear código antes de enviar). |
| 15 | `mba_pa_edi` (`dgi_document_type.py:34`) | `name_get()` — método eliminado en Odoo 18 (reemplazado por `_compute_display_name`). El dict de mapeo a código numérico DGI nunca se ejecuta; el desplegable nunca muestra "01 - Factura...". | Cosmético / UX, pero relacionado con #14 | No | Diferido | Migrar a `_compute_display_name`, y aprovechar para que el mismo mapeo alimente el payload real de HKA (fix de #14). |
| 16 | Infra / no es código del repo | Vista huérfana en `demo-motolider`: `loyalty_card_count` referenciado en una vista de `res.partner` con el módulo `loyalty` desinstalado (confirmado por captura: los 7 módulos de loyalty muestran "Activar"). Causa `OwlError` al abrir contactos para usuarios con acceso al botón. | Estabilidad del cliente demo | Sí — no es un bug de tu código, pero rompe la demo de ese cliente hoy | Discutir | Confirmar vía SQL si es residuo de un dump restaurado desde otra instancia; limpiar la vista huérfana o reinstalar/desinstalar `loyalty` limpiamente. |

---

## Historial de contexto (para no repetir la discusión)

- El módulo nació como una integración específica de Digifact (fue la entrada de MBA Consultings a
  este negocio) y se generalizó después a una arquitectura modular cuando llegó HKA. La lógica de
  negocio sí se generalizó bien (confirmado con grep exhaustivo: cero fugas funcionales de "digifact"/
  "hka" en los módulos agnósticos). Lo que quedó sin generalizar es nomenclatura técnica (#1) y el
  cableado del número fiscal en el conector Digifact (#13), probablemente porque `_pa_next_numero()`
  como pieza compartida se creó después de que el flujo de Digifact ya existía con su propio campo.
- Brooks: por ahora no hay trabajo activo en clientes con HKA — todo lo que toque `mba_pa_edi_hka`
  o el flujo compartido de numeración (#2, #3, #4, #5, #6, #14) queda diferido hasta que haya
  capacidad, salvo que surja una urgencia real en alguno de los dos clientes activos.
- De los dos clientes nuevos: uno usa HKA, el otro probablemente no activará facturación electrónica.
