from datetime import datetime
from typing import Any, Tuple, List, Dict, Optional
from enum import Enum, auto
from abc import ABC, abstractmethod


class TokenType(Enum):
    FIELD = auto()
    OPERATOR = auto()
    VALUE = auto()
    LOGICAL_OP = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF = auto()
    DOLLAR = auto()
    EQUALS = auto()
    COMMA = auto()
    AMPERSAND = auto()


class Token:
    def __init__(self, type: TokenType, value: str, position: int):
        self.type = type
        self.value = value
        self.position = position

    def __str__(self):
        return f"Token({self.type}, '{self.value}', pos={self.position})"


class Lexer:
    """Lexical analyzer for OData filter expressions"""

    def __init__(self, text: str):
        self.text = text
        self.position = 0
        self.current_char = self.text[0] if text else None

    def advance(self):
        self.position += 1
        if self.position >= len(self.text):
            self.current_char = None
        else:
            self.current_char = self.text[self.position]

    def peek(self, n: int = 1) -> Optional[str]:
        peek_pos = self.position + n
        if peek_pos >= len(self.text):
            return None
        return self.text[peek_pos]

    def skip_whitespace(self):
        while self.current_char and self.current_char.isspace():
            self.advance()

    def read_identifier(self) -> str:
        """Read field names and operators"""
        result = ''
        while self.current_char and (
            self.current_char.isalnum() or self.current_char in '._$'
        ):
            result += self.current_char
            self.advance()
        return result

    def read_string(self, quote_char: str) -> str:
        """Read quoted string values"""
        result = quote_char
        self.advance()  # consume opening quote

        while self.current_char and self.current_char != quote_char:
            if self.current_char == '\\' and self.peek() == quote_char:
                result += self.current_char
                self.advance()
                result += self.current_char
                self.advance()
            else:
                result += self.current_char
                self.advance()

        if self.current_char == quote_char:
            result += self.current_char
            self.advance()

        return result

    def read_array(self) -> str:
        """Read array values like [1,2,3]"""
        result = '['
        self.advance()  # consume opening bracket

        while self.current_char and self.current_char != ']':
            result += self.current_char
            self.advance()

        if self.current_char == ']':
            result += self.current_char
            self.advance()

        return result

    def read_number_or_identifier(self) -> str:
        """Read numbers or unquoted identifiers including datetime strings"""
        result = ''
        while self.current_char and (
            self.current_char.isalnum() or self.current_char in '._-:T'
        ):
            result += self.current_char
            self.advance()
        return result

    def get_next_token(self) -> Token:
        while self.current_char:
            if self.current_char.isspace():
                self.skip_whitespace()
                continue

            if self.current_char == '(':
                token = Token(TokenType.LPAREN, self.current_char, self.position)
                self.advance()
                return token

            if self.current_char == ')':
                token = Token(TokenType.RPAREN, self.current_char, self.position)
                self.advance()
                return token

            if self.current_char == '$':
                # Check if it's part of a logical operator like $and, $or
                if self.peek() and self.peek().isalpha():
                    # Read the full identifier including the $
                    identifier = self.current_char
                    self.advance()
                    while self.current_char and (
                        self.current_char.isalnum() or self.current_char in '_'
                    ):
                        identifier += self.current_char
                        self.advance()

                    # Check if it's a logical operator
                    if identifier in ['$and', '$or']:
                        return Token(
                            TokenType.LOGICAL_OP,
                            identifier,
                            self.position - len(identifier),
                        )
                    else:
                        # For OData query parameters like $expand, $join, etc.
                        return Token(
                            TokenType.DOLLAR,
                            identifier,
                            self.position - len(identifier),
                        )
                else:
                    # Single $ character
                    token = Token(TokenType.DOLLAR, self.current_char, self.position)
                    self.advance()
                    return token

            if self.current_char == '=':
                token = Token(TokenType.EQUALS, self.current_char, self.position)
                self.advance()
                return token

            if self.current_char == ',':
                token = Token(TokenType.COMMA, self.current_char, self.position)
                self.advance()
                return token

            if self.current_char == '&':
                token = Token(TokenType.AMPERSAND, self.current_char, self.position)
                self.advance()
                return token

            if self.current_char in '\'"':
                value = self.read_string(self.current_char)
                return Token(TokenType.VALUE, value, self.position - len(value))

            if self.current_char == '[':
                value = self.read_array()
                return Token(TokenType.VALUE, value, self.position - len(value))

            if self.current_char.isalpha() or self.current_char == '_':
                identifier = self.read_identifier()

                # Check if it's a logical operator
                if identifier in ['$and', '$or', 'AND', 'OR']:
                    return Token(
                        TokenType.LOGICAL_OP,
                        identifier,
                        self.position - len(identifier),
                    )

                # Check if it's an operator
                operators = ['eq', 'gt', 'lt', 'lte', 'gte', 'contains', 'in']
                if identifier in operators:
                    return Token(
                        TokenType.OPERATOR, identifier, self.position - len(identifier)
                    )

                # Must be a field name
                return Token(
                    TokenType.FIELD, identifier, self.position - len(identifier)
                )

            if self.current_char.isdigit() or self.current_char in '._-:T':
                value = self.read_number_or_identifier()
                return Token(TokenType.VALUE, value, self.position - len(value))

            raise ValueError(
                f'Unexpected character: {self.current_char} at position {self.position}'
            )

        return Token(TokenType.EOF, '', self.position)


