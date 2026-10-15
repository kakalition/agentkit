"""The contract + driver substrate.

Wherever agentkit commits to one implementation, it exposes a **contract** (a
Protocol in :mod:`agentkit.contracts`), a **driver registry**
(:mod:`agentkit.support.drivers`), a **manager** resolving the settings-selected
driver (:mod:`agentkit.support.manager`), and an ``extend()`` hook. Existing
classes remain the *default drivers*; new behavior is opt-in.
"""

from agentkit.support.drivers import (
    DriverFactory,
    register,
    register_driver,
    resolve,
    unregister,
)
from agentkit.support.kinds import DriverKind
from agentkit.support.manager import Manager, manager_class, registered_managers

__all__ = [
    "DriverFactory",
    "DriverKind",
    "Manager",
    "manager_class",
    "register",
    "register_driver",
    "registered_managers",
    "resolve",
    "unregister",
]
