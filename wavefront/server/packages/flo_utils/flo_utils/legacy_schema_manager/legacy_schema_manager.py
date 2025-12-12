import json
import yaml
import os
from datetime import datetime
from typing import List


class TableNameConstants:
    GOLD_LOAN_DATA = 'rf_gold_data_object'
    GOLD_ITEM_DATA = 'rf_gold_item_details'


class LegacySchemaManager:
    """Base class for all schema managers"""

    def __init__(self, cloud_provider: str, schema_file: str):
        """Initialize base schema manager"""
        self.cloud_provider = cloud_provider
        self.super_fields = {}
        self.schema = self._load_schema(schema_file)
        self._initialize_super_fields()

    def _load_schema(self, schema_file: str):
        """Load the schema from unified schema file"""
        yaml_path = schema_file
        if os.path.exists(yaml_path):
            with open(yaml_path) as f:
                full_schema = yaml.safe_load(f)
            return full_schema
        raise ValueError(f'Schema file not found at {yaml_path}')

    def _initialize_super_fields(self):
        """Initialize super fields from schema, organized by table"""
        if (
            not hasattr(self, 'schema')
            or not self.schema
            or 'tables' not in self.schema
        ):
            return

        # Track super fields per table
        for table in self.schema['tables']:
            table_super_fields = []
            for field_name, field_info in table['fields'].items():
                field_type = field_info['type']
                if field_type == 'SUPER':
                    table_super_fields.append(field_name)
            self.super_fields[table['name']] = table_super_fields

    @staticmethod
    def fetch():
        """Factory method - should be implemented by subclasses"""
        raise NotImplementedError('Subclasses must implement fetch')

    def fetch_ddl_query(self, table_name: str, dataset_id: str = None) -> List[str]:
        """Generate DDL queries for table creation"""
        queries = []

        for table in self.schema['tables']:
            field_definitions = []
            for field_name, field_info in table['fields'].items():
                if self.is_aws:
                    nullable = 'NULL' if field_info['nullable'] else 'NOT NULL'
                    field_definitions.append(
                        f"{field_name} {field_info['type']} {nullable}"
                    )
                elif self.is_gcp:
                    nullable = '' if field_info['nullable'] else 'NOT NULL'
                    bq_type = self._convert_to_bigquery_type(field_info['type'])
                    field_definitions.append(f'{field_name} {bq_type} {nullable}')

            timestamp_type = 'TIMESTAMPTZ' if self.is_aws else 'TIMESTAMP'
            field_definitions = [
                *field_definitions,
                f'created_at {timestamp_type} NOT NULL',
            ]

            fields_sql = ',\n            '.join(field_definitions)

            if self.cloud_provider == 'aws':
                full_table_name = self.resolve_table_name(table_name, table['name'])
                query = f"""
                    CREATE TABLE IF NOT EXISTS {full_table_name} (
                        {fields_sql}
                    )
                    DISTSTYLE AUTO
                    SORTKEY AUTO;
                    """
            elif self.cloud_provider == 'gcp':
                full_table_name = (
                    f'{dataset_id}.{self.resolve_table_name(table_name, table["name"])}'
                )
                query = f"""
                    CREATE TABLE IF NOT EXISTS {full_table_name} (
                        {fields_sql}
                    )
                    """
            queries.append(query)
        return queries

    def _custom_serializer(self, obj):
        """Helper method for JSON serialization"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return str(obj)

    def populate_schema(
        self, core_table_schema: dict, table_name: str, record: dict, insights: dict
    ) -> dict:
        """Populate schema with entries"""
        table_super_fields = self.super_fields.get(table_name, [])
        for field in core_table_schema['fields']:
            value = insights.get(field, record.get(field))
            if value is not None:
                if field in table_super_fields:
                    value = json.dumps(value, default=self._custom_serializer)
                record[field] = value
            elif field not in record:
                record[field] = None
        return record

    def _prepare_values_placeholder(
        self, super_fields: list, column_name: str, is_gcp: bool = False
    ):
        """Prepare placeholder for field value in SQL"""
        if is_gcp:
            if column_name in super_fields:
                return f'JSON_EXTRACT_SCALAR(@{column_name})'
            return f'@{column_name}'
        else:
            if column_name in super_fields:
                return f'JSON_PARSE(:{column_name})'
            return f':{column_name}'

    def resolve_table_name(self, table_name: str, rf_internal_name: str):
        """Resolve full table name"""
        if table_name == '':
            return f'rf_{rf_internal_name}'
        return f'rf_{rf_internal_name}_{table_name}'

    def fix_metadata_keys(self, metadata):
        """Clean up metadata keys"""
        if metadata is None:
            return None
        if not isinstance(metadata, dict):
            raise ValueError('Input must be a dictionary')

        def transform_key(key):
            return str(key).replace(' ', '_').lower()

        meta = {transform_key(key): value for key, value in metadata.items()}
        return meta

    def _convert_to_bigquery_type(self, redshift_type: str) -> str:
        """Convert Redshift data types to equivalent BigQuery data types."""
        type_mapping = {
            # Numeric types
            'INTEGER': 'INT64',
            'INT': 'INT64',
            'SMALLINT': 'INT64',
            'BIGINT': 'INT64',
            'DECIMAL': 'NUMERIC',
            'NUMERIC': 'NUMERIC',
            'REAL': 'FLOAT64',
            'DOUBLE PRECISION': 'FLOAT64',
            'FLOAT': 'FLOAT64',
            # Character types
            'CHAR': 'STRING',
            'CHARACTER': 'STRING',
            'VARCHAR': 'STRING',
            'CHARACTER VARYING': 'STRING',
            'TEXT': 'STRING',
            # Date/Time types
            'DATE': 'DATE',
            'TIME': 'TIME',
            'TIMETZ': 'TIME',
            'TIMESTAMP': 'TIMESTAMP',
            'TIMESTAMPTZ': 'TIMESTAMP',
            # Boolean type
            'BOOLEAN': 'BOOL',
            'BOOL': 'BOOL',
            # JSON
            'SUPER': 'JSON',
        }

        # Handle types with precision/scale like DECIMAL(10,2)
        base_type = redshift_type.split('(')[0].upper()
        if base_type in type_mapping:
            if '(' in redshift_type and base_type in ['DECIMAL', 'NUMERIC']:
                # Keep the precision/scale for numeric types
                precision_scale = redshift_type[redshift_type.find('(') :]
                return f'{type_mapping[base_type]}{precision_scale}'
            return type_mapping[base_type]

        # Default to STRING for unsupported types
        return 'STRING'

    def fetch_gold_schema(self):
        return list(
            filter(
                lambda x: x['name'] == TableNameConstants.GOLD_LOAN_DATA,
                self.schema['tables'],
            )
        )[0], list(
            filter(
                lambda x: x['name'] == TableNameConstants.GOLD_ITEM_DATA,
                self.schema['tables'],
            )
        )[0]
