from . import models


def _post_init_hook(env):
    """When the module is installed (or upgraded), make sure the
    Deliver-in-2-steps routes of every physical warehouse that participates
    in a virtual aggregator follow the pull+pull MTO/MTS pattern. The Odoo 19
    default (pull Stock->Customer + push Output->Customer) defers the customer
    delivery picking until the warehouse pick is validated, which breaks the
    requirement of seeing the global pick AND the customer delivery as soon
    as the order is confirmed."""
    env['stock.warehouse']._pc_apply_2step_chain_pattern_all()
