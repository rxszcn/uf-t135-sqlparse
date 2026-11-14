#
# Copyright (C) 2009-2020 the sqlparse authors and contributors
# <see AUTHORS file>
#
# This module is part of python-sqlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

"""Split a token stream into statements.

Procedural dialects wrap several statements in one block.  Whether a
semicolon ends the statement or just a statement inside a block depends on
the block nesting, so the splitter keeps a block stack.

Which keyword opens which block, and which keyword closes it again, is
described by a single table (:data:`_BLOCK_TABLE`).  Every entry is a
:class:`_BlockSpec`; the flags on it capture the dialect-specific quirks
that used to be scattered across ``if``/``elif`` chains:

* a block may only be recognized inside a body (``IF``, ``WHILE``, ...),
* a loop may need a confirmer before it starts (``FOR ... LOOP``,
  ``WHILE ... DO``),
* ``DECLARE`` only exists in a ``CREATE`` statement and only at top level,
* ``REPEAT`` is also a scalar function, so its opener is only considered in
  statement position, may arrive as a plain name, and is deferred until the
  next token proves that a body follows.

``UNTIL`` is a *pivot*: a keyword that belongs to a block and marks a
structural boundary, without changing the nesting.
"""

from sqlparse import sql
from sqlparse import tokens as T


class _BlockSpec:
    """One row of the block pairing table.

    A spec describes a block that is opened by a keyword (``openers``),
    optionally carries a structural marker (``pivots``) and is closed by
    one or more keywords (``closers``).  All values are normalized
    (uppercase, single-spaced) token values.

    ``needs_nesting``
        The block is only recognized while a body is open, i.e. while a
        block with ``provides_nesting`` is on the stack.  This keeps
        standalone loop/conditional keywords from opening blocks when no
        dialect would allow it.

    ``provides_nesting``
        Opening this block makes the nested control-flow blocks above
        recognizable.

    ``confirmed_by``
        The opener is only turned into a block when one of the given
        confirmers follows (``FOR ... LOOP``, ``WHILE ... DO``).

    ``statement_position``
        The opener is only recognized where a statement (or a block body
        statement) may start.

    ``accepts_name``
        The opener may also be a plain ``Name`` token.  MySQL's ``REPEAT``
        is such a word: it is also a scalar function, so it is not added
        to the global keyword table; the splitter recognizes it only in
        statement position.

    ``deferred``
        The opener is not applied immediately.  The next significant
        token confirms it, unless that token makes the construct an
        expression or a call (``REPEAT(...)``, ``repeat := 1``).

    ``create_only``
        The opener is only recognized within a ``CREATE`` statement.

    ``top_level``
        The opener is only recognized while the block stack is empty.
    """

    __slots__ = (
        'accepts_name',
        'closers',
        'confirmed_by',
        'create_only',
        'deferred',
        'name',
        'needs_nesting',
        'openers',
        'pivots',
        'provides_nesting',
        'statement_position',
        'top_level',
    )

    def __init__(self, name, openers=(), pivots=(), closers=(),
                 needs_nesting=False, provides_nesting=False,
                 confirmed_by=(), statement_position=False,
                 accepts_name=False, deferred=False,
                 create_only=False, top_level=False):
        self.name = name
        self.openers = openers
        self.pivots = pivots
        self.closers = closers
        self.needs_nesting = needs_nesting
        self.provides_nesting = provides_nesting
        self.confirmed_by = confirmed_by
        self.statement_position = statement_position
        self.accepts_name = accepts_name
        self.deferred = deferred
        self.create_only = create_only
        self.top_level = top_level


