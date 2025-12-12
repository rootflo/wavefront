from datetime import datetime, date
import uuid


def serialize_values(input):
    # Handle non-dict inputs
    if not isinstance(input, dict):
        if isinstance(input, uuid.UUID):
            return str(input)
        elif isinstance(input, (datetime, date)):
            return input.isoformat()
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
        elif isinstance(value, dict):
            result[column] = serialize_values(value)
        elif isinstance(value, list):
            result[column] = [serialize_values(item) for item in value]
        else:
            result[column] = value

    return result
