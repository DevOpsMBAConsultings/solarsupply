# MBA Consultings - Facturación Electrónica Panamá (DGI)

Este repositorio contiene la suite de aplicaciones de localización para Panamá (DGI), enfocada en la facturación electrónica bajo el esquema de conectores PAC (The Factory HKA y Digifact).

## Arquitectura de Módulos

El proyecto está diseñado bajo una arquitectura modular (al estilo OCA), separando la lógica base, los modelos de productos, el flujo de ventas, y el motor de conectividad EDI para diferentes Proveedores de Autorización Calificados (PAC).

### Módulos Disponibles (Versión 18.0.1.0.0):

* **`mba_pa_base`**: Configuración base de la empresa, campos DGI en Contactos, y catálogos de Provincia, Distrito y Corregimiento.
* **`mba_pa_products`**: Atributos fiscales para productos y catálogos de Unidades de Medida y Segmentos CPBS.
* **`mba_pa_sale`**: Extensión de cotizaciones y ventas para incluir validaciones de retenciones y cálculos de ITBMS para la DGI.
* **`mba_pa_sale_hitos`**: Módulo opcional de soporte para gestión, auditoría y simulación interactiva de anticipos e hitos de facturación.
* **`mba_pa_edi`** *(Core)*: Motor principal agnóstico de Facturación Electrónica. Provee el flujo estandarizado, catálogos de métodos de pago y tipos de documento.
* **`mba_pa_edi_hka`**: Conector API REST/JSON específico para envío de documentos a The Factory HKA.
* **`mba_pa_edi_digifact`**: Conector XML específico para envío de documentos a Digifact.

### Lo que es común para todos los PACs

Gracias a esta arquitectura, **la experiencia del usuario y la estructura de datos es exactamente la misma** sin importar si la empresa contrata The Factory HKA, Digifact o cualquier otro PAC en el futuro. 
Lo que es común y centralizado en los módulos base y en el Core (`mba_pa_edi`) incluye:
* **Datos del Cliente y Empresa**: RUC, DV, Tipo de Contribuyente, Provincia, Distrito, Corregimiento.
* **Catálogos Oficiales de la DGI**: Unidades de medida, CPBS (Familias y Segmentos), Tipos de Documento (Factura, NC, ND, etc.) y Métodos de Pago.
* **Validaciones**: Obligatoriedad de impuestos (ITBMS), validaciones de clientes tipo gobierno.
* **Datos en la Factura**: Los campos donde se almacena el **CUFE**, la **URL del Código QR** y el Estatus de envío. Todo esto lo gestiona el Core, mientras que los submódulos de PAC (`_hka`, `_digifact`) actúan únicamente como un "puente de comunicación" invisible para el usuario.

## Instalación y Despliegue

1. Clona este repositorio en el directorio `addons` de tu instancia de Odoo 18.0.
2. Actualiza la lista de aplicaciones en Odoo (`Update Apps List`).
3. Instala el módulo conector correspondiente al PAC que deseas utilizar (Odoo instalará automáticamente todas las dependencias base):
   * **The Factory HKA**: Instala el módulo `mba_pa_edi_hka`.
   * **Digifact**: Instala el módulo `mba_pa_edi_digifact`.
4. Configura las credenciales del PAC en **Ajustes > Compañías**.

## Contribución y Mantenimiento

* Repositorio mantenido por [MBA Consultings](https://www.mbaconsultings.com).
* Sigue los estándares de código de Odoo (PEP8, Flake8).