#: Block pairing table.  The order of the specs is the order in which
#: openers are tried when a token value is ambiguous.
_BLOCK_TABLE = (
    # A routine's declaration section.  It is neither a control-flow block
    # nor closed by its own keyword: a bare ``END`` terminates it, and a
    # following ``BEGIN`` turns it into the routine body (see
    # ``_open_begin``).
    _BlockSpec('DECLARE', openers=('DECLARE',), closers=('END',),
               create_only=True, top_level=True),
    _BlockSpec('BEGIN', openers=('BEGIN',), closers=('END',),
               provides_nesting=True),
    _BlockSpec('IF', openers=('IF',), closers=('END IF',),
               needs_nesting=True),
    _BlockSpec('CASE', openers=('CASE',), closers=('END CASE',),
               needs_nesting=True),
    _BlockSpec('LOOP', openers=('LOOP',), closers=('END LOOP',),
               needs_nesting=True),
    _BlockSpec('FOR', openers=('FOR',), closers=('END FOR', 'END LOOP'),
               needs_nesting=True, confirmed_by=('LOOP', 'DO')),
    _BlockSpec('WHILE', openers=('WHILE',), closers=('END WHILE', 'END LOOP'),
               needs_nesting=True, confirmed_by=('LOOP', 'DO')),
    # MySQL: ``REPEAT <body> UNTIL <condition> END REPEAT``.  UNTIL is a
    # pivot: it belongs to the block but does not change nesting.  The
    # block is self-delimiting, so it is recognized outside of BEGIN as
    # well (MySQL allows a routine body without BEGIN ... END).
    _BlockSpec('REPEAT', openers=('REPEAT',), pivots=('UNTIL',),
               closers=('END REPEAT',), provides_nesting=True,
               statement_position=True, accepts_name=True, deferred=True),
)


def _build_lookup(attribute):
    lookup = {}
    for spec in _BLOCK_TABLE:
        for value in getattr(spec, attribute):
            lookup.setdefault(value, []).append(spec)
    return lookup


_OPENERS = _build_lookup('openers')
_CLOSERS = {value: frozenset(spec.name for spec in specs)
            for value, specs in _build_lookup('closers').items()}
#: Structural markers that belong to a block but never change nesting.
_PIVOTS = frozenset(
    value for spec in _BLOCK_TABLE for value in spec.pivots)
_CONFIRMERS = frozenset(
    value for spec in _BLOCK_TABLE for value in spec.confirmed_by)

#: Opener values that are allowed to arrive as a plain ``Name`` token.
_NAME_OPENERS = frozenset(
    value for spec in _BLOCK_TABLE if spec.accepts_name
    for value in spec.openers)

#: Block names that make nested control-flow blocks recognizable.
_NESTING_PROVIDERS = frozenset(
    spec.name for spec in _BLOCK_TABLE if spec.provides_nesting)

#: A bare ``END`` carries no block keyword: it terminates the innermost
#: block (BEGIN, a CASE expression, ...).  This mirrors the historical
#: behavior and is the reason a block stack is required at all.
_INNERMOST_TERMINATOR = 'END'

#: Keywords that turn ``BEGIN`` into a transaction statement (issue826).
_TRANSACTION_KEYWORDS = frozenset((
    'TRANSACTION', 'WORK', 'TRAN', 'DISTRIBUTED', 'DEFERRED',
    'IMMEDIATE', 'EXCLUSIVE',
))

#: Values after which a new statement (or a block body statement) may start.
#: Used by openers with ``statement_position`` so that a word like
#: ``repeat`` used as a column or variable is not mistaken for a block.
_STATEMENT_STARTERS = frozenset((
    None, ';', ':', ')', 'BEGIN', 'THEN', 'ELSE', 'DO', 'LOOP',
    'END', 'END IF', 'END LOOP', 'END WHILE', 'END FOR', 'END CASE',
    'END REPEAT', 'REPEAT',
))

#: Keywords that may start the body of a deferred block.  A deferred
#: opener is only confirmed by one of these (or by a name: a label, an
#: assignment target or a procedure call).  This is what tells
#: ``REPEAT <statement>`` apart from the word ``repeat`` used in an
#: expression, e.g. ``CASE WHEN a THEN repeat ELSE 0 END``.
_BODY_START_KEYWORDS = frozenset((
    'ALTER', 'BEGIN', 'CALL', 'CASE', 'CLOSE', 'COMMIT', 'CONTINUE',
    'CREATE', 'DECLARE', 'DELETE', 'DO', 'DROP', 'EXEC', 'EXECUTE',
    'EXIT', 'FETCH', 'FOR', 'HANDLER', 'IF', 'INSERT', 'ITERATE',
    'LEAVE', 'LOOP', 'MERGE', 'OPEN', 'PERFORM', 'RAISE', 'RELEASE',
    'RENAME', 'REPEAT', 'REPLACE', 'RETURN', 'ROLLBACK', 'SAVEPOINT',
    'SELECT', 'SET', 'SHOW', 'SIGNAL', 'START', 'TRUNCATE', 'UNTIL',
    'UPDATE', 'UPSERT', 'USE', 'WHILE', 'WITH',
))


