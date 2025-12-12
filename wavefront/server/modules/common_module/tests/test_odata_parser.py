from datetime import datetime
import os

from common_module.utils.odata_parser import fill_odata_query
from common_module.utils.odata_parser import prepare_odata_filter
import pytest

# Set cloud provider for testing
os.environ['CLOUD_PROVIDER'] = 'gcp'


def test_basic_equality_filter():
    filter_expr = "name eq 'John'"
    expected_sql = 'name = @name'
    expected_params = {'name': 'John'}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_equality_filter_with_quotes():
    filter_expr = "branch eq 'Agar - (MP) 5323'"
    expected_sql = 'branch = @branch'
    expected_params = {'branch': 'Agar - (MP) 5323'}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_numeric_comparison():
    filter_expr = 'age gt 25'
    expected_sql = 'age > @age'
    expected_params = {'age': 25}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_date_comparison():
    filter_expr = 'created_at gt 2024-01-01T00:00:00'
    expected_sql = 'created_at > @created_at'
    expected_params = {'created_at': datetime(2024, 1, 1, 0, 0)}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_contains_operator():
    filter_expr = "description contains 'test'"
    expected_sql = 'description LIKE @description'
    expected_params = {'description': '%test%'}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_in_operator():
    filter_expr = "status in ['active', 'pending']"
    expected_sql = 'status IN (@status_0, @status_1)'
    expected_params = {'status_0': 'active', 'status_1': 'pending'}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_complex_and_condition():
    filter_expr = "age gt 25 $and status eq 'active'"
    expected_sql = 'age > @age AND status = @status'
    expected_params = {'age': 25, 'status': 'active'}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_complex_or_condition():
    filter_expr = "status eq 'active' $or status eq 'pending'"
    expected_sql = 'status = @status OR status = @status_1'
    expected_params = {'status': 'active', 'status_1': 'pending'}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_complex_or_condition_with_quotes():
    filter_expr = "(branch eq 'Agar - (MP) 5323' $or created_at gt 2025-05-04T05:59:56)"
    expected_sql = '(branch = @branch OR created_at > @created_at)'
    expected_params = {
        'branch': 'Agar - (MP) 5323',
        'created_at': datetime(2025, 5, 4, 5, 59, 56),
    }
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_custom_parameter_prefix():
    filter_expr = "name eq 'John'"
    expected_sql = 'name = :name'
    expected_params = {'name': 'John'}
    sql_expr, params = prepare_odata_filter(filter_expr, parameter=':')
    assert sql_expr == expected_sql
    assert params == expected_params


def test_empty_filter():
    sql_expr, params = prepare_odata_filter('')
    assert sql_expr is None
    assert params is None


def test_invalid_operator():
    with pytest.raises(ValueError, match='Invalid filter expression'):
        prepare_odata_filter("name invalid_op 'John'")


def test_invalid_filter_format():
    with pytest.raises(ValueError, match='Invalid filter expression'):
        prepare_odata_filter('invalid filter format')


def test_multiple_conditions_with_same_field():
    filter_expr = "status eq 'active' $and status eq 'pending'"
    expected_sql = 'status = @status AND status = @status_1'
    expected_params = {'status': 'active', 'status_1': 'pending'}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_less_than_or_equal():
    filter_expr = 'age lte 30'
    expected_sql = 'age <= @age'
    expected_params = {'age': 30}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_greater_than_or_equal():
    filter_expr = 'age gte 18'
    expected_sql = 'age >= @age'
    expected_params = {'age': 18}
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql
    assert params == expected_params


def test_greater_than_or_equal_filling():
    filter_expr = 'age gte 18'
    expected_sql = 'age >= 18'
    sql_expr, params = prepare_odata_filter(filter_expr)
    fill_odata = fill_odata_query(sql_expr, params)
    assert fill_odata == expected_sql


def test_multiple_conditions_with_same_field_filling():
    filter_expr = "status eq 'active' $and status eq 'pending'"
    expected_sql = "status = 'active' AND status = 'pending'"
    sql_expr, params = prepare_odata_filter(filter_expr)
    fill_odata = fill_odata_query(sql_expr, params)
    assert fill_odata == expected_sql


def test_multiple_conditions_with_loan_amt():
    filter_expr = "created_at gt 2025-07-23T07:42:44 $and (loan_id contains '96444' $or branch contains '96444' $or region contains '96444' $or zone contains '96444' $or loan_amount eq '96444')"
    expected_sql = "created_at > @created_at AND (loan_id LIKE '%96444%' OR branch LIKE '%96444%' OR region LIKE '%96444%' OR zone LIKE '%96444%' OR loan_amount = '96444')"
    sql_expr, params = prepare_odata_filter(filter_expr)
    fill_odata = fill_odata_query(sql_expr, params)
    assert fill_odata == expected_sql


def test_multiple_conditions_with_contains():
    filter_expr = '(loan_amount gt 50000 $and loan_amount lt 100000 $or loan_amount gt 100000 $and loan_amount lt 250000 $or loan_amount gt 250000 $and loan_amount lt 500000 $or loan_amount gt 500000) $and  created_at gt 2025-07-23T08:03:37'
    expected_sql = '(loan_amount > @loan_amount AND loan_amount < @loan_amount_1 OR loan_amount > @loan_amount_2 AND loan_amount < @loan_amount_3 OR loan_amount > @loan_amount_4 AND loan_amount < @loan_amount_5 OR loan_amount > @loan_amount_6) AND  created_at > @created_at'
    sql_expr, _ = prepare_odata_filter(filter_expr)
    assert sql_expr == expected_sql


def test_multiple_conditions_with_float():
    filter_expr = '(gold_purity gt 91.67) $and  created_at gt 2025-07-23T10:07:03'
    expected_sql = '(gold_purity > @gold_purity) AND  created_at > @created_at'
    sql_expr, params = prepare_odata_filter(filter_expr)
    assert params['gold_purity'] == 91.67
    assert sql_expr == expected_sql
