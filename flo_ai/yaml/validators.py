import re
from flo_ai.error.flo_exception import FloException

name_regex = r'^[a-zA-Z0-9-_]+$'


def raise_for_name_error(string):
    if not re.match(name_regex, string):
        raise FloException(
            'Name must contain only alphanumeric characters and hyphens.'
        )