def _can_start_body(ttype, unified):
    """True if the token after a deferred opener can start its body."""
    if ttype is T.Name:
        return True
    return ttype in T.Keyword and unified in _BODY_START_KEYWORDS


class StatementSplitter:
    """Filter that split stream at individual statements"""

    def __init__(self):
        self._reset()

    def _reset(self):
        """Set the filter attributes to its default values"""
        self._block_stack = []
        self._parenthesis_level = 0
        self._unconfirmed_start = None
        self._pending_opener = None
        self._last_significant = None
        self._is_create = False
        self._seen_begin = False

        self.consume_ws = False
        self.tokens = []
        self.level = 0

    def _has_nesting_context(self):
        """True if a block that contains statements is currently open."""
        return any(name in _NESTING_PROVIDERS
                   for name in self._block_stack)

    def _at_statement_position(self):
        """True if the current token starts a statement or a block body."""
        return self._last_significant in _STATEMENT_STARTERS

    def _open_begin(self):
        """Handle BEGIN: a block start or a DECLARE -> BEGIN transition."""
        self._seen_begin = True
        # Transition DECLARE to BEGIN if present
        if self._block_stack and self._block_stack[-1] == 'DECLARE':
            self._block_stack.pop()
            self._block_stack.append('BEGIN')
            return 0
        self._block_stack.append('BEGIN')
        return 1

    def _close_statement_punctuation(self):
        """Handle a semicolon: end a standalone BEGIN and reset pending state."""
        self._unconfirmed_start = None
        if self._seen_begin:
            self._seen_begin = False
            if self._block_stack and self._block_stack[-1] == 'BEGIN':
                self._block_stack.pop()
                return -1
        return 0

    def _resolve_pending_opener(self, ttype, value):
        """Apply or cancel the deferred opener, if there is one."""
        name = self._pending_opener
        if name is None:
            return 0
        self._pending_opener = None

        # ``REPEAT(...)`` is the string function, ``repeat := 1`` or
        # ``repeat.x`` an assignment/qualified name: those are no blocks.
        # Only a token that can start a body confirms the opener.
        unified = ' '.join(value.upper().split())
        if not _can_start_body(ttype, unified):
            return 0

        self._block_stack.append(name)
        return 1

    def _match_closer(self, unified):
        """Close the innermost block if *unified* is one of its closers."""
        closers = _CLOSERS.get(unified)
        if closers and self._block_stack \
                and self._block_stack[-1] in closers:
            self._block_stack.pop()
            return -1

        if unified == _INNERMOST_TERMINATOR:
            if self._block_stack:
                self._block_stack.pop()
            return -1
        return 0

    def _apply_pairing(self, unified, is_name=False):
        """Consult the block pairing table for *unified*.

        Returns the bias for the current split level.
        """
        # "FOR ... LOOP" / "WHILE ... DO": the loop block only starts once
        # its confirmer shows up.
        if not is_name and unified in _CONFIRMERS:
            confirmed = self._unconfirmed_start
            self._unconfirmed_start = None
            if confirmed is not None and self._has_nesting_context():
                self._block_stack.append(confirmed)
                return 1

        for spec in _OPENERS.get(unified, ()):
            if is_name and not spec.accepts_name:
                continue
            if spec.create_only and not self._is_create:
                continue
            if spec.top_level and self._block_stack:
                continue
            if spec.needs_nesting and not self._has_nesting_context():
                continue
            if spec.statement_position and not self._at_statement_position():
                continue
            if spec.confirmed_by:
                self._unconfirmed_start = spec.name
                return 0
            if spec.deferred:
                self._pending_opener = spec.name
                return 0
            self._block_stack.append(spec.name)
            return 1

        if is_name:
            return 0

        if unified in _PIVOTS:
            # A pivot (UNTIL) belongs to the innermost block but never
            # changes nesting: it only ends the loop body, the block itself
            # stays open until its closer arrives.
            self._unconfirmed_start = None
            return 0

        return self._match_closer(unified)

    def _change_splitlevel(self, ttype, value):
        """Get the new split level (increase, decrease or remain equal)"""

        # Whitespace (including newlines) and comments never affect the
        # split level nor confirm or cancel a deferred opener.
        if ttype in T.Whitespace or ttype in T.Comment:
            return 0

        # Apply a deferred opener now that the following token is known.
        result = self._resolve_pending_opener(ttype, value)

        # Semicolon resets unconfirmed loop starters
        # and handles standalone BEGIN;
        if ttype is T.Punctuation and value == ';':
            return result + self._close_statement_punctuation()

        # parenthesis increase/decrease a level
        if ttype is T.Punctuation and value == '(':
            self._parenthesis_level += 1
            return result + 1
        elif ttype is T.Punctuation and value == ')':
            self._parenthesis_level = max(0, self._parenthesis_level - 1)
            return result - 1
        elif ttype is not T.Name and ttype not in T.Keyword:
            return result

        # Everything after here is a keyword or the plain Name that the
        # pairing table explicitly accepts (MySQL's REPEAT).  Multi-word
        # keywords keep their original spacing in ``value`` (e.g.
        # "END\t\nIF"), so normalize for the table lookups.
        unified = ' '.join(value.upper().split())

        if ttype is T.Name and unified not in _NAME_OPENERS:
            return result

        # DDL Create though can contain more words such as "or replace"
        if ttype is T.Keyword.DDL and unified.startswith('CREATE'):
            self._is_create = True
            return result

        # Handle BEGIN block start
        if unified == 'BEGIN' and ttype in T.Keyword:
            return result + self._open_begin()

        # Issue826: If we see a transaction keyword after BEGIN,
        # it's a transaction statement, not a block.
        if self._seen_begin and unified in _TRANSACTION_KEYWORDS:
            self._seen_begin = False
            if self._block_stack and self._block_stack[-1] == 'BEGIN':
                self._block_stack.pop()
                return result - 1
            return result

        # Everything else: consult the block pairing table.
        return result + self._apply_pairing(
            unified, is_name=(ttype is T.Name))

    def process(self, stream):
        """Process the stream"""
        EOS_TTYPE = T.Whitespace, T.Comment.Single

        # Run over all stream tokens
        for ttype, value in stream:
            # Yield token if we finished a statement and there's no whitespaces
            # It will count newline token as a non whitespace. In this context
            # whitespace ignores newlines.
            # why don't multi line comments also count?
            if self.consume_ws and ttype not in EOS_TTYPE:
                yield sql.Statement(self.tokens)

                # Reset filter and prepare to process next statement
                self._reset()

            # Change current split level (increase, decrease or remain equal)
            self.level += self._change_splitlevel(ttype, value)

            # Append the token to the current statement
            self.tokens.append(sql.Token(ttype, value))

            # Remember the last token that may open a statement so that
            # statement-position-only openers (REPEAT) can be recognized.
            # Keywords and names are compared case-insensitively.
            if ttype not in T.Whitespace and ttype not in T.Comment:
                if ttype in T.Keyword or ttype is T.Name:
                    self._last_significant = ' '.join(value.upper().split())
                else:
                    self._last_significant = value

            # Check if we get the end of a statement
            # Issue762: Allow GO (or "GO 2") as statement splitter.
            # When implementing a language toggle, it's not only to add
            # keywords it's also to change some rules, like this splitting
            # rule.
            # Issue809: Ignore semicolons inside BEGIN...END blocks, but handle
            # standalone BEGIN; as a transaction statement
            if ttype is T.Punctuation and value == ';':
                self._seen_begin = False
                # Split on semicolon if not inside a BEGIN...END block
                if self.level <= 0 and 'BEGIN' not in self._block_stack:
                    self.consume_ws = True
            elif ttype is T.Keyword and value.split()[0] == 'GO':
                self.consume_ws = True
            elif (ttype not in (T.Whitespace, T.Newline, T.Comment.Single,
                                T.Comment.Multiline)
                  and not (ttype is T.Keyword and value.upper() == 'BEGIN')):
                # Reset _seen_begin if we see a non-whitespace, non-comment
                # token but not for BEGIN itself (which just set the flag)
                self._seen_begin = False

        # Yield pending statement (if any)
        if self.tokens and not all(t.is_whitespace for t in self.tokens):
            yield sql.Statement(self.tokens)
