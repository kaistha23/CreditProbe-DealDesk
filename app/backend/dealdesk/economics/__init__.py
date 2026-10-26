"""R14 E: the one economics engine (RAROC/SVA with basis, EL/RWA/PD/LGD (i), RAROC bridge, reporting period).

    from backend.dealdesk.economics import economics, raroc_bridge, reporting_period, SVA_BASIS
"""
from backend.dealdesk.economics.core import (  # noqa: F401 - public API
    SVA_BASIS, covenant_headroom, economics, el_rwa, raroc_bridge, reporting_period)
