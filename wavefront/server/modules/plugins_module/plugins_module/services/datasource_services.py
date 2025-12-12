import collections
from datasource import DataSourceType, BigQueryConfig, RedshiftConfig
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from auth_module.auth_container import AuthContainer
from plugins_module.plugins_container import PluginsContainer
from plugins_module.utils.helper import AddDatasourcePayload
from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID


async def get_datasource_config(
    datasource_id: str,
    datasource_repository: SQLAlchemyRepository[Datasource] = Depends(
        Provide(PluginsContainer.datasource_repository)
    ),
) -> tuple[DataSourceType, BigQueryConfig | RedshiftConfig]:
    datasource: Datasource | None = await datasource_repository.find_one(
        id=datasource_id
    )
    if not datasource:
        return None, None

    if datasource.type == DataSourceType.GCP_BIGQUERY:
        return DataSourceType.GCP_BIGQUERY, BigQueryConfig(**datasource.config)
    elif datasource.type == DataSourceType.AWS_REDSHIFT:
        return DataSourceType.AWS_REDSHIFT, RedshiftConfig(**datasource.config)
    else:
        raise ValueError(f'Invalid datasource type: {datasource.type}')


@inject
async def check_admin(
    role_id: str,
    role_repositroy: SQLAlchemyRepository[Role] = Depends(
        Provide(AuthContainer.role_repository)
    ),
) -> bool:
    if role_id == SERVICE_AUTH_ROLE_ID:
        return True
    role = await role_repositroy.find_one(id=role_id)
    if not role:
        return False
    return role.name == 'admin'


def check_is_valid_resource(resource_id: str) -> bool:
    if resource_id in [
        'parsed_data_object',
        'rf_parsed_data_object',
        'rf_gold_data_object',
        'rf_gold_item_details',
    ]:
        return True
    return False


def fetch_data_filters(data_filters: list) -> str:
    group_filter = collections.defaultdict(list)
    for data_filter in data_filters:
        group_filter[data_filter.key].append(data_filter.value)

    additional_filters = []
    for key, values in group_filter.items():
        if len(values) == 1:
            additional_filters.append(f"({key} eq '{values[0]}')")
        else:
            or_condition = []
            for value in values:
                or_condition.append(f"({key} eq '{value}')")
            additional_filters.append(f"{'$or'.join(or_condition)}")

    return additional_filters


def validate_datasource_payload(payload: AddDatasourcePayload) -> bool:
    if payload.type not in [
        datasource_type.value for datasource_type in DataSourceType
    ]:
        return False
    return True
