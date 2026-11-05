import json
from datetime import date, datetime, time

from common_module.utils.serializer import serialize_values


def test_time_values_are_serialized_as_iso_strings():
    # A Postgres TIME column arrives as datetime.time (#464).
    row = {
        'scheduled_time': time(10, 0),
        'at': datetime(2026, 10, 22, 9, 30),
        'on': date(2026, 10, 22),
    }

    result = serialize_values(row)

    assert result == {
        'scheduled_time': '10:00:00',
        'at': '2026-10-22T09:30:00',
        'on': '2026-10-22',
    }
    json.dumps(result)


def test_time_values_in_lists_and_bare_values_are_serialized():
    assert serialize_values([{'t': time(23, 59, 1)}]) == [{'t': '23:59:01'}]
    assert serialize_values(time(7, 5)) == '07:05:00'