class ODataParserABC(ABC):
    @abstractmethod
    def prepare_odata_filter(
        self, filter_expr: str, dynamic_var_char: str = '@'
    ) -> Tuple[str, dict]:
        pass

    @abstractmethod
    def prepare_odata_joins(
        self, odata_query: str, parent_table: str
    ) -> Tuple[str, List[str], str, Dict[str, Any]]:
        pass


class ODataQueryParser:
    """Unified parser for OData query parameters"""

    def __init__(self, type: str, dynamic_var_char: str = '@'):
        self.type = type
        self.dynamic_var_char = dynamic_var_char

        if self.type == 'sql':
            self.parser = SQLODataParser(self.dynamic_var_char)
        else:
            raise ValueError(f'Invalid type: {self.type}')

    def prepare_odata_filter(self, odata_filter: str) -> Dict[str, Any]:
        return self.parser.prepare_odata_filter(odata_filter)

    def prepare_odata_joins(
        self, odata_joins: str, parent_table: str
    ) -> Tuple[str, List[str], str, Dict[str, Any]]:
        return self.parser.prepare_odata_joins(odata_joins, parent_table)


class SQLFilterParser:
    """Unified parser for OData filter expressions and query parameters"""

    def __init__(self, lexer: Lexer, dynamic_var_char: str = '@'):
        self.lexer = lexer
        self.current_token = self.lexer.get_next_token()
        self.params = {}
        self.param_count = {}
        self.dynamic_var_char = dynamic_var_char

    def eat(self, token_type: TokenType):
        if self.current_token.type == token_type:
            self.current_token = self.lexer.get_next_token()
        else:
            raise ValueError(f'Expected {token_type}, got {self.current_token.type}')

    def parse_filter_expression(self) -> str:
        """Parse a complete filter expression"""
        if self.current_token.type == TokenType.EOF:
            return ''

        return self.parse_logical_expression()

    def parse_logical_expression(self) -> str:
        """Parse AND/OR expressions"""
        left = self.parse_comparison_expression()

        while self.current_token.type == TokenType.LOGICAL_OP:
            op = self.current_token.value
            self.eat(TokenType.LOGICAL_OP)
            right = self.parse_comparison_expression()

            # Convert OData logical operators to SQL
            sql_op = 'AND' if op in ['$and', 'AND'] else 'OR'
            left = f'{left} {sql_op} {right}'

        return left

    def parse_comparison_expression(self) -> str:
        """Parse comparison expressions like field eq value"""
        if self.current_token.type == TokenType.LPAREN:
            self.eat(TokenType.LPAREN)
            expr = self.parse_logical_expression()
            self.eat(TokenType.RPAREN)
            return f'({expr})'

        if self.current_token.type != TokenType.FIELD:
            raise ValueError(f'Expected field name, got {self.current_token.type}')

        field = self.current_token.value
        self.eat(TokenType.FIELD)

        if self.current_token.type != TokenType.OPERATOR:
            raise ValueError(f'Expected operator, got {self.current_token.type}')

        operator = self.current_token.value
        self.eat(TokenType.OPERATOR)

        if self.current_token.type != TokenType.VALUE:
            raise ValueError(f'Expected value, got {self.current_token.type}')

        value = self.current_token.value
        self.eat(TokenType.VALUE)

        return self.build_comparison(field, operator, value)

    def build_comparison(self, field: str, operator: str, value: str) -> str:
        """Build SQL comparison expression with parameter binding"""
        ops = {
            'eq': '=',
            'gt': '>',
            'lt': '<',
            'lte': '<=',
            'gte': '>=',
            'contains': 'LIKE',
            'in': 'IN',
        }

        if operator not in ops:
            raise ValueError(f'Unsupported operator: {operator}')

        # Generate parameter key - handle table aliases (e.g., "a.id" -> "a_id")
        if '.' in field:
            # For table aliases like "a.id", use "a_id" as parameter key
            table_alias, column_name = field.split('.', 1)
            base_param_key = f'{table_alias}_{column_name}'
        else:
            base_param_key = field

        if base_param_key in self.param_count:
            self.param_count[base_param_key] += 1
            param_key = f'{base_param_key}_{self.param_count[base_param_key]}'
        else:
            self.param_count[base_param_key] = 0
            param_key = base_param_key

        sql_op = ops[operator]

        if operator == 'contains':
            parsed_value = self.parse_value(value)
            self.params[param_key] = f'%{parsed_value}%'
            return f'{field} {sql_op} {self.dynamic_var_char}{param_key}'

        elif operator == 'in':
            # Parse array values
            items = value.strip('[]').split(',')
            parsed_values = [v.strip().strip('\'"') for v in items]

            placeholder_keys = []
            for idx, val in enumerate(parsed_values):
                item_key = f'{param_key}_{idx}'
                self.params[item_key] = val
                placeholder_keys.append(f'{self.dynamic_var_char}{item_key}')

            return f"{field} IN ({', '.join(placeholder_keys)})"

        else:
            parsed_value = self.parse_value(value)
            self.params[param_key] = parsed_value
            return f'{field} {sql_op} {self.dynamic_var_char}{param_key}'

    def parse_value(self, value: str) -> Any:
        """Parse value to appropriate Python type"""
        # Remove quotes if present
        was_quoted = False
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
            was_quoted = True

        # If it was quoted, treat as string unless it's a datetime
        if was_quoted:
            # Try to parse as datetime first
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
            return value

        # Try to parse as number
        if value.isdigit():
            return int(value)

        # Try to parse as float
        try:
            return float(value)
        except ValueError:
            pass

        # Try to parse as datetime
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass

        return value

    def parse_odata_query(self) -> Dict[str, Any]:
        """Parse OData query string and extract parameters"""
        if self.current_token.type == TokenType.EOF:
            return {}

        result = {}

        while self.current_token.type != TokenType.EOF:
            if self.current_token.type == TokenType.AMPERSAND:
                self.eat(TokenType.AMPERSAND)
                continue

            if self.current_token.type == TokenType.DOLLAR:
                # The DOLLAR token contains the full parameter name (e.g., '$expand', '$join')
                param_name = self.current_token.value[1:]  # Remove the '$' prefix
                self.eat(TokenType.DOLLAR)

                if self.current_token.type == TokenType.EQUALS:
                    self.eat(TokenType.EQUALS)
                    param_value = self.parse_parameter_value()

                    if param_name == 'expand':
                        expand_tables = self.parse_expand_value(param_value)
                        if expand_tables:
                            result['expand'] = expand_tables
                            # Also add the old format for backward compatibility
                            result['expand_tables'] = [
                                table['name'] for table in expand_tables
                            ]
                    elif param_name == 'join':
                        join_columns = self.parse_join_value(param_value)
                        if join_columns:
                            result['join'] = join_columns
                    elif param_name in ['filter', 'select', 'orderby', 'top', 'skip']:
                        # Skip other parameters for now
                        pass
                else:
                    raise ValueError(
                        f"Expected '=' after parameter name, got {self.current_token.type}"
                    )
            else:
                # Skip unknown tokens
                self.current_token = self.lexer.get_next_token()

        return result

    def parse_parameter_value(self) -> str:
        """Parse parameter value until next parameter or end"""
        value_parts = []
        paren_depth = 0

        while self.current_token.type != TokenType.EOF:
            if self.current_token.type == TokenType.AMPERSAND and paren_depth == 0:
                # Only stop at & if we're not inside parentheses
                break
            elif self.current_token.type == TokenType.DOLLAR and paren_depth == 0:
                # Only stop at $ if we're not inside parentheses
                break
            elif self.current_token.type == TokenType.LPAREN:
                paren_depth += 1
                value_parts.append(self.current_token.value)
            elif self.current_token.type == TokenType.RPAREN:
                paren_depth -= 1
                value_parts.append(self.current_token.value)
            elif self.current_token.type in [
                TokenType.VALUE,
                TokenType.FIELD,
                TokenType.COMMA,
                TokenType.OPERATOR,
                TokenType.EQUALS,
            ]:
                value_parts.append(self.current_token.value)
            elif self.current_token.type == TokenType.DOLLAR:
                # When inside parentheses, include $ tokens (like $filter=)
                value_parts.append(self.current_token.value)
            else:
                # Skip other tokens
                pass

            self.current_token = self.lexer.get_next_token()

        return ''.join(value_parts)

    def parse_expand_value(self, expand_value: str) -> List[Dict[str, Any]]:
        """Parse $expand parameter to extract table names and their filters"""
        tables = []

        # Split by comma, but be careful about commas inside parentheses
        parts = self._split_expand_parts(expand_value)

        for part in parts:
            # Extract the main table name (before any parentheses)
            table_name = part.split('(')[0].strip()
            if not table_name:
                continue

            table_info = {'name': table_name, 'filters': []}

            # Add the main table first
            tables.append(table_info)

            # Check for nested expands and filters within parentheses
            if '(' in part and ')' in part:
                # Extract content within parentheses
                nested_start = part.find('(') + 1
                nested_end = part.rfind(')')
                if nested_start < nested_end:
                    nested_content = part[nested_start:nested_end]

                    # Parse nested content for filters on the main table
                    # Only process filters if they are directly on this table (not nested)
                    if (
                        '$filter=' in nested_content
                        and '$expand=' not in nested_content
                    ):
                        filter_start = (
                            nested_content.find('$filter=') + 8
                        )  # Remove '$filter=' prefix
                        filter_end = nested_content.find('&', filter_start)
                        if filter_end == -1:
                            filter_end = len(nested_content)
                        filter_expr = nested_content[filter_start:filter_end].strip()
                        if filter_expr:
                            # Fix the filter expression by adding spaces between field, operator, and value
                            fixed_filter_expr = self._fix_filter_expression(filter_expr)
                            table_info['filters'].append(fixed_filter_expr)

                    # Parse nested expand content - remove $expand= prefix
                    if '$expand=' in nested_content:
                        expand_start = (
                            nested_content.find('$expand=') + 8
                        )  # Remove '$expand=' prefix
                        expand_end = nested_content.find('&', expand_start)
                        if expand_end == -1:
                            expand_end = len(nested_content)
                        nested_expand_content = nested_content[expand_start:expand_end]
                        # Recursively parse nested content
                        nested_tables = self._split_expand_parts(nested_expand_content)
                        for nested_table in nested_tables:
                            nested_table = nested_table.strip()
                            if nested_table and not nested_table.startswith('$'):
                                # Extract clean table name from nested table (remove any filter expressions)
                                clean_nested_table = nested_table.split('(')[0].strip()
                                nested_info = {
                                    'name': clean_nested_table,
                                    'filters': [],
                                }

                                # Check if this nested table has filters
                                if '(' in nested_table and ')' in nested_table:
                                    nested_table_start = nested_table.find('(') + 1
                                    nested_table_end = nested_table.rfind(')')
                                    if nested_table_start < nested_table_end:
                                        nested_table_content = nested_table[
                                            nested_table_start:nested_table_end
                                        ]
                                        if '$filter=' in nested_table_content:
                                            filter_start = (
                                                nested_table_content.find('$filter=')
                                                + 8
                                            )
                                            filter_end = nested_table_content.find(
                                                '&', filter_start
                                            )
                                            if filter_end == -1:
                                                filter_end = len(nested_table_content)
                                            filter_expr = nested_table_content[
                                                filter_start:filter_end
                                            ].strip()
                                            if filter_expr:
                                                fixed_filter_expr = (
                                                    self._fix_filter_expression(
                                                        filter_expr
                                                    )
                                                )
                                                nested_info['filters'].append(
                                                    fixed_filter_expr
                                                )

                                # Add nested tables after the main table
                                tables.append(nested_info)

        return tables

    def _fix_filter_expression(self, filter_expr: str) -> str:
        """Fix filter expression by adding spaces between field, operator, and value"""
        # Common OData operators
        operators = ['eq', 'gt', 'lt', 'lte', 'gte', 'contains', 'in', 'ne']

        for operator in operators:
            if operator in filter_expr:
                # Find the operator and add spaces around it
                op_index = filter_expr.find(operator)
                if op_index > 0:
                    # Check if there's already a space before the operator
                    if not filter_expr[op_index - 1].isspace():
                        filter_expr = (
                            filter_expr[:op_index] + ' ' + filter_expr[op_index:]
                        )
                        op_index += 1  # Adjust index after adding space
                    # Check if there's already a space after the operator
                    if (
                        op_index + len(operator) < len(filter_expr)
                        and not filter_expr[op_index + len(operator)].isspace()
                    ):
                        filter_expr = (
                            filter_expr[: op_index + len(operator)]
                            + ' '
                            + filter_expr[op_index + len(operator) :]
                        )
                break

        return filter_expr

    def get_expand_table_names(self, expand_value: str) -> List[str]:
        """Get just the table names for backward compatibility"""
        tables = self.parse_expand_value(expand_value)
        return [table['name'] for table in tables]

    def parse_join_value(self, join_value: str) -> List[str]:
        """Parse $join parameter to extract column names"""
        if not join_value:
            return []

        # Split by comma and clean up
        columns = [col.strip() for col in join_value.split(',') if col.strip()]
        return columns

    def _split_expand_parts(self, expand_value: str) -> List[str]:
        """Split expand value by comma, but respect parentheses"""
        parts = []
        current_part = ''
        paren_depth = 0

        for char in expand_value:
            if char == '(':
                paren_depth += 1
                current_part += char
            elif char == ')':
                paren_depth -= 1
                current_part += char
            elif char == ',' and paren_depth == 0:
                # Only split on comma if we're not inside parentheses
                parts.append(current_part.strip())
                current_part = ''
            else:
                current_part += char

        # Add the last part
        if current_part.strip():
            parts.append(current_part.strip())

        return parts


