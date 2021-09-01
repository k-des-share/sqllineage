import re

from sqlparse.sql import Function, Identifier, IdentifierList, Parenthesis, Token
from sqlparse.tokens import Literal

from sqllineage.core.handlers.base import NextTokenBaseHandler
from sqllineage.core.lineage_result import LineageResult
from sqllineage.exceptions import SQLLineageException
from sqllineage.models import Table


class SourceHandler(NextTokenBaseHandler):
    SOURCE_TABLE_TOKENS = (
        r"FROM",
        # inspired by https://github.com/andialbrecht/sqlparse/blob/master/sqlparse/keywords.py
        r"((LEFT\s+|RIGHT\s+|FULL\s+)?(INNER\s+|OUTER\s+|STRAIGHT\s+)?|(CROSS\s+|NATURAL\s+)?)?JOIN",
    )

    def _indicate(self, token: Token) -> bool:
        # SELECT trim(BOTH '  ' FROM '  abc  '); Here FROM is not a source table flag
        return any(
            re.match(regex, token.normalized) for regex in self.SOURCE_TABLE_TOKENS
        ) and not isinstance(token.parent.parent, Function)

    def _handle(self, token: Token, lineage_result: LineageResult) -> None:
        if isinstance(token, Identifier):
            if isinstance(token.token_first(skip_cm=True), Parenthesis):
                # SELECT col1 FROM (SELECT col2 FROM tab1) dt, the subquery will be parsed as Identifier
                # and this Identifier's get_real_name method would return alias name dt
                # referring https://github.com/andialbrecht/sqlparse/issues/218 for further information
                pass
            else:
                lineage_result.read.add(Table.create(token))
        elif isinstance(token, IdentifierList):
            # This is to support join in ANSI-89 syntax
            for token in token.tokens:
                # when real name and alias name are the same, it means subquery here
                if (
                    isinstance(token, Identifier)
                    and token.get_real_name() != token.get_alias()
                ):
                    lineage_result.read.add(Table.create(token))
        elif isinstance(token, Parenthesis):
            # SELECT col1 FROM (SELECT col2 FROM tab1), the subquery will be parsed as Parenthesis
            # This syntax without alias for subquery is invalid in MySQL, while valid for SparkSQL
            pass
        elif token.ttype == Literal.String.Single:
            # The case when source is a path, like in "COPY tab1 FROM 's3://path'" which is valid Redshift SQL
            lineage_result.read.add(Table(token.value))
        else:
            raise SQLLineageException(
                "An Identifier is expected, got %s[value: %s] instead."
                % (type(token).__name__, token)
            )
