# Tests splitting functions.

import types
from io import StringIO

import pytest

import sqlparse


def test_split_semicolon():
    sql1 = 'select * from foo;'
    sql2 = "select * from foo where bar = 'foo;bar';"
    stmts = sqlparse.parse(''.join([sql1, sql2]))
    assert len(stmts) == 2
    assert str(stmts[0]) == sql1
    assert str(stmts[1]) == sql2


def test_split_backslash():
    stmts = sqlparse.parse("select '\'; select '\'';")
    assert len(stmts) == 2


@pytest.mark.parametrize('fn', ['function.sql',
                                'function_psql.sql',
                                'function_psql2.sql',
                                'function_psql3.sql',
                                'function_psql4.sql'])
def test_split_create_function(load_file, fn):
    sql = load_file(fn)
    stmts = sqlparse.parse(sql)
    assert len(stmts) == 1
    assert str(stmts[0]) == sql


def test_split_dashcomments(load_file):
    sql = load_file('dashcomment.sql')
    stmts = sqlparse.parse(sql)
    assert len(stmts) == 3
    assert ''.join(str(q) for q in stmts) == sql


@pytest.mark.parametrize('s', ['select foo; -- comment\n',
                               'select foo; -- comment\r',
                               'select foo; -- comment\r\n',
                               'select foo; -- comment'])
def test_split_dashcomments_eol(s):
    stmts = sqlparse.parse(s)
    assert len(stmts) == 1


def test_split_begintag(load_file):
    sql = load_file('begintag.sql')
    stmts = sqlparse.parse(sql)
    assert len(stmts) == 3
    assert ''.join(str(q) for q in stmts) == sql


def test_split_begintag_2(load_file):
    sql = load_file('begintag_2.sql')
    stmts = sqlparse.parse(sql)
    assert len(stmts) == 1
    assert ''.join(str(q) for q in stmts) == sql


def test_split_dropif():
    sql = 'DROP TABLE IF EXISTS FOO;\n\nSELECT * FROM BAR;'
    stmts = sqlparse.parse(sql)
    assert len(stmts) == 2
    assert ''.join(str(q) for q in stmts) == sql


def test_split_comment_with_umlaut():
    sql = ('select * from foo;\n'
           '-- Testing an umlaut: ä\n'
           'select * from bar;')
    stmts = sqlparse.parse(sql)
    assert len(stmts) == 2
    assert ''.join(str(q) for q in stmts) == sql


def test_split_comment_end_of_line():
    sql = ('select * from foo; -- foo\n'
           'select * from bar;')
    stmts = sqlparse.parse(sql)
    assert len(stmts) == 2
    assert ''.join(str(q) for q in stmts) == sql
    # make sure the comment belongs to first query
    assert str(stmts[0]) == 'select * from foo; -- foo\n'


def test_split_casewhen():
    sql = ("SELECT case when val = 1 then 2 else null end as foo;\n"
           "comment on table actor is 'The actor table.';")
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2


def test_split_casewhen_procedure(load_file):
    # see issue580
    stmts = sqlparse.split(load_file('casewhen_procedure.sql'))
    assert len(stmts) == 2


def test_split_cursor_declare():
    sql = ('DECLARE CURSOR "foo" AS SELECT 1;\n'
           'SELECT 2;')
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2


def test_split_if_function():  # see issue 33
    # don't let IF as a function confuse the splitter
    sql = ('CREATE TEMPORARY TABLE tmp '
           'SELECT IF(a=1, a, b) AS o FROM one; '
           'SELECT t FROM two')
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2


def test_split_stream():
    stream = StringIO("SELECT 1; SELECT 2;")
    stmts = sqlparse.parsestream(stream)
    assert isinstance(stmts, types.GeneratorType)
    assert len(list(stmts)) == 2


def test_split_encoding_parsestream():
    stream = StringIO("SELECT 1; SELECT 2;")
    stmts = list(sqlparse.parsestream(stream))
    assert isinstance(stmts[0].tokens[0].value, str)


def test_split_unicode_parsestream():
    stream = StringIO('SELECT ö')
    stmts = list(sqlparse.parsestream(stream))
    assert str(stmts[0]) == 'SELECT ö'


def test_split_simple():
    stmts = sqlparse.split('select * from foo; select * from bar;')
    assert len(stmts) == 2
    assert stmts[0] == 'select * from foo;'
    assert stmts[1] == 'select * from bar;'


