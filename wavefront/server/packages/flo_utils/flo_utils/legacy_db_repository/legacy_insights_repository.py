from common_module.log.logger import logger
from flo_utils.legacy_db_repository.legacy_redshift import LegacyRedshiftDatastore
from flo_utils.legacy_db_repository.legacy_bigquery import LegacyBigQueryDatastore
from typing import List, Dict


class LegacyInsightsRepository:
    def __init__(self):
        pass

    def create_tables(self):
        pass

    def store(self, table_name: str, records: List[Dict], **kwargs):
        pass


class LegacyInsightsRedshiftRepository(LegacyInsightsRepository):
    def __init__(
        self,
        redshift_host: str,
        redshift_port: int,
        redshift_db: str,
        redshift_username: str,
        redshift_password: str,
    ):
        self.redshift = LegacyRedshiftDatastore(
            redshift_db=redshift_db,
            redshift_host=redshift_host,
            redshift_port=redshift_port,
            redshift_username=redshift_username,
            redshift_password=redshift_password,
        )

    def store(self, table_name: str, records: list[dict], **kwargs):
        logger.debug(f'Inserting insights count: {len(records)}')
        self.redshift.bulk_insert(table_name, records)

    def create_tables(self):
        self.redshift.create_tables()


class LegacyInsightsBigQueryRepository(LegacyInsightsRepository):
    def __init__(self, project_id, dataset_id):
        self.bigquery = LegacyBigQueryDatastore(
            project_id=project_id, dataset_id=dataset_id
        )

    def store(self, table_name: str, records: list[dict], **kwargs):
        logger.debug(f'Inserting insights count: {len(records)}')
        self.bigquery.bulk_insert(table_name, records)

    def create_tables(self):
        self.bigquery.create_tables()
