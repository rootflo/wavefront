import pytest
from flo_ai.yaml.validators import raise_for_name_error


@pytest.mark.parametrize(
    'flo_name, validity',
    [
        ('CorrectName', True),
        ('Wrong Name', False),
        ('correct_name', True),
        ('correct-name', True),
        ('wrong/name', False),
    ],
)
def test_flo_component_names(flo_name, validity):
    isException = False
    try:
        raise_for_name_error(flo_name)
    except Exception:
        isException = True
    assert isException != validity
