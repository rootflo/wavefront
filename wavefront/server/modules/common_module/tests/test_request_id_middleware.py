import pytest
from fastapi.testclient import TestClient
from common_module.middleware.request_id_middleware import RequestIdMiddleware


class TestRequestIdMiddlewareUnit:
    """Unit tests for individual middleware methods."""

    def test_validate_request_id_valid_cases(self):
        """Test request ID validation for valid cases."""
        valid_ids = [
            'fe-abc12345',  # minimum fe
            'be-xyz67890',  # minimum be
            'fe-AbC123dEf',  # mixed case
            'be-123456789012',  # maximum length (12 chars)
            'fe-a1b2c3d4',  # mixed alphanumeric
        ]

        for request_id in valid_ids:
            assert RequestIdMiddleware.validate_request_id(
                request_id
            ), f'Should be valid: {request_id}'

    def test_validate_request_id_invalid_cases(self):
        """Test request ID validation for invalid cases."""
        invalid_ids = [
            'invalid-id',  # wrong prefix
            'fe-abc123',  # too short (7 chars)
            'be-abc1234567890',  # too long (13 chars)
            'fe-abc123!@',  # invalid characters
            'xx-abc12345',  # invalid prefix
            '',  # empty
            'fe-',  # no random part
            'abc12345',  # no prefix
            'FE-abc12345',  # uppercase prefix
            'fe_abc12345',  # underscore instead of dash
        ]

        for request_id in invalid_ids:
            assert not RequestIdMiddleware.validate_request_id(
                request_id
            ), f'Should be invalid: {request_id}'

    def test_generate_request_id_format(self):
        """Test that generated IDs have correct format."""
        # Test backend prefix
        be_id = RequestIdMiddleware.generate_request_id('be')
        assert be_id.startswith('be-')
        assert 11 <= len(be_id) <= 15  # be- + 8-12 chars
        assert RequestIdMiddleware.validate_request_id(be_id)

        # Test frontend prefix
        fe_id = RequestIdMiddleware.generate_request_id('fe')
        assert fe_id.startswith('fe-')
        assert 11 <= len(fe_id) <= 15  # fe- + 8-12 chars
        assert RequestIdMiddleware.validate_request_id(fe_id)

        # Test invalid prefix defaults to 'be'
        default_id = RequestIdMiddleware.generate_request_id('invalid')
        assert default_id.startswith('be-')

        # Test multiple generations are unique
        ids = set()
        for _ in range(100):
            new_id = RequestIdMiddleware.generate_request_id('be')
            assert new_id not in ids, 'Generated IDs should be unique'
            ids.add(new_id)

    def test_get_request_id_from_headers_case_insensitive(self, mock_request):
        """Test header extraction is case insensitive."""
        test_cases = [
            ('X-Flo-Request-ID', 'fe-standard'),
            ('x-flo-request-id', 'fe-lower'),
            ('X-FLO-REQUEST-ID', 'fe-upper'),
            ('X-flo-Request-Id', 'fe-mixed'),
            ('x-Flo-REQUEST-id', 'be-weird'),
        ]

        for header_name, expected_value in test_cases:
            mock_request.headers = {header_name: expected_value}
            result = RequestIdMiddleware.get_request_id_from_headers(mock_request)
            assert (
                result == expected_value
            ), f'Should find {expected_value} in header {header_name}'

    def test_get_request_id_from_headers_not_found(self, mock_request):
        """Test when request ID header is not present."""
        mock_request.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer token',
        }
        result = RequestIdMiddleware.get_request_id_from_headers(mock_request)
        assert result is None


