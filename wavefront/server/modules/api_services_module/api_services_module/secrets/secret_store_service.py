"""Named secrets that API service definitions reference as `${secrets.NAME}`."""

from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from common_module.log.logger import logger
from common_module.security.secret_cipher import SecretCipher
from db_repo_module.models.secret import Secret
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from sqlalchemy.exc import IntegrityError

from .references import SECRET_NAME_PATTERN

_MAX_NAME_LENGTH = 128
_MAX_DESCRIPTION_LENGTH = 255
_LIST_LIMIT = 1000


class SecretNotFound(LookupError):
    pass


class SecretStoreService:
    """CRUD on the `secrets` table. Values go in through `protect`, out through `reveal`.

    Every read except `resolve` returns metadata only.
    """

    def __init__(
        self,
        secret_repository: SQLAlchemyRepository[Secret],
        secret_cipher: SecretCipher,
    ):
        self._secrets = secret_repository
        self._cipher = secret_cipher

    @property
    def encryption_enabled(self) -> bool:
        return self._cipher.enabled

    async def create(
        self, name: str, value: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        _validate_name(name)
        _validate_value(value)
        _validate_description(description)

        if await self._secrets.find_one(name=name):
            raise ValueError(f'A secret named {name} already exists')

        try:
            secret = await self._secrets.create(
                name=name,
                description=description,
                value=await self._cipher.aprotect(value),
            )
        except IntegrityError:
            # Lost a race with a concurrent create of the same name.
            raise ValueError(f'A secret named {name} already exists')

        logger.info(f'Created secret {name}')
        return secret.to_dict()

    async def update(
        self,
        id: UUID,
        value: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rotate the value and/or change the description. `None` leaves a field as is."""
        secret = await self._require(id)

        updates: Dict[str, Any] = {}
        if value is not None:
            _validate_value(value)
            updates['value'] = await self._cipher.aprotect(value)
        if description is not None:
            _validate_description(description)
            updates['description'] = description
        if not updates:
            return secret.to_dict()

        updated = await self._secrets.find_one_and_update(
            filters={'id': secret.id}, refresh=True, **updates
        )
        if not updated:
            raise SecretNotFound(f'Secret not found: {id}')
        if 'value' in updates:
            logger.info(f'Rotated secret {updated.name}')
        return updated.to_dict()

    async def delete(self, id: UUID) -> Dict[str, Any]:
        secret = await self._require(id)
        await self._secrets.delete_all(id=secret.id)
        logger.info(f'Deleted secret {secret.name}')
        return secret.to_dict()

    async def list(self) -> List[Dict[str, Any]]:
        secrets = await self._secrets.find(limit=_LIST_LIMIT, order_by='name')
        return [secret.to_dict() for secret in secrets]

    async def get(self, id: UUID) -> Dict[str, Any]:
        return (await self._require(id)).to_dict()

    async def missing(self, names: Iterable[str]) -> List[str]:
        """Names from `names` that have no secret, sorted."""
        wanted = sorted(set(names))
        if not wanted:
            return []
        found = await self._secrets.find(name=wanted, limit=len(wanted))
        known = {secret.name for secret in found}
        return [name for name in wanted if name not in known]

    async def resolve(self, names: Iterable[str]) -> Dict[str, str]:
        """Plaintext of each named secret. Raises `ValueError` for an unknown name."""
        wanted = sorted(set(names))
        if not wanted:
            return {}
        found = await self._secrets.find(name=wanted, limit=len(wanted))
        values = {secret.name: secret.value for secret in found}
        unknown = [name for name in wanted if name not in values]
        if unknown:
            raise ValueError(f'Unknown secret: {", ".join(unknown)}')
        return {
            name: await self._cipher.areveal(value) for name, value in values.items()
        }

    async def _require(self, id: UUID) -> Secret:
        secret = await self._secrets.find_one(id=id)
        if not secret:
            raise SecretNotFound(f'Secret not found: {id}')
        return secret


def _validate_name(name: str) -> None:
    if not name or not SECRET_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            'Secret name must be upper snake case: a capital letter, then capital letters, digits or underscores'
        )
    if len(name) > _MAX_NAME_LENGTH:
        raise ValueError(f'Secret name must be at most {_MAX_NAME_LENGTH} characters')


def _validate_value(value: str) -> None:
    if not value:
        raise ValueError('Secret value must not be empty')


def _validate_description(description: Optional[str]) -> None:
    if description and len(description) > _MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            f'Description must be at most {_MAX_DESCRIPTION_LENGTH} characters'
        )