def test_split_ignores_empty_newlines():
    stmts = sqlparse.split('select foo;\nselect bar;\n')
    assert len(stmts) == 2
    assert stmts[0] == 'select foo;'
    assert stmts[1] == 'select bar;'


def test_split_quotes_with_new_line():
    stmts = sqlparse.split('select "foo\nbar"')
    assert len(stmts) == 1
    assert stmts[0] == 'select "foo\nbar"'

    stmts = sqlparse.split("select 'foo\n\bar'")
    assert len(stmts) == 1
    assert stmts[0] == "select 'foo\n\bar'"


def test_split_mysql_handler_for(load_file):
    # see issue581
    stmts = sqlparse.split(load_file('mysql_handler.sql'))
    assert len(stmts) == 2


@pytest.mark.parametrize('sql, expected', [
    ('select * from foo;', ['select * from foo']),
    ('select * from foo', ['select * from foo']),
    ('select * from foo; select * from bar;', [
        'select * from foo',
        'select * from bar',
    ]),
    ('  select * from foo;\n\nselect * from bar;\n\n\n\n', [
        'select * from foo',
        'select * from bar',
    ]),
    ('select * from foo\n\n;  bar', ['select * from foo', 'bar']),
])
def test_split_strip_semicolon(sql, expected):
    stmts = sqlparse.split(sql, strip_semicolon=True)
    assert len(stmts) == len(expected)
    for idx, expectation in enumerate(expected):
        assert stmts[idx] == expectation


def test_split_strip_semicolon_procedure(load_file):
    stmts = sqlparse.split(load_file('mysql_handler.sql'),
                           strip_semicolon=True)
    assert len(stmts) == 2
    assert stmts[0].endswith('end')
    assert stmts[1].endswith('end')

@pytest.mark.parametrize('sql, num', [
    ('USE foo;\nGO\nSELECT 1;\nGO', 4),
    ('SELECT * FROM foo;\nGO', 2),
    ('USE foo;\nGO 2\nSELECT 1;', 3)
])
def test_split_go(sql, num):  # issue762
    stmts = sqlparse.split(sql)
    assert len(stmts) == num


def test_split_multiple_case_in_begin(load_file):  # issue784
    stmts = sqlparse.split(load_file('multiple_case_in_begin.sql'))
    assert len(stmts) == 1


def test_split_if_exists_in_begin_end():  # issue812
    # IF EXISTS should not be confused with control flow IF
    sql = """CREATE TASK t1 AS
BEGIN
    CREATE OR REPLACE TABLE temp1;
    DROP TABLE IF EXISTS temp1;
END;
EXECUTE TASK t1;"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert 'CREATE TASK' in stmts[0]
    assert 'EXECUTE TASK' in stmts[1]


def test_split_begin_end_semicolons():  # issue809
    # Semicolons inside BEGIN...END blocks should not split statements
    sql = """WITH
FUNCTION meaning_of_life()
  RETURNS tinyint
  BEGIN
    DECLARE a tinyint DEFAULT CAST(6 as tinyint);
    DECLARE b tinyint DEFAULT CAST(7 as tinyint);
    RETURN a * b;
  END
SELECT meaning_of_life();"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 1
    assert 'WITH' in stmts[0]
    assert 'SELECT meaning_of_life()' in stmts[0]


def test_split_begin_end_procedure():  # issue809
    # Test with CREATE PROCEDURE (BigQuery style)
    sql = """CREATE OR REPLACE PROCEDURE mydataset.create_customer()
BEGIN
  DECLARE id STRING;
  SET id = GENERATE_UUID();
  INSERT INTO mydataset.customers (customer_id)
    VALUES(id);
  SELECT FORMAT("Created customer %s", id);
END;"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 1
    assert 'CREATE OR REPLACE PROCEDURE' in stmts[0]


def test_split_begin_transaction():  # issue826
    # BEGIN TRANSACTION should not be treated as a block start
    sql = """BEGIN TRANSACTION;
DELETE FROM "schema"."table_a" USING "table_a_temp" WHERE "schema"."table_a"."id" = "table_a_temp"."id";
INSERT INTO "schema"."table_a" SELECT * FROM "table_a_temp";
END TRANSACTION;"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 4
    assert stmts[0] == 'BEGIN TRANSACTION;'
    assert stmts[1].startswith('DELETE')
    assert stmts[2].startswith('INSERT')
    assert stmts[3] == 'END TRANSACTION;'


