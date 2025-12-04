from dataclasses import dataclass
from typing import Dict, List

from common_module.log.logger import logger
from common_module.utils.odata_parser import fill_odata_query
from common_module.utils.odata_parser import prepare_odata_filter
from fastapi import HTTPException
import requests


@dataclass
class Resource:
    key: str
    value: str


def generate_rls_policy(
    filters: List[Resource], odata_query_filter: str
) -> Dict[str, str]:
    """
    Generate RLS policy from a list of filters.

    Automatically groups filters by unique keys to create appropriate
    OR/AND conditions.

    :param filters: List of Filter objects
    :return: RLS policy configuration
    """
    # Group filters by their keys
    if len(filters) == 0 and not odata_query_filter:
        return []
    filter_groups: dict[str, list[str]] = {}
    for filter_obj in filters:
        if filter_obj.key not in filter_groups:
            filter_groups[filter_obj.key] = []
        filter_groups[filter_obj.key].append(filter_obj.value)

    # Generate conditions
    conditions = []
    for key, values in filter_groups.items():
        # If multiple values for a key, use OR
        if len(values) > 1:
            or_condition = ' OR '.join([f"{key} = '{value}'" for value in values])
            conditions.append(f'({or_condition})')
        else:
            # Single value, use direct equality
            conditions.append(f"{key} = '{values[0]}'")

    if odata_query_filter:
        # If an OData filter is provided, parse it and add to conditions
        odata_condition, params = prepare_odata_filter(odata_query_filter)
        odata_query_condition = fill_odata_query(odata_condition, params)
        conditions.append(odata_query_condition)

    # Combine all conditions with AND
    full_condition = ' AND '.join(conditions)

    return [{'clause': full_condition}]


class SupersetService:
    def __init__(self, url, username, password, cache_manager):
        self.url = url
        self.username = username
        self.password = password
        self.cache_manager = cache_manager

    def generate_guest_token(
        self,
        user_id: str,
        dashboards: List[Resource],
        filters: List[Resource],
        query_filter: str,
    ):
        dashboard_ids = [dashboard.value for dashboard in dashboards]
        combined_keys = {':'.join(dashboard_ids)}
        cache_key = f'superset:{user_id}:{combined_keys}'
        cached_access_token = self.cache_manager.get_str(cache_key)

        logger.info('Fetching superset token from cache')
        if cached_access_token:
            access_token = cached_access_token
        else:
            login_body = {
                'password': self.password,
                'provider': 'db',
                'refresh': True,
                'username': self.username,
            }

            login_response = requests.post(
                f'{self.url}/api/v1/security/login', json=login_body
            )
            if login_response.status_code != 200:
                logger.error(f'error during superset login {login_response.text}')
                raise HTTPException(
                    status_code=login_response.status_code, detail='Login failed'
                )
            access_token = login_response.json().get('access_token')
            logger.info('Saving superset token into cache')
            self.cache_manager.add(cache_key, access_token, 900)

        resources = [{'type': 'dashboard', 'id': id} for id in dashboard_ids]
        rls_policy = generate_rls_policy(filters, query_filter)
        guest_token_body = {
            'resources': resources,
            'rls': rls_policy,
            'user': {
                'username': '',
                'first_name': '',
                'last_name': '',
            },
        }
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        guest_token_response = requests.post(
            f'{self.url}/api/v1/security/guest_token/',
            json=guest_token_body,
            headers=headers,
        )
        if guest_token_response.status_code != 200:
            logger.error(
                f'Error getting superset guest token {guest_token_response.text}'
            )
            raise HTTPException(
                status_code=guest_token_response.status_code,
                detail='Guest token generation failed',
            )
        guest_token = guest_token_response.json().get('token')
        return guest_token
