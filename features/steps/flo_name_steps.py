from behave import when, then
from flo_ai.yaml.validators import raise_for_name_error

@when('use the name, {flo_name}')
def step_impl(context, flo_name):
    isException = "False"
    try:
        raise_for_name_error(flo_name)
    except Exception as e:
        isException = "True"
    context.isException = isException

@then('it should be {validity}')
def step_impl(context, validity):
    assert context.isException != validity