class TestRequestIdMiddlewareMockIntegration:
    """Integration tests using mock FastAPI app."""

    @pytest.mark.parametrize(
        'header_name,request_id',
        [
            ('X-Flo-Request-ID', 'fe-abc12345'),
            ('x-flo-request-id', 'fe-def67890'),
            ('X-FLO-REQUEST-ID', 'be-ghi12345'),
            ('X-flo-request-id', 'fe-jkl67890'),
            ('x-Flo-Request-Id', 'be-mno12345'),
            ('X-FLO-request-ID', 'fe-pqr67890'),
            ('x-flo-REQUEST-id', 'be-stu12345'),
        ],
    )
    def test_case_insensitive_headers(
        self, client: TestClient, header_name: str, request_id: str
    ):
        """Test that X-Flo-Request-ID header is case insensitive."""
        response = client.get('/test', headers={header_name: request_id})

        # Check response header
        returned_id = response.headers.get('X-Flo-Request-ID')
        assert returned_id == request_id, f'Expected {request_id}, got {returned_id}'

        # Check that middleware stored it in request state
        assert response.json()['request_id_in_state'] == request_id

    @pytest.mark.parametrize(
        'request_id,expected_prefix,description',
        [
            # Valid cases (should be preserved)
            ('fe-abc12345', 'fe-abc12345', 'Valid frontend ID (8 chars)'),
            ('be-xyz123456789', 'be-xyz123456789', 'Valid backend ID (12 chars)'),
            ('fe-AbC123dEf', 'fe-AbC123dEf', 'Valid mixed case alphanumeric'),
            # Invalid cases (should generate new be-* ID)
            ('invalid-id', 'be-', 'Invalid format - no prefix'),
            ('fe-abc123', 'be-', 'Too short (7 chars)'),
            ('be-abc1234567890', 'be-', 'Too long (13 chars)'),
            ('fe-abc123!@', 'be-', 'Invalid characters'),
            ('xx-abc12345', 'be-', 'Invalid prefix'),
            ('', 'be-', 'Empty ID'),
        ],
    )
    def test_request_id_validation(
        self,
        client: TestClient,
        request_id: str,
        expected_prefix: str,
        description: str,
    ):
        """Test request ID validation and generation."""
        headers = {'X-Flo-Request-ID': request_id} if request_id else {}
        response = client.get('/test', headers=headers)

        returned_id = response.headers.get('X-Flo-Request-ID')
        assert (
            returned_id is not None
        ), 'Response should always contain X-Flo-Request-ID header'

        if expected_prefix == returned_id:
            # Exact match expected
            assert returned_id == expected_prefix
        elif expected_prefix.endswith('-'):
            # Should generate new ID with expected prefix
            assert returned_id.startswith(
                expected_prefix
            ), f"Expected ID to start with '{expected_prefix}', got '{returned_id}'"
            assert len(returned_id) >= 11, f'Generated ID too short: {returned_id}'
        else:
            # Valid ID should be preserved
            assert returned_id == expected_prefix

    def test_no_request_id_header(self, client: TestClient):
        """Test behavior when no X-Flo-Request-ID header is provided."""
        response = client.get('/test')

        returned_id = response.headers.get('X-Flo-Request-ID')
        assert (
            returned_id is not None
        ), 'Response should always contain X-Flo-Request-ID header'
        assert returned_id.startswith(
            'be-'
        ), f"Generated ID should start with 'be-', got: {returned_id}"
        assert len(returned_id) >= 11, f'Generated ID too short: {returned_id}'

        # Check it's stored in request state
        assert response.json()['request_id_in_state'] == returned_id

    @pytest.mark.parametrize(
        'input_headers',
        [
            {'X-Flo-Request-ID': 'fe-test12345'},
            {'x-flo-request-id': 'be-test67890'},
            {},  # no header
        ],
    )
    def test_response_headers_always_present(
        self, client: TestClient, input_headers: dict
    ):
        """Test that response headers always contain X-Flo-Request-ID."""
        response = client.get('/metrics', headers=input_headers)

        returned_id = response.headers.get('X-Flo-Request-ID')
        assert (
            returned_id is not None
        ), 'Response should always contain X-Flo-Request-ID header'
        assert returned_id.startswith(
            ('fe-', 'be-')
        ), f'Invalid ID prefix: {returned_id}'
        assert len(returned_id) >= 11, f'ID too short: {returned_id}'

    def test_middleware_state_persistence(self, client: TestClient):
        """Test that request ID persists in request state throughout request lifecycle."""
        response = client.get('/test', headers={'X-Flo-Request-ID': 'fe-persist123'})

        # Verify the middleware stored the request ID in request.state
        assert response.json()['request_id_in_state'] == 'fe-persist123'
        # Verify the middleware added it to response headers
        assert response.headers.get('X-Flo-Request-ID') == 'fe-persist123'

    def test_request_id_format_edge_cases(self, client: TestClient):
        """Test specific format requirements for request IDs."""
        test_cases = [
            ('fe-abcd1234', True, 'Minimum valid length'),  # 8 chars
            ('be-abcd12345678', True, 'Maximum valid length'),  # 12 chars
            ('fe-abc1234a', True, 'Mixed alphanumeric'),
            ('be-12345678', True, 'All numbers'),
            ('fe-abcdefgh', True, 'All letters'),
        ]

        for test_id, should_be_valid, description in test_cases:
            response = client.get('/test', headers={'X-Flo-Request-ID': test_id})
            returned_id = response.headers.get('X-Flo-Request-ID')

            if should_be_valid:
                assert (
                    returned_id == test_id
                ), f'{description}: {test_id} should be preserved'
            else:
                assert (
                    returned_id != test_id
                ), f'{description}: {test_id} should be rejected'
                assert returned_id.startswith('be-'), 'Should generate new be- ID'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