class SQLODataParser(ODataParserABC):
    def __init__(self, dynamic_var_char: str = '@'):
        self.dynamic_var_char = dynamic_var_char

    def prepare_odata_filter(self, filter_expr: str) -> Tuple[str, dict]:
        """Parses an OData-like filter expression and converts it into a SQL-like query with parameters."""
        if not filter_expr:
            return None, None

        lexer = Lexer(filter_expr)
        parser = SQLFilterParser(lexer, self.dynamic_var_char)

        sql_expr = parser.parse_filter_expression()

        if not sql_expr:
            raise ValueError('Invalid filter expression')

        return sql_expr, parser.params

    def prepare_odata_joins(
        self, odata_query: str, parent_table: str
    ) -> Tuple[str, List[str], str, Dict[str, Any]]:
        """Parses OData query parameters including $expand and $join and generates SQL JOIN statements."""
        if not odata_query:
            return '', [], '', {}

        lexer = Lexer(odata_query)
        query_parser = SQLFilterParser(lexer, self.dynamic_var_char)

        query_params = query_parser.parse_odata_query()

        expand_tables = query_params.get('expand', [])
        join_columns = query_params.get('join', [])

        join_builder = JoinBuilder(self.dynamic_var_char)
        join_sql, table_aliases, where_clause, filter_params = join_builder.build_joins(
            expand_tables, join_columns, parent_table
        )

        return join_sql, table_aliases, where_clause, filter_params


