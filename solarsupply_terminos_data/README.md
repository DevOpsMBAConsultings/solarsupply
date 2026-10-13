# Solar Supply - Datos de Términos y Condiciones (`solarsupply_terminos_data`)

Micro-módulo de datos del cliente Solar Supply. Depende de `mba_terminos_condiciones` (agnóstico).
Carga los datos de pago en la compañía y regenera los términos y condiciones al instalar/actualizar
(`noupdate="0"`: el repo es la fuente de verdad; las ediciones manuales en Ajustes se pisan en el siguiente `-u`).

Para cambiar una cuenta o un texto: editar `data/company_data.xml`, subir la versión del manifest,
commit, push y actualizar el módulo en el servidor del cliente.
