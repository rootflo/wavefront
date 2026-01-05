from typing import Dict, Any, Optional, List
from uuid import UUID

from db_repo_module.models.authenticator import Authenticator
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from authenticator import AuthenticatorType
from authenticator.factory import get_authenticator_factory
from authenticator.types import AuthenticatorABC


async def get_authenticator_config(
    auth_id: UUID, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> Optional[Dict[str, Any]]:
    """Get authenticator configuration by ID."""
    authenticator = await authenticator_repository.find_one(
        auth_id=auth_id, is_deleted=False
    )

    if not authenticator:
        return None

    return {
        'auth_id': str(authenticator.auth_id),
        'auth_name': authenticator.auth_name,
        'auth_type': authenticator.auth_type,
        'auth_desc': authenticator.auth_desc,
        'config': authenticator.config,
        'is_enabled': authenticator.is_enabled,
        'created_at': authenticator.created_at.isoformat()
        if authenticator.created_at
        else None,
        'updated_at': authenticator.updated_at.isoformat()
        if authenticator.updated_at
        else None,
    }


async def validate_authenticator_type(
    auth_type: str, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> bool:
    """Validate if authenticator type is enabled."""
    enabled_auth = await authenticator_repository.find_one(
        auth_type=auth_type, is_enabled=True, is_deleted=False
    )
    return enabled_auth is not None


async def create_authenticator_config(
    auth_name: str,
    auth_type: str,
    auth_desc: Optional[str],
    config: Dict[str, Any],
    authenticator_repository: SQLAlchemyRepository[Authenticator],
) -> Dict[str, Any]:
    """Create new authenticator configuration."""

    # Validate auth_name has no spaces
    if ' ' in auth_name:
        raise ValueError('Authenticator name cannot contain spaces')

    # Validate configuration based on type
    auth_type_enum = AuthenticatorType(auth_type)
    factory = get_authenticator_factory()
    # Validate config without creating instance
    factory.validate_config(auth_type_enum, config)

    # Check if authenticator name already exists
    existing = await authenticator_repository.find_one(auth_name=auth_name)
    if existing and not existing.is_deleted:
        raise ValueError(f"Authenticator with name '{auth_name}' already exists")

    # Create or update authenticator
    if existing:
        # Reactivate deleted authenticator
        authenticator = await authenticator_repository.find_one_and_update(
            {'auth_name': auth_name},
            refresh=True,
            auth_type=auth_type,
            auth_desc=auth_desc,
            config=config,
            is_enabled=True,
            is_deleted=False,
        )
        # Add to factory with auth_id
        factory.get_authenticator(str(authenticator.auth_id), auth_type_enum, config)
    else:
        # Create new authenticator
        authenticator = await authenticator_repository.create(
            auth_name=auth_name,
            auth_type=auth_type,
            auth_desc=auth_desc,
            config=config,
            is_enabled=True,
        )
        # Add to factory with auth_id
        factory.get_authenticator(str(authenticator.auth_id), auth_type_enum, config)

    return {
        'auth_id': str(authenticator.auth_id),
        'auth_name': authenticator.auth_name,
        'auth_type': authenticator.auth_type,
        'auth_desc': authenticator.auth_desc,
        'config': authenticator.config,
        'is_enabled': authenticator.is_enabled,
        'created_at': authenticator.created_at.isoformat()
        if authenticator.created_at
        else None,
        'updated_at': authenticator.updated_at.isoformat()
        if authenticator.updated_at
        else None,
    }


async def update_authenticator_config(
    auth_id: UUID,
    config: Dict[str, Any],
    auth_desc: Optional[str] = None,
    authenticator_repository: SQLAlchemyRepository[Authenticator] = None,
) -> Optional[Dict[str, Any]]:
    """Update existing authenticator configuration."""

    authenticator = await authenticator_repository.find_one(
        auth_id=auth_id, is_deleted=False
    )

    if not authenticator:
        return None

    factory = get_authenticator_factory()
    auth_type_enum = AuthenticatorType(authenticator.auth_type)

    # Validate config without creating instance
    factory.validate_config(auth_type_enum, config)

    # Update authenticator
    update_data = {'config': config}
    if auth_desc is not None:
        update_data['auth_desc'] = auth_desc

    updated_authenticator = await authenticator_repository.find_one_and_update(
        {'auth_id': auth_id}, refresh=True, **update_data
    )

    # Update factory with auth_id
    factory.update_authenticator(str(auth_id), auth_type_enum, config)

    return {
        'auth_id': str(updated_authenticator.auth_id),
        'auth_name': updated_authenticator.auth_name,
        'auth_type': updated_authenticator.auth_type,
        'auth_desc': updated_authenticator.auth_desc,
        'config': updated_authenticator.config,
        'is_enabled': updated_authenticator.is_enabled,
        'created_at': updated_authenticator.created_at.isoformat()
        if updated_authenticator.created_at
        else None,
        'updated_at': updated_authenticator.updated_at.isoformat()
        if updated_authenticator.updated_at
        else None,
    }


async def delete_authenticator_config(
    auth_id: UUID, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> None:
    """Soft delete authenticator configuration."""

    authenticator = await authenticator_repository.find_one(
        auth_id=auth_id, is_deleted=False
    )

    if not authenticator:
        raise Exception('Authenticator not found. Might be deleted')

    # Remove from factory cache before deletion
    factory = get_authenticator_factory()
    auth_type_enum = AuthenticatorType(authenticator.auth_type)
    factory.remove_authenticator(str(auth_id), auth_type_enum)

    await authenticator_repository.find_one_and_update(
        {'auth_id': auth_id}, refresh=False, is_deleted=True
    )


async def test_authenticator_health(
    auth_id: UUID, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> Dict[str, Any]:
    """Test authenticator health and connectivity by auth_id."""

    # Get authenticator instance and config to distinguish not found vs disabled
    authenticator, config_data = await get_authenticator_with_config(
        auth_id, authenticator_repository
    )

    # Authenticator not found
    if config_data is None:
        return {
            'healthy': False,
            'message': f"Authenticator ID '{auth_id}' not found",
            'details': {},
        }

    # Authenticator exists but is disabled
    if authenticator is None:
        return {
            'healthy': False,
            'message': f"Authenticator ID '{auth_id}' is disabled",
            'details': {'is_enabled': False},
        }

    # Authenticator is enabled, check health
    health_result = authenticator.get_health_status()

    return {
        'healthy': health_result.healthy,
        'message': health_result.message,
        'last_check': health_result.last_check.isoformat()
        if health_result.last_check
        else None,
        'details': health_result.details or {},
    }


async def get_authenticator_instance(
    auth_id: UUID, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> Optional[AuthenticatorABC]:
    """
    Get authenticator instance by ID.

    Returns None if authenticator doesn't exist OR if it's disabled.
    Callers must check is_enabled separately if they need to distinguish
    between missing and disabled authenticators.
    """

    config_data = await get_authenticator_config(auth_id, authenticator_repository)
    if not config_data:
        return None

    # Return None if disabled (don't raise exception to keep function side-effect-free)
    if not config_data['is_enabled']:
        return None

    auth_type_enum = AuthenticatorType(config_data['auth_type'])
    factory = get_authenticator_factory()
    return factory.get_authenticator(
        str(auth_id), auth_type_enum, config_data['config']
    )


async def get_authenticator_with_config(
    auth_id: UUID, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> tuple[Optional[AuthenticatorABC], Optional[Dict[str, Any]]]:
    """
    Get authenticator instance and its configuration by ID.

    Returns:
        tuple: (authenticator_instance, config_data)
            - (None, None): Authenticator not found
            - (None, config_data): Authenticator exists but is disabled
            - (authenticator_instance, config_data): Authenticator is enabled and ready
    """

    config_data = await get_authenticator_config(auth_id, authenticator_repository)
    if not config_data:
        return None, None

    # If disabled, return config but no instance
    if not config_data['is_enabled']:
        return None, config_data

    auth_type_enum = AuthenticatorType(config_data['auth_type'])
    factory = get_authenticator_factory()
    authenticator = factory.get_authenticator(
        str(auth_id), auth_type_enum, config_data['config']
    )

    return authenticator, config_data


async def get_authenticator_instance_by_name(
    auth_name: str, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> Optional[AuthenticatorABC]:
    """Get authenticator instance by name."""

    authenticator = await authenticator_repository.find_one(
        auth_name=auth_name, is_deleted=False
    )

    if not authenticator:
        return None

    auth_type_enum = AuthenticatorType(authenticator.auth_type)
    factory = get_authenticator_factory()
    return factory.get_authenticator(
        str(authenticator.auth_id), auth_type_enum, authenticator.config
    )


async def get_all_authenticators(
    authenticator_repository: SQLAlchemyRepository[Authenticator],
) -> List[Dict[str, Any]]:
    """Get list of all authenticators."""
    authenticators = await authenticator_repository.find(is_deleted=False)

    return [
        {
            'auth_id': str(auth.auth_id),
            'auth_name': auth.auth_name,
            'auth_type': auth.auth_type,
            'auth_desc': auth.auth_desc,
            'is_enabled': auth.is_enabled,
            'created_at': auth.created_at.isoformat() if auth.created_at else None,
            'updated_at': auth.updated_at.isoformat() if auth.updated_at else None,
        }
        for auth in authenticators
    ]


async def enable_authenticator(
    auth_id: UUID, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> None:
    """Enable an authenticator."""
    authenticator = await authenticator_repository.find_one(
        auth_id=auth_id, is_deleted=False
    )
    if not authenticator:
        raise Exception('Authenticator not found. Might be deleted')

    if authenticator.is_enabled:
        raise Exception('Authenticator is already enabled')

    await authenticator_repository.find_one_and_update(
        {'auth_id': auth_id}, refresh=False, is_enabled=True
    )


async def disable_authenticator(
    auth_id: UUID, authenticator_repository: SQLAlchemyRepository[Authenticator]
) -> None:
    """Disable an authenticator."""
    authenticator = await authenticator_repository.find_one(
        auth_id=auth_id, is_deleted=False
    )
    if not authenticator:
        raise Exception('Authenticator not found. Might be deleted')

    if not authenticator.is_enabled:
        raise Exception('Authenticator is already disabled')

    # Check if there's at least one other enabled authenticator
    other_enabled_authenticators = await authenticator_repository.find(
        is_enabled=True, is_deleted=False
    )
    # Filter out the current authenticator from the list
    other_enabled_authenticators = [
        auth for auth in other_enabled_authenticators if auth.auth_id != auth_id
    ]

    if not other_enabled_authenticators:
        raise Exception(
            'Cannot disable authenticator. At least one authenticator must remain enabled'
        )

    await authenticator_repository.find_one_and_update(
        {'auth_id': auth_id}, refresh=False, is_enabled=False
    )
