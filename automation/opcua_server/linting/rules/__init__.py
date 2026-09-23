"""Rule modules register themselves on import."""

from . import ap_1_full_scan
from . import ap_2_db_in_loop
from . import ap_3_subscription
from . import ap_4_setattr
from . import ap_5_unbounded_deque
from . import ap_7_sleep
from . import ap_8_io_in_hot_path
from . import ap_9_except_pass
from . import ap_10_access

__all__ = [
    "ap_1_full_scan",
    "ap_2_db_in_loop",
    "ap_3_subscription",
    "ap_4_setattr",
    "ap_5_unbounded_deque",
    "ap_7_sleep",
    "ap_8_io_in_hot_path",
    "ap_9_except_pass",
    "ap_10_access",
]
