"""Process-wide inference_app DI.

Importing this package loads config.ini. Import ``application_container`` from
``inference_app.di``, or ``ApplicationContainer`` from
``inference_app.di.application_container`` for a ``Provide`` marker only.
"""

from inference_app.di.application_container import ApplicationContainer
from inference_app.di.application_container import create_container

application_container = create_container()

__all__ = ['ApplicationContainer', 'application_container']
