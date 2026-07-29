from datetime import datetime, date
from decimal import Decimal
import uuid


def serialize_values(input):
    # Handle non-dict inputs
    if not isinstance(input, dict):
        if isinstance(input, uuid.UUID):
            return str(input)
        elif isinstance(input, (datetime, date)):
            return input.isoformat()
        # Postgres numeric/decimal arrives as Decimal, which json.dumps rejects.
        # float keeps it a JSON number, so callers can do arithmetic on it
        # without parsing — at the cost of float's ~15-17 significant digits.
        # numeric is arbitrary-precision, so a wider value is rounded here;
        # return str instead if exactness ever matters more than ergonomics.
        elif isinstance(input, Decimal):
            return float(input)
        elif isinstance(input, list):
            return [serialize_values(item) for item in input]
        elif hasattr(input, '_asdict'):
            return serialize_values(input._asdict())
        else:
            return input

    result = {}
    for column in input.keys():
        value = input.get(column, None)
        if isinstance(value, uuid.UUID):
            result[column] = str(value)
        elif isinstance(value, (datetime, date)):
            result[column] = value.isoformat()
        elif isinstance(value, Decimal):
            result[column] = float(value)
        elif isinstance(value, dict):
            result[column] = serialize_values(value)
        elif isinstance(value, list):
            result[column] = [serialize_values(item) for item in value]
        else:
            result[column] = value

    return result
