#!/usr/bin/env python3
"""
Test script for join operations in the OData parser
"""

import pytest
from datasource.odata_parser import (
    JoinBuilder,
    ODataQueryParser,
    Lexer,
    SQLFilterParser,
)
import os

# Set cloud provider for testing
os.environ['CLOUD_PROVIDER'] = 'gcp'

parser = ODataQueryParser(type='sql')


class TestODataQueryParser:
    """Test cases for ODataQueryParser class"""

    def test_parse_empty_query(self):
        """Test parsing empty query string"""
        lexer = Lexer('')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result == {}

    def test_parse_none_query(self):
        """Test parsing None query string"""
        lexer = Lexer('')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result == {}

    def test_parse_simple_expand(self):
        """Test parsing simple $expand parameter"""
        lexer = Lexer('$expand=orders')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['expand_tables'] == ['orders']
        assert 'expand' in result

    def test_parse_multiple_expand(self):
        """Test parsing multiple tables in $expand"""
        lexer = Lexer('$expand=orders,payments')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['expand_tables'] == ['orders', 'payments']

    def test_parse_nested_expand(self):
        """Test parsing nested expand expressions"""
        lexer = Lexer('$expand=orders($expand=payments)')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['expand_tables'] == ['orders', 'payments']

    def test_parse_complex_nested_expand(self):
        """Test parsing complex nested expand expressions"""
        lexer = Lexer('$expand=orders($expand=payments,items),customers')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['expand_tables'] == ['orders', 'payments', 'items', 'customers']

    def test_parse_join_parameter(self):
        """Test parsing $join parameter"""
        lexer = Lexer('$join=customer_id')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['join'] == ['customer_id']
        assert 'expand' not in result

    def test_parse_multiple_join_columns(self):
        """Test parsing multiple join columns"""
        lexer = Lexer('$join=customer_id,order_id,payment_id')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['join'] == ['customer_id', 'order_id', 'payment_id']

    def test_parse_expand_and_join_together(self):
        """Test parsing both $expand and $join parameters"""
        lexer = Lexer('$expand=orders,payments&$join=customer_id,order_id')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['expand_tables'] == ['orders', 'payments']
        assert result['join'] == ['customer_id', 'order_id']

    def test_parse_join_with_whitespace(self):
        """Test parsing join columns with whitespace"""
        lexer = Lexer('$join= customer_id , order_id ')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result['join'] == ['customer_id', 'order_id']

    def test_parse_empty_join(self):
        """Test parsing empty join parameter"""
        lexer = Lexer('$join=')
        query_parser = SQLFilterParser(lexer)
        result = query_parser.parse_odata_query()
        assert result == {}


