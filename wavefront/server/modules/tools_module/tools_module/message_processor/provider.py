from typing import List, Dict, Any
import yaml
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.message_processors import MessageProcessors
from tools_module.models.tool_schemas import ToolExecutionDetails
from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger


class MessageProcessorToolDetailsProvider(ToolDetailsProvider):
    """Provider for expanding message processor tools from database + YAML definitions"""

    def __init__(
        self,
        message_processor_repository: SQLAlchemyRepository[MessageProcessors],
        cloud_manager: CloudStorageManager,
        message_processor_bucket_name: str,
    ):
        self.message_processor_repository = message_processor_repository
        self.cloud_manager = cloud_manager
        self.message_processor_bucket_name = message_processor_bucket_name
        self.prefix = 'message_processors/v1'

    def can_handle(self, category: str) -> bool:
        return category == 'message_processor'

    async def get_tool_details(
        self, tool_metadata: Dict[str, Any]
    ) -> List[ToolExecutionDetails]:
        """
        Expand the trigger_message_processor template into individual tools.

        For each message processor in the database:
        1. Fetch the processor metadata
        2. Load YAML from cloud storage
        3. Parse input_schema to get parameters
        4. Create a ToolExecutionDetails with processor-specific params
        """
        tool_details = []

        # Fetch all message processors from database
        all_processors = await self.message_processor_repository.find()

        for processor in all_processors:
            try:
                # Load YAML content from cloud storage
                yaml_content = self._load_yaml_content(processor)

                # Parse YAML to extract schema
                yaml_dict = yaml.safe_load(yaml_content)

                # Validate YAML structure
                if not self._validate_yaml_structure(yaml_dict):
                    # Skip processors with invalid YAML
                    logger.warning(
                        f'Invalid YAML structure for message processor {processor.name}, skipping'
                    )
                    continue

                # Extract parameters from input_schema
                input_schema = yaml_dict.get('input_schema', {})
                parameters = self._convert_schema_to_parameters(input_schema)
                required = input_schema.get('required', [])

                # Use description from YAML if available, otherwise from processor
                description = yaml_dict.get(
                    'description', processor.description or 'Message processor function'
                )

                # Create tool details with processor-specific parameters
                tool_details.append(
                    ToolExecutionDetails(
                        name=processor.name,  # Each processor becomes its own tool
                        resource_name=processor.name,
                        prefill_parameter_names=['message_processor_id'],
                        prefilled_value={
                            'message_processor_id': str(processor.id),
                        },
                        required=required,
                        parameters=parameters,
                        description=description,
                        category='message_processor',
                    )
                )
            except Exception as e:
                # Log error but continue processing other processors
                logger.warning(
                    f'Error loading message processor {processor.name}: {str(e)}, skipping'
                )
                continue

        return tool_details

    def _load_yaml_content(self, processor: MessageProcessors) -> str:
        """Load YAML content from cloud storage"""
        filepath = f'{self.prefix}/{processor.source}'
        yaml_bytes = self.cloud_manager.read_file(
            self.message_processor_bucket_name, filepath
        )
        return yaml_bytes.decode('utf-8')

    def _validate_yaml_structure(self, yaml_dict: Dict[str, Any]) -> bool:
        """Validate that YAML has required fields for tool definition"""
        required_fields = ['function', 'input_schema', 'type']
        if not all(field in yaml_dict for field in required_fields):
            return False

        input_schema = yaml_dict.get('input_schema', {})
        if 'properties' not in input_schema:
            return False

        return True

    def _convert_schema_to_parameters(
        self, input_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert YAML input_schema to tool parameters format.

        YAML format:
          properties:
            number:
              type: number
              description: The number to process

        Tool format:
          {
            "number": {
              "type": "number",
              "description": "The number to process"
            }
          }
        """
        properties = input_schema.get('properties', {})

        # Add message_processor_id to parameters (it's prefilled)
        parameters = {
            'message_processor_id': {
                'type': 'string',
                'description': 'UUID of the message processor (automatically filled)',
            }
        }

        # Add all properties from YAML input_schema
        for param_name, param_spec in properties.items():
            parameters[param_name] = {
                'type': param_spec.get('type', 'string'),
                'description': param_spec.get('description', ''),
            }

            # Handle additional schema properties if needed
            if 'items' in param_spec:
                parameters[param_name]['items'] = param_spec['items']

        return parameters
