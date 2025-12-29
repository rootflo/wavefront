"""
Tests for payload validation functionality.

Tests cover:
- Valid payload passes validation
- Missing required fields return 400
- Wrong field types return 400
- Extra fields are allowed
- Validation applies to POST/PUT/PATCH only
- Validation skipped when no schema defined
- Complex types (object, array)
- Detailed error messages
- Multiple validation errors
"""

import pytest
from api_services_module.config.parser import ServiceDefinitionParser
from api_services_module.core.proxy import ApiProxy
from api_services_module.config.registry import ServiceRegistry
from api_services_module.models.service import (
    PayloadFieldSchema,
    PayloadSchema,
    ApiConfig,
    HttpMethod,
)
from api_services_module.pipeline.stages import PayloadValidatorStage
from api_services_module.models.pipeline import PipelineContext, PipelineException


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def payload_validation_yaml():
    """YAML configuration with payload validation."""
    return """
service:
  id: test-validation-service
  base_url: https://api.test.com
  auth:
    id: test-auth
    type: bearer
    token: test-token
  apis:
    - id: create-user
      path: /users
      backend_path: /users
      method: POST
      payload_schema:
        fields:
          - name: name
            type: string
            required: true
            description: User's full name
          - name: email
            type: string
            required: true
            description: User's email address
          - name: age
            type: integer
            required: false
            description: User's age
          - name: is_active
            type: boolean
            required: false
            description: Whether user is active
    - id: update-user
      path: /users/{id}
      backend_path: /users/{id}
      method: PUT
      payload_schema:
        fields:
          - name: name
            type: string
            required: false
          - name: email
            type: string
            required: false
    - id: no-validation-api
      path: /no-validation
      backend_path: /no-validation
      method: POST
"""


@pytest.fixture
def complex_types_yaml():
    """YAML configuration with complex types (array, object)."""
    return """
service:
  id: complex-types-service
  base_url: https://api.complex.com
  auth:
    id: complex-auth
    type: bearer
    token: complex-token
  apis:
    - id: create-order
      path: /orders
      backend_path: /orders
      method: POST
      payload_schema:
        fields:
          - name: customer
            type: object
            required: true
            description: Customer object
          - name: items
            type: array
            required: true
            description: Order items
          - name: total
            type: number
            required: true
            description: Total amount
"""


@pytest.fixture
async def validation_service_registry(payload_validation_yaml):
    """Service registry with validation-enabled service."""
    from tests.conftest import MockApiServicesManager

    yaml_map = {'test-validation-service': payload_validation_yaml}
    manager = MockApiServicesManager(service_yaml_map=yaml_map)
    registry = ServiceRegistry(manager)
    await registry.load_from_db()
    return registry


@pytest.fixture
async def complex_types_registry(complex_types_yaml):
    """Service registry with complex types validation."""
    from tests.conftest import MockApiServicesManager

    yaml_map = {'complex-types-service': complex_types_yaml}
    manager = MockApiServicesManager(service_yaml_map=yaml_map)
    registry = ServiceRegistry(manager)
    await registry.load_from_db()
    return registry


# ============================================================================
# Parser Tests
# ============================================================================


def test_parse_payload_schema_valid():
    """Test parsing valid payload schema from YAML."""
    yaml_content = """
service:
  id: test-service
  base_url: https://api.test.com
  auth:
    id: test-auth
    type: bearer
    token: test-token
  apis:
    - id: test-api
      path: /test
      backend_path: /test
      method: POST
      payload_schema:
        fields:
          - name: field1
            type: string
            required: true
            description: Test field
          - name: field2
            type: integer
            required: false
"""

    service_def = ServiceDefinitionParser.parse_yaml_string(yaml_content)
    api_config = service_def.apis[0]

    assert api_config.payload_schema is not None
    assert len(api_config.payload_schema.fields) == 2

    field1 = api_config.payload_schema.fields[0]
    assert field1.name == 'field1'
    assert field1.type == 'string'
    assert field1.required is True
    assert field1.description == 'Test field'

    field2 = api_config.payload_schema.fields[1]
    assert field2.name == 'field2'
    assert field2.type == 'integer'
    assert field2.required is False


def test_parse_payload_schema_no_schema():
    """Test parsing API without payload schema."""
    yaml_content = """
service:
  id: test-service
  base_url: https://api.test.com
  auth:
    id: test-auth
    type: bearer
    token: test-token
  apis:
    - id: test-api
      path: /test
      backend_path: /test
      method: GET
"""

    service_def = ServiceDefinitionParser.parse_yaml_string(yaml_content)
    api_config = service_def.apis[0]

    assert api_config.payload_schema is None


def test_parse_payload_schema_invalid_type():
    """Test parsing payload schema with invalid type."""
    yaml_content = """
service:
  id: test-service
  base_url: https://api.test.com
  auth:
    id: test-auth
    type: bearer
    token: test-token
  apis:
    - id: test-api
      path: /test
      backend_path: /test
      method: POST
      payload_schema:
        fields:
          - name: field1
            type: invalid_type
            required: true
"""

    with pytest.raises(ValueError) as exc_info:
        ServiceDefinitionParser.parse_yaml_string(yaml_content)

    assert "Invalid payload field type 'invalid_type'" in str(exc_info.value)


