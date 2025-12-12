import yaml
import os
from datetime import datetime


class LegacyBaseDatabase:
    """Base class for database operations"""

    def __init__(self, cloud_provider: str, schema_file: str):
        self.cloud_provider = cloud_provider
        self.super_fields = []
        self._load_schema(schema_file)
        self._initialize_super_fields()

    def _load_schema(self, schema_file: str):
        """Load the schema from unified schema file"""
        yaml_path = schema_file
        if os.path.exists(yaml_path):
            with open(yaml_path) as f:
                self.schema = yaml.safe_load(f)
        else:
            raise FileNotFoundError(f'Schema file not found at {yaml_path}')

    def _initialize_super_fields(self):
        """Initialize super fields from schema"""
        if not self.schema or 'tables' not in self.schema:
            return

        try:
            table = self.schema['tables'][0]
            for field_name, field_info in table['fields'].items():
                if field_info['type'] == 'SUPER':
                    self.super_fields.append(field_name)
        except (IndexError, KeyError):
            pass

    def _custom_serializer(self, obj):
        """Helper method for JSON serialization"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return str(obj)

    def fix_metadata_keys(self, metadata):
        """Clean up metadata keys"""
        if metadata is None:
            return None
        if not isinstance(metadata, dict):
            raise ValueError('Input must be a dictionary')
        return {
            str(key).replace(' ', '_').lower(): value for key, value in metadata.items()
        }

    def create_tables(self):
        """Create tables in the database"""
        pass
