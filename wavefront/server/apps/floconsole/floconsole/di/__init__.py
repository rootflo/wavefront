"""Process-wide floconsole DI.

Importing this package loads config.ini and initialises resources. Import
``application_container`` from ``floconsole.di``, or ``ApplicationContainer``
from ``floconsole.di.application_container`` for a ``Provide`` marker only.
"""

from floconsole.di.application_container import create_container

application_container = create_container()

__all__ = ['application_container']
