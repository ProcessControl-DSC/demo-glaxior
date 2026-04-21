==================================
PoS Restrict Negative Stock
==================================

**Autor:** Process Control | https://www.processcontrol.es

Bloquea la venta en el Punto de Venta de productos almacenables cuya cantidad
disponible en el almacén de la configuración del PoS sea insuficiente para
cubrir el ticket, con bypass opcional mediante PIN de empleado autorizado.

Funcionalidades
===============

* Activación por PoS (``pos.config.restrict_negative_stock``).
* El control se calcula **solo sobre el almacén de la configuración del PoS**
  (``pos.config.warehouse_id``). Nunca considera stock de otros almacenes.
* Soporta los dos modos de actualización de stock:

  * **Tiempo real**: usa ``qty_available`` con contexto de warehouse.
  * **Al cierre de sesión**: descuenta las cantidades ya vendidas en
    órdenes pagadas, finalizadas o facturadas de **todas las sesiones abiertas**
    que operen sobre el mismo almacén, evitando la sobreventa entre cajeros.

* Bloqueo temprano al añadir una línea al ticket.
* Revalidación completa al pulsar *Pago*, incluyendo modificaciones
  posteriores del ticket.
* Bypass opcional mediante PIN:

  * ``pos.config.allow_negative_stock_override`` habilita la excepción.
  * ``pos.config.negative_stock_authorizer_ids`` indica los empleados
    autorizados a forzar la venta.
  * El PIN valida contra ``hr.employee.pin`` de esa lista.
  * El empleado que autoriza queda registrado en
    ``pos.order.negative_stock_authorizer_id``.

Configuración
=============

#. *Punto de venta > Configuración > Ajustes*.
#. Sección **Interfaz de PoS** → activar **Restrict Negative Stock**.
#. Opcionalmente activar **Allow bypass with authoriser PIN** y seleccionar
   los empleados autorizados.

Limitaciones
============

* El control se realiza por ``product.product``. Kits / BoM fantasma no se
  expanden en componentes (fuera de alcance v1).
* La modificación de cantidad mediante el numpad en una línea ya existente no
  dispara el control temprano; se validará en todo caso al pulsar *Pago*.
* En modo **real-time**, ventas locales aún no sincronizadas con el servidor
  pueden reflejarse con retraso. Si se requiere tolerancia cero, debe usarse
  modo **al cierre**.

Datos técnicos
==============

**Modelos extendidos:**

* ``pos.config`` - campos de activación y autorización, método RPC
  ``get_available_stock_for_pos`` y ``check_negative_stock_pin``.
* ``pos.order`` - campo ``negative_stock_authorizer_id``.
* ``pos.session`` - exposición de ``update_stock_at_closing`` al cliente.
* ``product.product`` - exposición de ``is_storable`` al cliente.
* ``res.config.settings`` - atajos related para la UI de ajustes.

Créditos
========

**Desarrollado por** `Process Control <https://www.processcontrol.es>`_
