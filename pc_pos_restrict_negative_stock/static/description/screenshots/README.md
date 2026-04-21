# Capturas pendientes

El `index.html` referencia las siguientes imágenes. Deben generarse desde el
build de Odoo.sh y guardarse en este mismo directorio con el nombre exacto.

Recomendado: **1200x750** aprox. (proporción 16:10), PNG optimizado.

| Archivo | Contenido esperado |
|---|---|
| `01_settings_activation.png` | Pantalla *Punto de Venta > Configuración > Ajustes*, con la PoS seleccionada y la casilla **Restrict Negative Stock** marcada dentro de la sección *Interfaz de PoS*. |
| `02_settings_authorizers.png` | Mismo ajuste, ampliado para mostrar el checkbox **Allow bypass with authoriser PIN** activo y la lista de empleados autorizadores añadidos (al menos 2 etiquetas visibles). |
| `03_pos_block_early.png` | Interfaz PoS con un producto almacenable sin stock añadido al ticket, mostrando el diálogo **"Not enough stock"** en modo bloqueante (sin bypass). |
| `04_pos_warning_line.png` | Interfaz PoS con bypass habilitado, mostrando el diálogo **"Stock warning"** (amarillo) con el texto sobre la próxima solicitud de PIN al pagar. |
| `05_pos_pin_dialog.png` | Interfaz PoS mostrando el diálogo **Authoriser PIN required** con el listado de productos afectados y el campo de PIN. |
| `06_order_authorizer.png` | Ficha del `pos.order` en backend con el campo **Negative Stock Authoriser** relleno con el empleado autorizador. |

## Cómo generarlas rápidamente

1. Abrir el build actual en Odoo.sh del proyecto `demo-glaxior`.
2. Instalar `pc_pos_restrict_negative_stock`.
3. Configurar una PoS con un almacén de prueba, dejar un producto con `qty_available = 0`.
4. Seguir los escenarios A–D del `index.html` e ir capturando en cada paso.
5. Recortar al área relevante y guardar con el nombre de la tabla.
