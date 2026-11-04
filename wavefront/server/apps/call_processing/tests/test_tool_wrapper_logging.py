import logging

from call_processing.services.common.tools.tool_wrapper_service import (
    ToolWrapperFactory,
    log_safe_keys,
    log_safe_result,
)

PHONE = '+911234567890'


def test_params_log_names_only():
    assert log_safe_keys({'caller_phone': PHONE, 'service': 'water'}) == [
        'caller_phone',
        'service',
    ]
    assert log_safe_keys('raw') == 'str'


def test_result_log_has_no_values():
    line = log_safe_result(
        {
            'success': True,
            'status_code': 200,
            'data': {'customer_name': 'Jane Doe', 'amount_due': 1250},
        }
    )

    assert line == (
        "success=True status_code=200 data_keys=['amount_due', 'customer_name']"
    )
    assert 'Jane Doe' not in line


class _FakeWrapper:
    async def execute(self, params):
        return {
            'success': True,
            'status_code': 200,
            'data': {'customer_name': 'Jane Doe', 'phone': PHONE},
        }


async def test_tool_function_logs_no_customer_data(caplog):
    tool = {
        'name': 'find_account',
        'description': 'Find the account',
        'parameter_schema': {'properties': {'caller_phone': {'type': 'string'}}},
    }
    _, fn = ToolWrapperFactory.create_pipecat_function(tool, _FakeWrapper())

    with caplog.at_level(logging.INFO, logger='call_processing'):
        result = await fn({'caller_phone': PHONE})

    assert result['data']['customer_name'] == 'Jane Doe'  # the LLM still gets it all
    assert PHONE not in caplog.text
    assert 'Jane Doe' not in caplog.text
    assert 'caller_phone' in caplog.text
