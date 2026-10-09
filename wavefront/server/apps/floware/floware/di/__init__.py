"""Process-wide floware DI.

Importing this package loads config.ini and initialises resources. Import
``application_container`` from ``floware.di``, or ``ApplicationContainer`` from
``floware.di.application_container`` for a ``Provide`` marker only.
"""

from floware.di.application_container import create_container

application_container = create_container()

__all__ = ['application_container']