def test_parse_payload_schema_missing_name():
    """Test parsing payload schema with missing field name."""
    yaml_content = """
service:
  id: test-service
  base_url: https://api.test.com
  auth:
    id: test-auth
    type: bearer
    token: test-token
  apis:
    - id: test-api
      path: /test
      backend_path: /test
      method: POST
      payload_schema:
        fields:
          - type: string
            required: true
"""

    with pytest.raises(ValueError) as exc_info:
        ServiceDefinitionParser.parse_yaml_string(yaml_content)

    assert 'missing required attribute: name' in str(exc_info.value)


# ============================================================================
# Validation Stage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_valid_payload_passes():
    """Test that valid payload passes validation."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
            PayloadFieldSchema(name='age', type='integer', required=False),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(method='POST', body={'name': 'John Doe', 'age': 30})

    result = await stage.execute(context)
    assert result is context  # No exception raised


@pytest.mark.asyncio
async def test_missing_required_field_fails():
    """Test that missing required field raises validation error."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
            PayloadFieldSchema(name='email', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(
        method='POST',
        body={'name': 'John Doe'},  # Missing 'email'
    )

    with pytest.raises(PipelineException) as exc_info:
        await stage.execute(context)

    assert 'validation failed' in str(exc_info.value).lower()
    assert "Missing required field 'email'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_wrong_field_type_fails():
    """Test that wrong field type raises validation error."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='age', type='integer', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(
        method='POST',
        body={'age': 'thirty'},  # String instead of integer
    )

    with pytest.raises(PipelineException) as exc_info:
        await stage.execute(context)

    assert 'expected type integer but got str' in str(exc_info.value)


@pytest.mark.asyncio
async def test_extra_fields_allowed():
    """Test that extra fields not in schema are allowed."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(
        method='POST', body={'name': 'John Doe', 'extra_field': 'value', 'another': 123}
    )

    result = await stage.execute(context)
    assert result is context  # No exception raised


@pytest.mark.asyncio
async def test_validation_skipped_for_get_method():
    """Test that validation is skipped for GET requests."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.GET,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(method='GET', body={'invalid': 'data'})

    result = await stage.execute(context)
    assert result is context  # Validation skipped


@pytest.mark.asyncio
async def test_validation_applies_to_post():
    """Test that validation applies to POST requests."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(
        method='POST',
        body={},  # Missing required field
    )

    with pytest.raises(PipelineException):
        await stage.execute(context)


@pytest.mark.asyncio
async def test_validation_applies_to_put():
    """Test that validation applies to PUT requests."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.PUT,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(
        method='PUT',
        body={},  # Missing required field
    )

    with pytest.raises(PipelineException):
        await stage.execute(context)


@pytest.mark.asyncio
async def test_validation_applies_to_patch():
    """Test that validation applies to PATCH requests."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.PATCH,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(
        method='PATCH',
        body={},  # Missing required field
    )

    with pytest.raises(PipelineException):
        await stage.execute(context)


@pytest.mark.asyncio
async def test_validation_skipped_when_no_schema():
    """Test that validation is skipped when no schema is defined."""
    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=None,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(method='POST', body={'any': 'data'})

    result = await stage.execute(context)
    assert result is context  # No validation performed


@pytest.mark.asyncio
async def test_complex_type_object():
    """Test validation of object type."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='user', type='object', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)

    # Valid object
    context = PipelineContext(method='POST', body={'user': {'name': 'John', 'age': 30}})
    result = await stage.execute(context)
    assert result is context

    # Invalid (not an object)
    context_invalid = PipelineContext(method='POST', body={'user': 'not an object'})
    with pytest.raises(PipelineException) as exc_info:
        await stage.execute(context_invalid)
    assert 'expected type object but got str' in str(exc_info.value)


@pytest.mark.asyncio
async def test_complex_type_array():
    """Test validation of array type."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='items', type='array', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)

    # Valid array
    context = PipelineContext(method='POST', body={'items': [1, 2, 3]})
    result = await stage.execute(context)
    assert result is context

    # Invalid (not an array)
    context_invalid = PipelineContext(method='POST', body={'items': 'not an array'})
    with pytest.raises(PipelineException) as exc_info:
        await stage.execute(context_invalid)
    assert 'expected type array but got str' in str(exc_info.value)


