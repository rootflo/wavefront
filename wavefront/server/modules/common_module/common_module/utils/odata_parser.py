from datetime import datetime
import os
import re
from typing import Any, Tuple

from common_module.log.logger import logger

cloud_provider = os.environ.get('CLOUD_PROVIDER')


def parse_value(value: str) -> Any:
    """Converts string values to appropriate Python types."""
    if value.isdigit():
        return int(value)
    if value.replace('.', '', 1).isdigit():
        return float(value)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    return value.strip("'")


def prepare_odata_filter(
    filter_expr: str, parameter: str = None, prefix: str = ''
) -> Tuple[str, dict]:
    """Parses an OData-like filter expression and converts it into a SQL-like query with parameters."""
    if not filter_expr:
        return None, None

    pattern = re.compile(
        r'(\w+)\s+(eq|lte|gte|gt|lt|contains|in)\s+(\'[^\']*\'|"[^"]*"|\[[^\]]*\]|[^$()\s]+?)(?=\s*(?:\$and|\$or|\)|\s*$))'
    )

    ops = {
        'eq': '=',
        'gt': '>',
        'lt': '<',
        'lte': '<=',
        'gte': '>=',
        'contains': 'LIKE',
        'in': 'IN',
    }

    # Replace AND / OR operators with SQL equivalents
    sql_expr = filter_expr.replace('$and', 'AND').replace('$or', 'OR')
    matches = pattern.findall(filter_expr)

    if not matches:
        logger.error(f'Invalid filter {filter_expr}')
        raise ValueError('Invalid filter expression')

    params = {}
    param_count = {}

    to_replace: list[Tuple[str, str]] = []
    for field, operator, value in matches:
        if operator not in ops:
            logger.error(f'Unsupported operator {operator}')
            raise ValueError(f'Unsupported operator: {operator}')

        if field in param_count:
            param_count[field] += 1
            param_key = f'{prefix}{field}_{param_count[field]}'
        else:
            param_count[field] = 0
            param_key = f'{prefix}{field}'

        dynamic_var_char = (
            parameter if parameter else ('@' if cloud_provider == 'gcp' else ':')
        )

        if operator == 'contains':
            parsed_value = parse_value(value)
            params[param_key] = f'%{parsed_value}%'
            new_expr = f'{field} {ops[operator]} {dynamic_var_char}{param_key}'

        elif operator == 'in':
            items = value.strip('[]').split(',')
            parsed_value = [v.strip().strip('\'"') for v in items]

            placeholder_keys = []
            for idx, val in enumerate(parsed_value):
                item_key = f'{param_key}_{idx}'
                params[item_key] = val
                placeholder_keys.append(f'{dynamic_var_char}{item_key}')
            new_expr = f"{field} IN ({', '.join(placeholder_keys)})"
        else:
            parsed_value = parse_value(value)
            params[param_key] = parsed_value
            new_expr = f'{field} {ops[operator]} {dynamic_var_char}{param_key}'

        old_expr = f'{field} {operator} {value}'
        to_replace.append((old_expr, new_expr))

    sorted_matches = sorted(to_replace, key=lambda x: len(x[0]), reverse=True)
    for old_expr, new_expr in sorted_matches:
        sql_expr = sql_expr.replace(old_expr, new_expr)

    return sql_expr, params


def fill_odata_query(sql_expr: str, parameters: dict = {}) -> str:
    output_sql = sql_expr
    dynamic_var_char = '@' if cloud_provider == 'gcp' else ':'
    param_names = sorted(parameters.keys(), key=len, reverse=True)
    for parameter in param_names:
        if isinstance(parameters[parameter], str):
            output_sql = output_sql.replace(
                f'{dynamic_var_char}{parameter}', f"'{parameters[parameter]}'"
            )
        if isinstance(parameters[parameter], int):
            output_sql = output_sql.replace(
                f'{dynamic_var_char}{parameter}', str(parameters[parameter])
            )
        else:
            logger.warning(
                f'Unsupported parameter type for {parameter}: {type(parameters[parameter])}'
            )
    return output_sql
