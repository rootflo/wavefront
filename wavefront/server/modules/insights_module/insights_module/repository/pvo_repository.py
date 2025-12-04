import os
from typing import Dict, List

from common_module.log.logger import logger
import dacite
from insights_module.db.redshift_connector import RedshiftConnector
from insights_module.models.dymanic_query import DynamicQuery
from insights_module.models.lead_signal_query import LeadQuery
from insights_module.models.insights_signal import serialize_values
import yaml

# Define default project paths
DEFAULT_PROJECT_PATH = 'apps/floware/floware'


class PVORepository:
    def __init__(
        self,
        redshift_connector: RedshiftConnector,
        dataset_id: str = None,
    ):
        self.dataset_id = dataset_id
        self.connector = redshift_connector
        self.project_path = os.getenv('PROJECT_PATH', DEFAULT_PROJECT_PATH)

    def __load_yaml_files(self, directory: str, data_class: type) -> List:
        """Load and parse YAML files from directory into list of data_class objects"""
        results = []
        for filename in os.listdir(directory):
            if filename.endswith(('.yaml', '.yml')):
                file_path = os.path.join(directory, filename)
                with open(file_path, 'r') as f:
                    yaml_data = yaml.safe_load(f)
                    if isinstance(yaml_data, list):
                        for item in yaml_data:
                            obj = dacite.from_dict(data_class=data_class, data=item)
                            results.append(obj)
                    else:
                        obj = dacite.from_dict(data_class=data_class, data=yaml_data)
                        results.append(obj)
        return results

    def __get_asset_directory(self, asset_type: str, env_var: str) -> str:
        """Get normalized directory path for asset files"""
        root_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
        )
        base_dir = os.path.join(root_dir, DEFAULT_PROJECT_PATH)
        directory_path = os.getenv(env_var, '')  # Provide empty string as default
        directory = os.path.join(base_dir, f'assets/{asset_type}', directory_path)
        return os.path.normpath(directory)

    def fetch_signal_from_yaml(self) -> List[LeadQuery]:
        directory = self.__get_asset_directory('leads', 'LEADS_DIR')
        return self.__load_yaml_files(directory, LeadQuery)

    def fetch_dynamic_queries(self) -> List[DynamicQuery]:
        directory = self.__get_asset_directory('dynamic_queries', 'DYNAMIC_QUERIES_DIR')
        return self.__load_yaml_files(directory, DynamicQuery)

    def fetch_pvo_record(
        self,
        odata_condition: str,
        params: Dict,
        limit: str | None = None,
        offset: str | None = None,
        table_name: str = 'rf_parsed_data_object',
    ) -> Dict[str, List]:
        table_name = self.__resolve_table_name(self.dataset_id, table_name=table_name)
        template_to_run = f'SELECT * FROM {table_name}'
        if odata_condition:
            template_to_run += f' WHERE {odata_condition}'

        template_to_run += ' ORDER BY start_time DESC'

        if limit:
            template_to_run += f' LIMIT {limit}'
        else:
            template_to_run += ' LIMIT 1'
        if offset:
            template_to_run += f' OFFSET {offset}'

        results, column_names = self.connector.execute_query(
            template_to_run, parameters=params
        )
        return self.__format_results_json(results, column_names)

    def update_pvo_record(
        self,
        id: str,
        update_data: Dict[str, str],
        table_name: str,
        odata_condition: str | None = None,
        rls_params: Dict[str, str] = {},
    ) -> None:
        odata_condition = odata_condition or 'TRUE'
        cloud_provider = os.environ.get('CLOUD_PROVIDER', 'aws')
        param_symbol = '@' if cloud_provider == 'gcp' else ':'
        table_name = self.__resolve_table_name(self.dataset_id, table_name=table_name)
        set_clause = ', '.join([f'{key} = @{key}' for key in update_data.keys()])
        query_to_run = f'UPDATE {table_name} SET {set_clause} WHERE id = {param_symbol}id AND {odata_condition}'
        params = {**update_data, 'id': id, **(rls_params if rls_params else {})}
        logger.info(f'Running query: {query_to_run} with params: {params}')
        self.connector.execute_query(query_to_run, parameters=params)

    def fetch_insights(
        self, query: str, projection: str, start_date: str, end_date: str
    ) -> Dict[str, List]:
        template_to_run = f'SELECT {projection} FROM ({query}) LIMIT 100'
        query_to_run = template_to_run.replace('{{start_date}}', start_date).replace(
            '{{end_date}}', end_date
        )
        logger.debug(f'Running query: {query_to_run}')
        results, column_names = self.connector.execute_query(query_to_run)

        return self.__format_results(results, column_names)

    def get_max_record_date(self) -> str | None:
        table_name = self.__resolve_table_name(self.dataset_id)
        query_to_run = f'SELECT MAX(start_time) as max_start_time FROM {table_name}'
        logger.debug(f'Running query: {query_to_run}')
        results, column_names = self.connector.execute_query(query_to_run)
        formatted_outputs = self.__format_results(results, column_names)
        max_date = None
        if (
            'max_start_time' in formatted_outputs
            and len(formatted_outputs['max_start_time']) > 0
        ):
            max_date = formatted_outputs['max_start_time'][0]
        return max_date

    def fetch_raw_values(
        self, query: str, projection: str, start_date: str, end_date: str
    ) -> Dict[str, List]:
        template_to_run = (
            f'SELECT start_date, {projection} FROM ({query}) GROUP BY start_date'
        )
        query_to_run = template_to_run.replace('{{start_date}}', start_date).replace(
            '{{end_date}}', end_date
        )
        logger.debug(f'Running query: {query_to_run}')
        results, column_names = self.connector.execute_query(query_to_run)

        return self.__format_results(results, column_names)

    def execute_query(
        self, query: str, start_date: str, end_date: str
    ) -> Dict[str, List]:
        query_to_run = query.replace('{{start_date}}', start_date).replace(
            '{{end_date}}', end_date
        )
        logger.debug(f'Running query: {query_to_run}')
        results, column_names = self.connector.execute_query(query_to_run)

        return self.__format_results(results, column_names)

    def execute_dynamic_query(
        self,
        query: str,
        odata_filters: str,
        odata_data_filter: str,
        params: dict | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> Dict[str, List]:
        logger.debug(f'Running query: {query}')

        query = query.replace(
            '{{rls}}', f'{odata_data_filter}' if odata_data_filter else 'TRUE'
        )
        query = query.replace(
            '{{filters}}', f'{odata_filters}' if odata_filters else 'TRUE'
        )
        if limit:
            query += f' LIMIT {limit}'
        if offset:
            query += f' OFFSET {offset}'

        results, column_names = self.connector.execute_query(query, parameters=params)

        return self.__format_results_json(results, column_names)

    def __format_results(self, results, column_names):
        if not results:
            return {col: [] for col in column_names}

        return {col: [row[i] for row in results] for i, col in enumerate(column_names)}

    def __format_results_json(self, results, column_names):
        if not results:
            return []

        json_data = []
        for res in results:
            result = {}
            for i, col in enumerate(column_names):
                result[col] = res[i]
            json_data.append(result)
        serialized_json = serialize_values(json_data)
        return serialized_json

    def __resolve_table_name(
        self, dataset_id: str = '', table_name='rf_parsed_data_object'
    ):
        full_table_name = table_name
        if dataset_id:
            full_table_name = f'{dataset_id}.{table_name}'

        return full_table_name

    def fetch_usage_metrics(self, start_time: str, end_time: str, cloud_provider: str):
        table_name = self.__resolve_table_name(self.dataset_id)
        dynamic_var_char = '@' if cloud_provider == 'gcp' else ':'
        query = f"""
        SELECT
            COUNT(DISTINCT CASE WHEN rf_transcription_status = 'success' THEN conversation_id END) AS transcription_success,
            COUNT(DISTINCT CASE WHEN rf_transcription_status = 'empty' THEN conversation_id END) AS transcription_empty,
            COUNT(DISTINCT CASE WHEN rf_insights_status = 'success' THEN conversation_id END) AS insights_success,
            COUNT(DISTINCT CASE WHEN rf_transcription_status = 'failure' OR rf_transcription_status IS NULL THEN conversation_id END) AS transcription_failure,
            COUNT(DISTINCT CASE WHEN rf_insights_status = 'failure' OR rf_insights_status IS NULL THEN conversation_id END) AS insights_failure,
            SUM(CASE WHEN rf_insights_status = 'success' THEN total_duration END) as total_call_duration
        FROM {table_name}
        WHERE created_at BETWEEN {dynamic_var_char}start_time AND {dynamic_var_char}end_time;
        """
        params = {'start_time': start_time, 'end_time': end_time}
        results, column_names = self.connector.execute_query(query, params)
        return self.__format_results(results, column_names)