@pytest.mark.asyncio
async def test_multiple_validation_errors():
    """Test that multiple validation errors are reported together."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
            PayloadFieldSchema(name='age', type='integer', required=True),
            PayloadFieldSchema(name='active', type='boolean', required=False),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(
        method='POST',
        body={'age': 'thirty', 'active': 'yes'},  # Missing 'name', wrong types
    )

    with pytest.raises(PipelineException) as exc_info:
        await stage.execute(context)

    error_message = str(exc_info.value)
    assert "Missing required field 'name'" in error_message
    assert 'expected type integer but got str' in error_message
    assert 'expected type boolean but got str' in error_message


@pytest.mark.asyncio
async def test_all_basic_types():
    """Test validation of all basic types."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='str_field', type='string', required=True),
            PayloadFieldSchema(name='int_field', type='integer', required=True),
            PayloadFieldSchema(name='num_field', type='number', required=True),
            PayloadFieldSchema(name='bool_field', type='boolean', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)

    # All valid types
    context = PipelineContext(
        method='POST',
        body={
            'str_field': 'hello',
            'int_field': 42,
            'num_field': 3.14,
            'bool_field': True,
        },
    )
    result = await stage.execute(context)
    assert result is context


@pytest.mark.asyncio
async def test_integer_vs_number_type():
    """Test distinction between integer and number types."""
    # Integer type should NOT accept floats
    int_schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='value', type='integer', required=True),
        ]
    )

    int_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=int_schema,
    )

    int_stage = PayloadValidatorStage(int_config)

    # Valid integer
    context_int = PipelineContext(method='POST', body={'value': 42})
    await int_stage.execute(context_int)

    # Invalid (float for integer)
    context_float = PipelineContext(method='POST', body={'value': 3.14})
    with pytest.raises(PipelineException):
        await int_stage.execute(context_float)

    # Number type should accept both int and float
    num_schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='value', type='number', required=True),
        ]
    )

    num_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=num_schema,
    )

    num_stage = PayloadValidatorStage(num_config)

    # Valid integer
    context_int = PipelineContext(method='POST', body={'value': 42})
    await num_stage.execute(context_int)

    # Valid float
    context_float = PipelineContext(method='POST', body={'value': 3.14})
    await num_stage.execute(context_float)


@pytest.mark.asyncio
async def test_null_value_treated_as_missing():
    """Test that null values are treated as missing fields."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='required_field', type='string', required=True),
            PayloadFieldSchema(name='optional_field', type='string', required=False),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)

    # Null for required field should fail
    context = PipelineContext(method='POST', body={'required_field': None})

    with pytest.raises(PipelineException) as exc_info:
        await stage.execute(context)
    assert "Missing required field 'required_field'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_no_body_with_required_fields():
    """Test that no body with required fields raises error."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='name', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(method='POST', body=None)

    with pytest.raises(PipelineException) as exc_info:
        await stage.execute(context)
    assert 'Missing required field' in str(exc_info.value)


@pytest.mark.asyncio
async def test_empty_string_valid_for_string_type():
    """Test that empty string is valid for string type."""
    schema = PayloadSchema(
        fields=[
            PayloadFieldSchema(name='text', type='string', required=True),
        ]
    )

    api_config = ApiConfig(
        id='test-api',
        path='/test',
        backend_path='/test',
        method=HttpMethod.POST,
        payload_schema=schema,
    )

    stage = PayloadValidatorStage(api_config)
    context = PipelineContext(method='POST', body={'text': ''})

    result = await stage.execute(context)
    assert result is context  # Empty string is valid


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_proxy_returns_400_for_validation_error(validation_service_registry):
    """Test that proxy returns HTTP 400 for validation errors."""

    proxy = ApiProxy(validation_service_registry)

    # Missing required fields
    response = await proxy.process_request(
        service_id='test-validation-service',
        api_id='create-user',
        api_version='v1',
        method='POST',
        path='/users',
        body={'name': 'John'},  # Missing 'email'
    )

    assert response.http_status_code == 400
    assert response.meta['status'] == 'validation_error'
    assert "Missing required field 'email'" in response.meta['message']


@pytest.mark.asyncio
async def test_proxy_successful_with_valid_payload(validation_service_registry):
    """Test that proxy succeeds with valid payload."""
    from unittest.mock import AsyncMock, Mock, patch

    proxy = ApiProxy(validation_service_registry)

    # Mock the httpx client
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {'content-type': 'application/json'}
    mock_response.json.return_value = {
        'id': 1,
        'name': 'John',
        'email': 'john@test.com',
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response = await proxy.process_request(
            service_id='test-validation-service',
            api_id='create-user',
            api_version='v1',
            method='POST',
            path='/users',
            body={'name': 'John', 'email': 'john@test.com', 'age': 30},
        )

    assert response.http_status_code == 200
    assert response.meta['status'] == 'success'


@pytest.mark.asyncio
async def test_validation_in_full_pipeline(validation_service_registry):
    """Test that validation is properly integrated in the pipeline."""

    proxy = ApiProxy(validation_service_registry)

    # Test with type error
    response = await proxy.process_request(
        service_id='test-validation-service',
        api_id='create-user',
        api_version='v1',
        method='POST',
        path='/users',
        body={'name': 'John', 'email': 'john@test.com', 'age': 'thirty'},  # Wrong type
    )

    assert response.http_status_code == 400
    assert 'expected type integer but got str' in response.meta['message']
