"""Process-wide call_processing DI.

Importing this package loads config.ini and initialises resources. Import
``application_container`` from ``call_processing.di``, or ``ApplicationContainer``
from ``call_processing.di.application_container`` for a ``Provide`` marker only.
"""

from call_processing.di.application_container import create_container

application_container = create_container()

__all__ = ['application_container']
