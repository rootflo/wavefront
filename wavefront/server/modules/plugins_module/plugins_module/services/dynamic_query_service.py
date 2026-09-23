from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
import yaml
from common_module.log.logger import logger
from flo_cloud.cloud_storage import CloudStorageManager
from db_repo_module.models.dynamic_query_yaml import DynamicQueryYaml
from sqlalchemy import func, select
from typing import Optional


class DynamicQueryService:
    def __init__(
        self,
        cloud_storage_manager: CloudStorageManager,
        dynamic_query_repo: SQLAlchemyRepository[DynamicQueryYaml],
        bucket_name: Optional[str] = None,
    ):
        self.cloud_storage_manager = cloud_storage_manager
        self.dynamic_query_repo = dynamic_query_repo
        self.bucket_name = bucket_name
        self.prefix = 'dynamic_query/v1'

    async def store_yaml_to_bucket(self, yaml_content: dict, datasource_id: str):
        """Store YAML file to cloud storage and save metadata to database

        Args:
            yaml_content: The YAML content as a dictionary
            datasource_id: The ID of the datasource

        Raises:
            ValueError: If YAML file is invalid or missing required 'id' field
        """
        try:
            yaml_id = yaml_content.get('id', '')
            if not yaml_id:
                raise ValueError("YAML file must contain an 'id' field")

            # generating file key
            file_key = f'{self.prefix}/{yaml_id}.yaml'

            # Convert the dictionary to YAML string and then to bytes
            yaml_string = yaml.dump(yaml_content, default_flow_style=False)
            file_content = yaml_string.encode('utf-8')

            # storing to s3bucket
            self.cloud_storage_manager.save_small_file(
                file_content=file_content,
                bucket_name=self.bucket_name,
                key=file_key,
                disable_cache=True,
            )

            # strogin to db
            await self.dynamic_query_repo.upsert(
                filters={'name': yaml_id},
                datasource_id=datasource_id,
                file_path=file_key,
            )

        except ValueError as e:
            logger.error(f'Error uploading dynamic query YAML {yaml_id}: {str(e)}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error uploading dynamic query YAML {yaml_id}: {str(e)}'
            )
            raise ValueError(f'Failed to upload YAML file: {str(e)}')

    async def retrive_dynamic_query_yaml(
        self, datasource_id: str, limit: int = 50, offset: int = 0
    ):
        """Retrieve dynamic query YAML metadata for a datasource from the database

        Args:
            datasource_id: The ID of the datasource to filter queries by
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            dict: Contains yamls list, pagination info, and total count
        """
        async with self.dynamic_query_repo.session() as session:
            total_count = await session.scalar(
                select(func.count())
                .select_from(DynamicQueryYaml)
                .where(DynamicQueryYaml.datasource_id == datasource_id)
            )
            query = (
                select(DynamicQueryYaml)
                .where(DynamicQueryYaml.datasource_id == datasource_id)
                .order_by(DynamicQueryYaml.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            records = (await session.scalars(query)).all()

        yamls = []
        for record in records:
            splitter = record.file_path.split('/')
            if len(splitter) >= 3:
                yamls.append(
                    {
                        'version': splitter[1],
                        'file': splitter[2],
                        'full_path': record.file_path,
                    }
                )

        return {
            'yamls': yamls,
            'has_more': offset + len(yamls) < total_count,
            'limit': limit,
            'offset': offset,
            'total_count': total_count,
        }

    async def get_dynamic_yaml_query(self, datasource_id: str, query_id: str):
        """Get dynamic yaml query from cloud storage

        Args:
            datasource_id: The ID of the datasource the query must belong to
            query_id: The ID of the query

        Returns:
            dict: Contains yaml query and their parameters
        """
        query_record = await self.dynamic_query_repo.find_one(
            name=query_id, datasource_id=datasource_id
        )
        if not query_record:
            return None, None

        file_content = self.cloud_storage_manager.read_file(
            self.bucket_name, query_record.file_path
        )
        yaml_query = yaml.safe_load(file_content.decode('utf-8'))
        if not yaml_query:
            raise ValueError('YAML file is invalid')

        querys = []
        for query in yaml_query['queries']:
            query_data = {
                'id': query['id'],
                'query': query['query'],
            }
            if 'description' in query:
                query_data['description'] = query['description']
            # Add parameters only if they exist in the query
            if 'parameters' in query and query['parameters']:
                # Handle both list format (with name/type) and dict format
                if isinstance(query['parameters'], list):
                    query_data['parameters'] = query['parameters']
                else:
                    raise ValueError('Invalid parameters format')

            querys.append(query_data)

        return querys, yaml_query['name'] if 'name' in yaml_query else None

    async def delete_dynamic_query(self, datasource_id: str, query_id: str):
        """Delete dynamic query from cloud storage and database

        Args:
            datasource_id: The ID of the datasource
            query_id: The ID of the query
        """
        try:
            # cheking whether the given query id is present in the database
            query = await self.dynamic_query_repo.find_one(
                name=query_id, datasource_id=datasource_id
            )
            if not query:
                raise ValueError(f'Query {query_id} not found')

            # deleting the file from the cloud storage
            self.cloud_storage_manager.delete_file(self.bucket_name, query.file_path)
            # deleting the record from the database
            await self.dynamic_query_repo.delete_all(name=query_id)

        except Exception as e:
            logger.error(f'Error deleting dynamic query {query_id}: {str(e)}')
            raise