class TestJoinBuilder:
    """Test cases for JoinBuilder class"""

    def test_build_joins_empty_tables(self):
        """Test building joins with empty table list"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [], [], 'customers'
        )
        assert join_sql == ''
        assert table_aliases == []
        assert where_clause == ''
        assert filter_params == {}

    def test_build_single_join(self):
        """Test building a single join"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [{'name': 'orders', 'filters': []}], ['customer_id'], 'customers'
        )
        expected_sql = 'JOIN orders\n    ON customers.customer_id = orders.customer_id'
        assert join_sql == expected_sql
        assert table_aliases == ['orders']
        assert where_clause == ''
        assert filter_params == {}

    def test_build_multiple_joins(self):
        """Test building multiple joins"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [{'name': 'orders', 'filters': []}, {'name': 'payments', 'filters': []}],
            ['customer_id', 'order_id'],
            'customers',
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}

    def test_build_joins_single_column(self):
        """Test building joins with single column for all tables"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [{'name': 'orders', 'filters': []}, {'name': 'payments', 'filters': []}],
            ['customer_id'],
            'customers',
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.customer_id = payments.customer_id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}

    def test_build_joins_insufficient_columns(self):
        """Test building joins with fewer columns than tables"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [
                {'name': 'orders', 'filters': []},
                {'name': 'payments', 'filters': []},
                {'name': 'items', 'filters': []},
            ],
            ['customer_id'],
            'customers',
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.customer_id = payments.customer_id\n'
            'JOIN items\n'
            '    ON payments.customer_id = items.customer_id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments', 'items']
        assert where_clause == ''
        assert filter_params == {}

    def test_build_joins_no_columns(self):
        """Test building joins with no columns provided"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [{'name': 'orders', 'filters': []}, {'name': 'payments', 'filters': []}],
            [],
            'customers',
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.id = orders.id\n'
            'JOIN payments\n'
            '    ON orders.id = payments.id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}

    def test_build_joins_different_columns(self):
        """Test building joins with different columns for each table"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [
                {'name': 'orders', 'filters': []},
                {'name': 'payments', 'filters': []},
                {'name': 'items', 'filters': []},
            ],
            ['customer_id', 'order_id', 'item_id'],
            'customers',
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id\n'
            'JOIN items\n'
            '    ON payments.item_id = items.item_id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments', 'items']
        assert where_clause == ''
        assert filter_params == {}

    def test_build_joins_with_filters(self):
        """Test building joins with filters"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [{'name': 'orders', 'filters': ['id eq "test"']}],
            ['customer_id'],
            'customers',
        )
        expected_sql = 'JOIN orders\n    ON customers.customer_id = orders.customer_id'
        assert join_sql == expected_sql
        assert table_aliases == ['orders']
        assert where_clause == 'orders.id = @orders_id_'
        assert filter_params == {'orders_id_': 'test'}

    def test_build_joins_with_multiple_filters(self):
        """Test building joins with multiple filters"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            [
                {'name': 'orders', 'filters': ['status eq "active"']},
                {'name': 'payments', 'filters': ['amount gt 100']},
            ],
            ['customer_id', 'order_id'],
            'customers',
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert (
            where_clause
            == 'orders.status = @orders_status_ AND payments.amount > @payments_amount_'
        )
        assert filter_params == {'orders_status_': 'active', 'payments_amount_': 100}

    def test_build_joins_backward_compatibility(self):
        """Test building joins with string table names for backward compatibility"""
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            ['orders', 'payments'], ['customer_id', 'order_id'], 'customers'
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}


class TestSQLODataParserJoinOperations:
    """Test cases for SQLODataParser join operations"""

    def test_prepare_odata_joins_empty_query(self):
        """Test prepare_odata_joins with empty query"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins('', 'customers')
        )
        assert sql_expr == ''
        assert table_aliases == []
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_none_query(self):
        """Test prepare_odata_joins with None query"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(None, 'customers')
        )
        assert sql_expr == ''
        assert table_aliases == []
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_simple_expand(self):
        """Test prepare_odata_joins with simple expand"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins('$expand=orders', 'customers')
        )
        expected_sql = 'JOIN orders\n    ON customers.id = orders.id'
        assert sql_expr == expected_sql
        assert table_aliases == ['orders']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_multiple_expand(self):
        """Test prepare_odata_joins with multiple expand tables"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins('$expand=orders,payments', 'customers')
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.id = orders.id\n'
            'JOIN payments\n'
            '    ON orders.id = payments.id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_with_join_columns(self):
        """Test prepare_odata_joins with explicit join columns"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                '$expand=orders,payments&$join=customer_id,order_id', 'customers'
            )
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_nested_expand(self):
        """Test prepare_odata_joins with nested expand"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins('$expand=orders($expand=payments)', 'customers')
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.id = orders.id\n'
            'JOIN payments\n'
            '    ON orders.id = payments.id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_complex_nested(self):
        """Test prepare_odata_joins with complex nested expand"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                '$expand=orders($expand=payments,items),customers', 'users'
            )
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON users.id = orders.id\n'
            'JOIN payments\n'
            '    ON orders.id = payments.id\n'
            'JOIN items\n'
            '    ON payments.id = items.id\n'
            'JOIN customers\n'
            '    ON items.id = customers.id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments', 'items', 'customers']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_invalid_query(self):
        """Test prepare_odata_joins with invalid query format"""
        # Invalid queries should return empty results rather than raising errors
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins('invalid query format', 'customers')
        )
        assert sql_expr == ''
        assert table_aliases == []
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_with_whitespace(self):
        """Test prepare_odata_joins with whitespace in query"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                '$expand= orders , payments &$join= customer_id , order_id ',
                'customers',
            )
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_single_join_column(self):
        """Test prepare_odata_joins with single join column for multiple tables"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                '$expand=orders,payments,items&$join=customer_id', 'customers'
            )
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.customer_id = payments.customer_id\n'
            'JOIN items\n'
            '    ON payments.customer_id = items.customer_id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments', 'items']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_rf_gold_item_details(self):
        """Test prepare_odata_joins with rf_gold_item_details expand and specific join columns"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                '$expand=rf_gold_item_details&$join=id,gold_data_id', 'customers'
            )
        )
        expected_sql = (
            'JOIN rf_gold_item_details\n'
            '    ON customers.id = rf_gold_item_details.gold_data_id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['rf_gold_item_details']
        assert where_clause == ''
        assert filter_params == {}

    def test_prepare_odata_joins_with_filter(self):
        """Test prepare_odata_joins with filter in expand expression"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                "$expand=orders($filter=id eq 'test')&$join=customer_id", 'customers'
            )
        )
        expected_sql = 'JOIN orders\n    ON customers.customer_id = orders.customer_id'
        assert sql_expr == expected_sql
        assert table_aliases == ['orders']
        assert where_clause == 'orders.id = @orders_id_'
        assert filter_params == {'orders_id_': 'test'}

    def test_prepare_odata_joins_with_multiple_filters(self):
        """Test prepare_odata_joins with multiple filters in expand expressions"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                "$expand=orders($filter=status eq 'active'),payments($filter=amount gt 100)&$join=customer_id,order_id",
                'customers',
            )
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert (
            where_clause
            == 'orders.status = @orders_status_ AND payments.amount > @payments_amount_'
        )
        assert filter_params == {'orders_status_': 'active', 'payments_amount_': 100}

    def test_prepare_odata_joins_with_nested_filter_and_expand(self):
        """Test prepare_odata_joins with nested filter and expand"""
        sql_expr, table_aliases, where_clause, filter_params = (
            parser.prepare_odata_joins(
                "$expand=orders($expand=payments($filter=status eq 'pending'))&$join=customer_id,order_id",
                'customers',
            )
        )
        expected_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert sql_expr == expected_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == 'payments.status = @payments_status_'
        assert filter_params == {'payments_status_': 'pending'}


class TestIntegrationJoinOperations:
    """Integration tests for join operations"""

    def test_complete_odata_query_parsing(self):
        """Test complete OData query parsing with joins"""
        query = "$expand=orders($expand=payments),customers&$join=customer_id,order_id&$filter=status eq 'active'"

        # Test query parsing
        lexer = Lexer(query)
        query_parser = SQLFilterParser(lexer)
        parsed = query_parser.parse_odata_query()

        assert parsed['expand_tables'] == ['orders', 'payments', 'customers']
        assert parsed['join'] == ['customer_id', 'order_id']

        # Test join building
        builder = JoinBuilder()
        join_sql, table_aliases, where_clause, filter_params = builder.build_joins(
            parsed['expand'], parsed['join'], 'users'
        )

        expected_sql = (
            'JOIN orders\n'
            '    ON users.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id\n'
            'JOIN customers\n'
            '    ON payments.order_id = customers.order_id'
        )
        assert join_sql == expected_sql
        assert table_aliases == ['orders', 'payments', 'customers']
        assert where_clause == ''
        assert filter_params == {}

    def test_parser_integration_with_joins(self):
        """Test SQLODataParser integration with join operations"""
        # Test filter and join together
        filter_expr = "status eq 'active'"
        join_query = '$expand=orders,payments&$join=customer_id,order_id'

        # Parse filter
        sql_filter, filter_params = parser.prepare_odata_filter(filter_expr)
        assert sql_filter == 'status = @status'
        assert filter_params == {'status': 'active'}

        # Parse joins
        join_sql, table_aliases, where_clause, join_filter_params = (
            parser.prepare_odata_joins(join_query, 'customers')
        )
        expected_join_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert join_sql == expected_join_sql
        assert table_aliases == ['orders', 'payments']
        assert where_clause == ''
        assert join_filter_params == {}

    def test_parser_integration_with_joins_and_filters(self):
        """Test SQLODataParser integration with join operations and filters"""
        # Test filter and join together with filters in expand
        filter_expr = "status eq 'active'"
        join_query = "$expand=orders($filter=id eq 'test'),payments($filter=amount gt 100)&$join=customer_id,order_id"

        # Parse filter
        sql_filter, filter_params = parser.prepare_odata_filter(filter_expr)
        assert sql_filter == 'status = @status'
        assert filter_params == {'status': 'active'}

        # Parse joins with filters
        join_sql, table_aliases, where_clause, join_filter_params = (
            parser.prepare_odata_joins(join_query, 'customers')
        )
        expected_join_sql = (
            'JOIN orders\n'
            '    ON customers.customer_id = orders.customer_id\n'
            'JOIN payments\n'
            '    ON orders.order_id = payments.order_id'
        )
        assert join_sql == expected_join_sql
        assert table_aliases == ['orders', 'payments']
        assert (
            where_clause
            == 'orders.id = @orders_id_ AND payments.amount > @payments_amount_'
        )
        assert join_filter_params == {'orders_id_': 'test', 'payments_amount_': 100}


if __name__ == '__main__':
    pytest.main([__file__])
