import asyncio
import json
import hashlib

from common_module.log.logger import logger
from common_module.utils.odata_parser import prepare_odata_filter
from db_repo_module.cache.cache_manager import CacheManager
from insights_module.models.dymanic_query import DynamicQuery
from insights_module.models.dymanic_query import Query
from insights_module.repository.pvo_repository import PVORepository


class DynamicQueryService:
    def __init__(
        self,
        pvo_repository: PVORepository,
        cache_manager: CacheManager,
    ):
        self.pvo_repository = pvo_repository
        self.cache_manager = cache_manager
        self.dynamic_query_map: dict[str, DynamicQuery] = dict()
        self.__load_dynamic_queries()

    def __load_dynamic_queries(self):
        all_dynamic_queries = self.pvo_repository.fetch_dynamic_queries()
        for dynamic_query in all_dynamic_queries:
            self.dynamic_query_map[dynamic_query.id] = dynamic_query

    def is_valid_query(self, query_id: str) -> bool:
        return query_id in self.dynamic_query_map

    async def execute_dynamic_query(
        self,
        query_id: str,
        filter: str | None = None,
        rls_filter_str: str | None = None,
        params: dict[str, str] | None = None,
        limit: str = None,
        offset: str = None,
        force: bool = False,
    ):
        query = self.dynamic_query_map[query_id]
        result_by_query = dict()

        logger.info(f'Executing dynamic query: {query_id}')

        # Create tasks for parallel execution
        tasks = []
        for query in query.queries:
            task = asyncio.create_task(
                self.__execute_single_query(
                    query,
                    filter,
                    rls_filter_str,
                    params,
                    limit=limit,
                    offset=offset,
                    force=force,
                )
            )
            tasks.append((query.id, task))

        # Wait for all tasks to complete
        for query_id, task in tasks:
            result_by_query[query_id] = await task

        return result_by_query

    def __generate_cache_key(
        self,
        query: Query,
        filter: str,
        rls_filter_str: str,
        params: dict,
        limit: str = None,
        offset: str = None,
    ) -> str:
        """Generate a unique cache key based on query parameters."""
        key_dict = {
            'query_id': query.id,
            'filter': filter,
            'rls_filter': rls_filter_str,
            'params': sorted(params.items()),
            'limit': limit,
            'offset': offset,
        }
        key_json = json.dumps(key_dict, sort_keys=True, separators=(',', ':'))
        hash_digest = hashlib.md5(key_json.encode()).hexdigest()
        return f'dynamic_query:{hash_digest}'

    async def __execute_single_query(
        self,
        query: Query,
        filter: str | None = None,
        rls_filter_str: str | None = None,
        params: dict[str, dict[str, str]] | None = None,
        limit: str = None,
        offset: str = None,
        force: bool = False,
    ) -> dict:
        try:
            params_to_execute = dict()
            odata_filter, odata_params = prepare_odata_filter(filter)
            odata_data_filter, odata_data_params = prepare_odata_filter(
                rls_filter_str, prefix='rls_'
            )
            incoming_param_value: dict[str, str] = params
            for qp in query.parameters:
                if qp.name not in incoming_param_value:
                    raise ValueError(
                        f'Missing parameter: {qp.name} for query {query.id}'
                    )
                params_to_execute[qp.name] = incoming_param_value[qp.name]

            # Generate cache key
            cache_key = self.__generate_cache_key(
                query, filter, rls_filter_str, params_to_execute, limit, offset
            )

            # Try to get from cache first
            cached_result = self.cache_manager.get_str(cache_key)
            if cached_result and not force:
                logger.info(f'Cache hit for query {query.id}')
                return {
                    'status': 'success',
                    'error': None,
                    'result': json.loads(cached_result),
                }

            logger.info(
                f'Executing query {query.id} with parameters: {params_to_execute}'
            )

            # TODO: If rls and filter have same columns mentioned, the behavior can be unpredictable.
            if odata_params:
                params_to_execute.update(odata_params)
            if odata_data_params:
                params_to_execute.update(odata_data_params)

            # Run the query in a thread pool since it's a blocking operation
            result = await asyncio.to_thread(
                self.pvo_repository.execute_dynamic_query,
                query.query,
                odata_filter,
                odata_data_filter,
                params_to_execute,
                limit=limit,
                offset=offset,
            )

            # Cache the result for 1 hour (3600 seconds)
            self.cache_manager.add(cache_key, json.dumps(result), expiry=60 * 2)

            return {
                'status': 'success',
                'error': None,
                'description': query.description,
                'result': result,
            }
        except Exception as e:
            logger.exception(e)
            logger.error(f'Error executing query {query.id}: {str(e)}')
            return {
                'status': 'error',
                'description': None,
                'error': 'Unexpected error while executing query',
                'result': [],
            }