def test_split_begin_transaction_formatted():  # issue826
    # Test with formatted SQL (newlines between BEGIN and TRANSACTION)
    sql = """BEGIN
TRANSACTION;
DELETE FROM "schema"."table_a" USING "table_a_temp" WHERE "schema"."table_a"."id" = "table_a_temp"."id";
INSERT INTO "schema"."table_a" SELECT * FROM "table_a_temp";
END
TRANSACTION;"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 4
    assert stmts[0] == 'BEGIN\nTRANSACTION;'
    assert stmts[1].startswith('DELETE')
    assert stmts[2].startswith('INSERT')
    assert stmts[3] == 'END\nTRANSACTION;'


def test_split_anonymous_begin_end_for():  # issue845 Case 1
    sql = """
BEGIN
    SELECT 1;
    FOR R DO
        SELECT 1;
    END FOR;
END;
"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 1
    assert "END FOR;" in stmts[0]


def test_split_anonymous_begin_end_case_inline():  # issue845 Case 2
    sql = """
BEGIN
    SELECT 1;
    IF 1 THEN
        SELECT CASE WHEN 1 THEN 2 ELSE 3 END AS COUNT;
    ELSE
        SELECT 2;
    END IF;
END;
"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 1
    assert "END AS COUNT;" in stmts[0]


def test_split_for_update_in_begin_end():
    # Verify that FOR UPDATE / FOR SHARE inside a BEGIN ... END block do not break level balancing
    sql = """
BEGIN
    SELECT * FROM foo FOR UPDATE;
    SELECT * FROM bar FOR SHARE;
END;
SELECT 3;
"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert "SELECT 3;" in stmts[1]


def test_split_multiple_for_loops_in_begin_end():
    # Verify that multiple sequential loops inside a BEGIN ... END block balance correctly
    sql = """
BEGIN
    FOR x IN select_query LOOP
        SELECT 1;
    END LOOP;
    FOR y IN select_query LOOP
        SELECT 2;
    END LOOP;
END;
SELECT 3;
"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert "SELECT 3;" in stmts[1]


def test_split_procedural_case_end_case():
    # Verify that CASE closed by END CASE inside a BEGIN block balances correctly
    sql = """
BEGIN
    CASE val
        WHEN 1 THEN SELECT 'one';
        WHEN 2 THEN SELECT 'two';
        ELSE SELECT 'other';
    END CASE;
