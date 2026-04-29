============================================================
Selección automática de almacén y consolidación entre almacenes
============================================================

**Autor:** Process Control | https://www.processcontrol.es

Cuando un pedido de venta se confirma contra un almacén marcado como
*Almacén virtual agregador*, este módulo reasigna el pedido al almacén físico
hijo que mejor cubra la demanda, y dispara los movimientos entre almacenes
necesarios cuando ningún almacén físico por sí solo tiene stock suficiente.

Funcionalidades
===============

* Cálculo por pedido (no por línea) de qué almacén físico aporta más.
* **Caso A** — el mejor almacén cubre el 100% de la demanda: el pedido se
  reasigna a ese almacén y el flujo *Pick + Out* se genera de forma nativa.
* **Caso B** — ningún almacén cubre solo: el pedido se reasigna al que más
  aporta, su movimiento de salida se divide en una porción
  *make-to-stock* (lo que reserva del stock disponible) y otra
  *make-to-order* (lo que falta), y se lanzan aprovisionamientos desde los
  demás almacenes encadenados con la porción MTO mediante
  ``move_dest_ids``. El *Pick* al cliente queda en *waiting* hasta que
  todas las llegadas inter-almacén estén completadas.
* **Desempate determinista** por secuencia del almacén y, en último término,
  por ID.
* **Sin stock** en ningún almacén → el pedido se deja contra el almacén
  virtual con el modo ``no_stock`` registrado, para que el equipo funcional
  lo revise manualmente.

Configuración
=============

**Requisito previo**: tener los tres almacenes físicos funcionando en modo
*2 pasos de entrega* (``pick_ship``) y un almacén adicional configurado
como agregador virtual, con su ``Stock`` de tipo ``view`` y las ubicaciones
``Stock`` de los físicos reparentadas bajo él.

#. En *Inventario → Configuración → Ajustes*, activar **Storage Locations**
   y **Multi-Step Routes**.
#. En *Inventario → Configuración → Almacenes*, abrir el almacén agregador
   virtual, desplegar la sección **Virtual Aggregator** y marcar el
   checkbox *Virtual Aggregator Warehouse*.
#. En el mismo formulario, cumplimentar *Physical Child Warehouses* con los
   tres almacenes físicos hijos.
#. En cada almacén físico, desplegar *Resupply From* y marcar los otros dos
   almacenes físicos. Esto genera automáticamente las rutas de aprovisiona-
   miento entre almacenes que el módulo usa en el **Caso B**.

Uso
===

El comercial crea el pedido de venta como siempre, eligiendo el almacén
virtual en la pestaña *Otra información → Entrega → Almacén*. Al confirmar:

* Si un almacén físico cubre todas las unidades demandadas, el pedido se
  reasigna a ese almacén y se generan las transferencias *Pick* y *Out*
  estándar desde el mismo.
* Si ninguno cubre solo, el pedido se reasigna al que aporta más
  unidades, se generan los movimientos entre almacenes necesarios para
  traer el faltante, y el *Pick* del cliente queda en espera hasta que el
  stock consolidado esté disponible en el almacén ganador.

En todos los casos queda registrado en el pedido:

* **Warehouse Selection Mode** — ``case_a`` / ``case_b`` / ``no_stock``.
* **Requires Consolidation** — marcado cuando se han lanzado procurements
  entre almacenes.
* **Original Virtual Warehouse** — el almacén virtual original, para
  trazabilidad.

Además, un smart button **Consolidación** en el pedido lista las
transferencias inter-almacén asociadas (las que se ven también en
*Inventario → Operaciones → Transferencias* filtrando por documento de
origen).

Datos técnicos
==============

**Modelos extendidos:**

* ``stock.warehouse`` — campos ``is_virtual_warehouse`` y
  ``pc_child_warehouse_ids``.
* ``sale.order`` — campos ``pc_warehouse_selection_mode``,
  ``pc_requires_consolidation`` y ``pc_original_warehouse_id``; override de
  ``_action_confirm`` para ejecutar la lógica antes de la generación de
  *pickings*.

**Modelos nuevos:** ninguno.

Limitaciones conocidas
======================

* El algoritmo se ejecuta al confirmar el pedido y **no** se recalcula si el
  stock cambia antes de validar los pickings. Si se desea revaluar, cancelar
  y volver a confirmar el pedido.
* En **Caso B**, el *Pick* final queda en estado *waiting* hasta que las
  transferencias entre almacenes hayan llegado al almacén ganador.
* El cálculo sólo aplica a líneas con productos almacenables con demanda
  positiva. Servicios y productos tipo ``service`` se ignoran.

Créditos
========

**Desarrollado por** `Process Control <https://www.processcontrol.es>`_