class JoinBuilder:
    """Builds SQL JOIN statements from OData expand and join parameters"""

    def __init__(self, dynamic_var_char: str = '@'):
        self.dynamic_var_char = dynamic_var_char

    def build_joins(
        self,
        expand_tables: List[Dict[str, Any]],
        join_columns: List[str],
        parent_table: str,
    ) -> Tuple[str, List[str], str, Dict[str, Any]]:
        """
        Build SQL JOIN statements with filters

        Args:
            expand_tables: List of table info dicts with names and filters
            join_columns: List of join columns (e.g., ['customer_id', 'order_id'])
            parent_table: The parent table name

        Returns:
            Tuple of (join_sql, table_aliases, where_clause, filter_params)
        """
        if not expand_tables:
            return '', [], '', {}

        join_statements = []
        table_aliases = []
        where_clauses = []
        all_filter_params = {}

        # Extract table names for backward compatibility
        table_names = [
            table['name'] if isinstance(table, dict) else table
            for table in expand_tables
        ]

        # If no join columns provided, use 'id' for all joins
        if not join_columns:
            join_columns = ['id'] * len(table_names)

        # If only one column is provided, use it for all joins
        if len(join_columns) == 1:
            join_columns = join_columns * len(table_names)

        # Ensure we have enough columns for all tables
        while len(join_columns) < len(table_names):
            join_columns.append(join_columns[-1] if join_columns else 'id')

        # Build joins
        for i, table_info in enumerate(expand_tables):
            if isinstance(table_info, dict):
                table = table_info['name']
                filters = table_info.get('filters', [])
            else:
                # Backward compatibility for string table names
                table = table_info
                filters = []

            # Determine the join columns for this table
            # Special case: if we have exactly 2 join columns and only 1 table, use different column names
            if len(table_names) == 1 and len(join_columns) == 2:
                parent_column = join_columns[0]
                table_column = join_columns[1]
            else:
                # General case: use the same column name on both sides
                if i < len(join_columns):
                    join_column = join_columns[i]
                else:
                    # Use the last column if not enough provided
                    join_column = join_columns[-1] if join_columns else 'id'
                parent_column = join_column
                table_column = join_column

            # Build the JOIN statement
            if i == 0:
                # First join: parent_table -> table
                join_stmt = f'JOIN {table}\n    ON {parent_table}.{parent_column} = {table}.{table_column}'
            else:
                # Subsequent joins: previous_table -> current_table
                prev_table = table_names[i - 1]
                join_stmt = f'JOIN {table}\n    ON {prev_table}.{parent_column} = {table}.{table_column}'

            join_statements.append(join_stmt)
            table_aliases.append(table)

            # Process filters for this table
            for filter_expr in filters:
                if filter_expr:
                    # Parse the filter expression to get SQL and parameters
                    try:
                        # Create a new parser instance to avoid circular imports
                        filter_parser = SQLODataParser(self.dynamic_var_char)
                        sql_filter, filter_params = filter_parser.prepare_odata_filter(
                            filter_expr
                        )
                        if sql_filter:
                            # Prefix the filter with table name to avoid ambiguity
                            # Replace @param with @table_param_ to match the new parameter names
                            for key in filter_params.keys():
                                sql_filter = sql_filter.replace(
                                    f'@{key}', f'@{table}_{key}_'
                                )
                            where_clauses.append(f'{table}.{sql_filter}')
                            # Update parameter names to avoid conflicts
                            for key, value in filter_params.items():
                                new_key = f'{table}_{key}_'
                                all_filter_params[new_key] = value
                    except Exception as e:
                        # If filter parsing fails, log the error and skip it
                        print(f"Filter parsing failed for '{filter_expr}': {e}")
                        pass

        join_sql = '\n'.join(join_statements)
        where_clause = ' AND '.join(where_clauses) if where_clauses else ''

        return join_sql, table_aliases, where_clause, all_filter_params