END;
SELECT 3;
"""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert "SELECT 3;" in stmts[1]


def test_split_standalone_for_update():
    # Verify that standalone FOR UPDATE statements split correctly
    sql = "SELECT * FROM foo FOR UPDATE; SELECT 3;"
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert stmts[0] == "SELECT * FROM foo FOR UPDATE;"
    assert stmts[1] == "SELECT 3;"


# ---------------------------------------------------------------------------
# Block pairing matrix: every control-flow block, standalone and inside a
# BEGIN ... END body.  A block inside a body has always been kept together
# with the enclosing statement; a standalone block has always been split at
# its inner semicolons.  Both shapes are pinned here so a change to the
# pairing table cannot regress one dialect while fixing another.
# ---------------------------------------------------------------------------
BLOCK_MATRIX = [
    # name, header, body statement, closing keyword
    ('if', 'IF x = 1 THEN', 'SET x = 1;', 'END IF'),
    ('while_do', 'WHILE x < 5 DO', 'SET x = x + 1;', 'END WHILE'),
    ('while_loop', 'WHILE x < 5 LOOP', 'x := x + 1;', 'END LOOP'),
    ('loop', 'LOOP', 'SELECT 1;', 'END LOOP'),
    ('for_loop', 'FOR i IN 1..10 LOOP', 'SELECT 1;', 'END LOOP'),
    ('for_do', 'FOR r DO', 'SELECT 1;', 'END FOR'),
    ('case', 'CASE x', 'WHEN 1 THEN SET y = 1;', 'END CASE'),
    ('repeat', 'REPEAT', 'SET x = x + 1;', 'UNTIL x > 10 END REPEAT'),
]


@pytest.mark.parametrize('name, header, body, closer', BLOCK_MATRIX)
def test_split_block_matrix_standalone(name, header, body, closer):
    """Standalone blocks keep their historical three-statement split.

    Every control-flow block except REPEAT was split at its inner
    semicolons before the pairing table existed; that behavior is kept
    verbatim.  REPEAT is paired now, so it forms one statement.
    """
    sql = f'{header}\n  {body}\n{closer};\nSELECT 2;'
    stmts = sqlparse.split(sql)
    assert stmts[-1] == 'SELECT 2;'
    if name == 'repeat':
        assert stmts == [f'{header}\n  {body}\n{closer};', 'SELECT 2;']
    else:
        assert stmts == [f'{header}\n  {body}', f'{closer};', 'SELECT 2;']


@pytest.mark.parametrize('name, header, body, closer', BLOCK_MATRIX)
def test_split_block_matrix_in_begin(name, header, body, closer):
    """A block inside BEGIN ... END stays part of the enclosing statement."""
    sql = (f'CREATE PROCEDURE p()\nBEGIN\n  {header}\n    {body}\n'
           f'  {closer};\n  SELECT 3;\nEND;\nSELECT 2;')
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2, (name, stmts)
    assert stmts[0].startswith('CREATE PROCEDURE p()')
    assert stmts[0].endswith('END;')
    assert stmts[1] == 'SELECT 2;'


# ---------------------------------------------------------------------------
# MySQL REPEAT ... UNTIL ... END REPEAT
# ---------------------------------------------------------------------------
def test_split_repeat_standalone():
    sql = 'REPEAT\n  SET x = x + 1;\nUNTIL x > 10 END REPEAT;\nSELECT 2;'
    stmts = sqlparse.split(sql)
    assert stmts == [
        'REPEAT\n  SET x = x + 1;\nUNTIL x > 10 END REPEAT;',
        'SELECT 2;',
    ]


def test_split_repeat_in_begin():
    sql = ('CREATE PROCEDURE p()\n'
           'BEGIN\n'
           '  REPEAT\n'
           '    SET x = x + 1;\n'
           '  UNTIL x > 10 END REPEAT;\n'
           'END;\n'
           'SELECT 2;')
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert stmts[0] == ('CREATE PROCEDURE p()\n'
                        'BEGIN\n'
                        '  REPEAT\n'
                        '    SET x = x + 1;\n'
                        '  UNTIL x > 10 END REPEAT;\n'
                        'END;')
    assert stmts[1] == 'SELECT 2;'


@pytest.mark.parametrize('sql', [
    # REPEAT containing WHILE ... DO
    ('BEGIN\n'
     '  REPEAT\n'
     '    WHILE x < 5 DO\n'
     '      SET x = x + 1;\n'
     '    END WHILE;\n'
     '  UNTIL x > 10 END REPEAT;\n'
     'END;\n'
     'SELECT 2;'),
    # ... same without the BEGIN wrapper
    ('REPEAT\n'
     '  WHILE x < 5 DO\n'
     '    SET x = x + 1;\n'
     '  END WHILE;\n'
     'UNTIL x > 10 END REPEAT;\n'
     'SELECT 2;'),
    # REPEAT containing IF
    ('BEGIN\n'
     '  REPEAT\n'
     '    IF x > 0 THEN\n'
     '      SET x = x - 1;\n'
     '    END IF;\n'
     '  UNTIL x = 0 END REPEAT;\n'
     'END;\n'
     'SELECT 2;'),
    # REPEAT containing LOOP
    ('BEGIN\n'
     '  REPEAT\n'
     '    LOOP\n'
     '      SET x = x + 1;\n'
     '    END LOOP;\n'
     '  UNTIL x > 10 END REPEAT;\n'
     'END;\n'
     'SELECT 2;'),
    # WHILE containing REPEAT
    ('BEGIN\n'
     '  WHILE x < 5 DO\n'
     '    REPEAT\n'
     '      SET y = y + 1;\n'
     '    UNTIL y > 3 END REPEAT;\n'
     '  END WHILE;\n'
     'END;\n'
     'SELECT 2;'),
    # REPEAT containing REPEAT
    ('BEGIN\n'
     '  REPEAT\n'
     '    REPEAT\n'
     '      SET x = x + 1;\n'
     '    UNTIL x > 5 END REPEAT;\n'
     '  UNTIL x > 10 END REPEAT;\n'
     'END;\n'
     'SELECT 2;'),
    # REPEAT containing a nested BEGIN ... END
    ('CREATE PROCEDURE p()\n'
     'BEGIN\n'
     '  REPEAT\n'
     '    BEGIN\n'
     '      SET x = x + 1;\n'
     '    END;\n'
     '  UNTIL x > 10 END REPEAT;\n'
     'END;\n'
     'SELECT 2;'),
])
def test_split_repeat_nested(sql):
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2, stmts
    assert stmts[-1] == 'SELECT 2;'


@pytest.mark.parametrize('until', [
    # CASE expression inside the UNTIL condition
    '(CASE WHEN x > 10 THEN 1 ELSE 0 END) = 1',
    'NOT (CASE WHEN x > 10 THEN x ELSE 0 END = x)',
    # multi-line CASE without parentheses
    'CASE\n    WHEN x > 10 THEN TRUE\n    ELSE FALSE\n  END',
    # subquery in the condition
    '(SELECT COUNT(*) FROM t WHERE t.x = x) > 5',
])
def test_split_repeat_until_expression(until):
    """END tokens inside the UNTIL condition must not close the block."""
    for template in (
        ('BEGIN\n  REPEAT\n    SET x = x + 1;\n  UNTIL {until} END REPEAT;\n'
         'END;\nSELECT 2;'),
        ('REPEAT\n  SET x = x + 1;\nUNTIL {until} END REPEAT;\nSELECT 2;'),
    ):
        sql = template.format(until=until)
        stmts = sqlparse.split(sql)
        assert len(stmts) == 2, (until, stmts)
        assert stmts[-1] == 'SELECT 2;'
        assert 'END REPEAT;' in stmts[0]


def test_split_repeat_case_in_body():
    """A CASE expression in the REPEAT body must not unbalance the block."""
    sql = ('CREATE PROCEDURE p()\n'
           'BEGIN\n'
           '  REPEAT\n'
           '    SET x = CASE WHEN y > 0 THEN 1 ELSE 2 END;\n'
           '  UNTIL x > 10 END REPEAT;\n'
           'END;\n'
           'SELECT 2;')
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert stmts[1] == 'SELECT 2;'


def test_split_repeat_single_statement():
    """MySQL allows a body statement without a trailing semicolon."""
    sql = 'REPEAT SET x = x + 1 UNTIL x > 10 END REPEAT;\nSELECT 2;'
    stmts = sqlparse.split(sql)
    assert stmts == ['REPEAT SET x = x + 1 UNTIL x > 10 END REPEAT;',
                     'SELECT 2;']


def test_split_repeat_labelled():
    sql = 'lbl: REPEAT\n  SET x = x + 1;\nUNTIL x > 10 END REPEAT lbl;\n' \
          'SELECT 2;'
    stmts = sqlparse.split(sql)
    assert stmts == [
        'lbl: REPEAT\n  SET x = x + 1;\nUNTIL x > 10 END REPEAT lbl;',
        'SELECT 2;',
    ]


@pytest.mark.parametrize('sql, last', [
    # REPEAT is also MySQL's string function.
    ("SELECT REPEAT('a', 3);\nSELECT 1;", 'SELECT 1;'),
    ("REPEAT('a', 3);\nSELECT 1;", 'SELECT 1;'),
    # ... and a perfectly valid column / variable name.
    ('SELECT repeat FROM t;\nSELECT 1;', 'SELECT 1;'),
    ('CREATE TABLE t (repeat int);\nSELECT 1;', 'SELECT 1;'),
    ('REPEAT.member = 1;\nSELECT 2;', 'SELECT 2;'),
    ('REPEAT[1] = 1;\nSELECT 2;', 'SELECT 2;'),
    ('REPEAT := 1;\nSELECT 2;', 'SELECT 2;'),
    # ... and a bare expression inside an enclosing CASE.
    ('SELECT CASE WHEN a THEN repeat ELSE 0 END AS x;\nSELECT 2;',
     'SELECT 2;'),
])
def test_split_repeat_lookalike(sql, last):
    """REPEAT used as a function or name must not open a block."""
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2, stmts
    assert stmts[-1] == last


def test_split_repeat_variable_in_procedure():
    sql = ('CREATE PROCEDURE p()\n'
           'BEGIN\n'
           '  DECLARE repeat INT;\n'
           '  SET repeat = 1;\n'
           'END;\n'
           'SELECT 1;')
    stmts = sqlparse.split(sql)
    assert len(stmts) == 2
    assert stmts[1] == 'SELECT 1;'


def test_split_repeat_procedure_body_without_begin():
    """MySQL allows a routine body without BEGIN ... END.

    The routine header and the REPEAT block stay together, and the
    standalone-block shape splits the same way as inside a BEGIN body.
    """
    sql = ('CREATE PROCEDURE p()\n'
           'REPEAT\n'
           '  SET x = x + 1;\n'
           'UNTIL x > 10 END REPEAT;\n'
           'SELECT 2;')
    stmts = sqlparse.split(sql)
    assert stmts == ['CREATE PROCEDURE p()\n'
                     'REPEAT\n'
                     '  SET x = x + 1;\n'
                     'UNTIL x > 10 END REPEAT;',
                     'SELECT 2;']


