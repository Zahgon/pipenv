"""
    pygments.util
    ~~~~~~~~~~~~~

    Utility functions.

    :copyright: Copyright 2006-2025 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re
from io import TextIOWrapper


split_path_re = re.compile(r'[/\\ ]')
doctype_lookup_re = re.compile(r'''
    <!DOCTYPE\s+(
     [a-zA-Z_][a-zA-Z0-9]*
     (?: \s+      # optional in HTML5
     [a-zA-Z_][a-zA-Z0-9]*\s+
     "[^"]*")?
     )
     [^>]*>
''', re.DOTALL | re.MULTILINE | re.VERBOSE)
tag_re = re.compile(r'<(.+?)(\s.*?)?>.*?</.+?>',
                    re.IGNORECASE | re.DOTALL | re.MULTILINE)
xml_decl_re = re.compile(r'\s*<\?xml[^>]*\?>', re.I)


class ClassNotFound(ValueError):
    """Raised if one of the lookup functions didn't find a matching class."""


class OptionError(Exception):
    """
    This exception will be raised by all option processing functions if
    the type or value of the argument is not correct.
    """

def get_choice_opt(options, optname, allowed, default=None, normcase=False):
    """
    If the key `optname` from the dictionary is not in the sequence
    `allowed`, raise an error, otherwise return it.
    """
    string = options.get(optname, default)
    if normcase:
        string = string.lower()
    if string not in allowed:
        raise OptionError('Value for option {} must be one of {}'.format(optname, ', '.join(map(str, allowed))))
    return string


def get_bool_opt(options, optname, default=None):
    """
    Intuitively, this is `options.get(optname, default)`, but restricted to
    Boolean value. The Booleans can be represented as string, in order to accept
    Boolean value from the command line arguments. If the key `optname` is
    present in the dictionary `options` and is not associated with a Boolean,
    raise an `OptionError`. If it is absent, `default` is returned instead.

    The valid string values for ``True`` are ``1``, ``yes``, ``true`` and
    ``on``, the ones for ``False`` are ``0``, ``no``, ``false`` and ``off``
    (matched case-insensitively).
    """
    string = options.get(optname, default)
    if isinstance(string, bool):
        return string
    elif isinstance(string, int):
        return bool(string)
    elif not isinstance(string, str):
        raise OptionError(f'Invalid type {string!r} for option {optname}; use '
                          '1/0, yes/no, true/false, on/off')
    elif string.lower() in ('1', 'yes', 'true', 'on'):
        return True
    elif string.lower() in ('0', 'no', 'false', 'off'):
        return False
    else:
        raise OptionError(f'Invalid value {string!r} for option {optname}; use '
                          '1/0, yes/no, true/false, on/off')


def get_int_opt(options, optname, default=None):
    """As :func:`get_bool_opt`, but interpret the value as an integer."""
    string = options.get(optname, default)
    try:
        return int(string)
    except TypeError:
        raise OptionError(f'Invalid type {string!r} for option {optname}; you '
                          'must give an integer value')
    except ValueError:
        raise OptionError(f'Invalid value {string!r} for option {optname}; you '
                          'must give an integer value')

def get_list_opt(options, optname, default=None):
    """
    If the key `optname` from the dictionary `options` is a string,
    split it at whitespace and return it. If it is already a list
    or a tuple, it is returned as a list.
    """
    val = options.get(optname, default)
    if isinstance(val, str):
        return val.split()
    elif isinstance(val, (list, tuple)):
        return list(val)
    else:
        raise OptionError(f'Invalid type {val!r} for option {optname}; you '
                          'must give a list value')


def docstring_headline(obj):
    pass


def make_analysator(f):
    """Return a static text analyser function that returns float values."""
    def text_analyse(text):
        pass
    text_analyse.__doc__ = f.__doc__
    return staticmethod(text_analyse)


def shebang_matches(text, regex):
    r"""Check if the given regular expression matches the last part of the
    shebang if one exists.

        >>> from pygments.util import shebang_matches
        >>> shebang_matches('#!/usr/bin/env python', r'python(2\.\d)?')
        True
        >>> shebang_matches('#!/usr/bin/python2.4', r'python(2\.\d)?')
        True
        >>> shebang_matches('#!/usr/bin/python-ruby', r'python(2\.\d)?')
        False
        >>> shebang_matches('#!/usr/bin/python/ruby', r'python(2\.\d)?')
        False
        >>> shebang_matches('#!/usr/bin/startsomethingwith python',
        ...                 r'python(2\.\d)?')
        True

    It also checks for common windows executable file extensions::

        >>> shebang_matches('#!C:\\Python2.4\\Python.exe', r'python(2\.\d)?')
        True

    Parameters (``'-f'`` or ``'--foo'`` are ignored so ``'perl'`` does
    the same as ``'perl -e'``)

    Note that this method automatically searches the whole string (eg:
    the regular expression is wrapped in ``'^$'``)
    """
    index = text.find('\n')
    if index >= 0:
        first_line = text[:index].lower()
    else:
        first_line = text.lower()
    if first_line.startswith('#!'):
        try:
            found = [x for x in split_path_re.split(first_line[2:].strip())
                     if x and not x.startswith('-')][-1]
        except IndexError:
            return False
        regex = re.compile(rf'^{regex}(\.(exe|cmd|bat|bin))?$', re.IGNORECASE)
        if regex.search(found) is not None:
            return True
    return False


def doctype_matches(text, regex):
    """Check if the doctype matches a regular expression (if present).

    Note that this method only checks the first part of a DOCTYPE.
    eg: 'html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
    """
    pass


def html_doctype_matches(text):
    """Check if the file looks like it has a html doctype."""
    pass


_looks_like_xml_cache = {}


def looks_like_xml(text):
    """Check if a doctype exists or if we have some tags."""
    pass


def surrogatepair(c):
    """Given a unicode character code with length greater than 16 bits,
    return the two 16 bit surrogate pair.
    """
    pass


def format_lines(var_name, seq, raw=False, indent_level=0):
    """Formats a sequence of strings for output."""
    pass


def duplicates_removed(it, already_seen=()):
    """
    Returns a list with duplicates removed from the iterable `it`.

    Order is preserved.
    """
    pass


class Future:
    """Generic class to defer some work.

    Handled specially in RegexLexerMeta, to support regex string construction at
    first use.
    """
    def get(self):
        raise NotImplementedError


def guess_decode(text):
    """Decode *text* with guessed encoding.

    First try UTF-8; this should fail for non-UTF-8 encodings.
    Then try the preferred locale encoding.
    Fall back to latin-1, which always works.
    """
    try:
        text = text.decode('utf-8')
        return text, 'utf-8'
    except UnicodeDecodeError:
        try:
            import locale
            prefencoding = locale.getpreferredencoding()
            text = text.decode()
            return text, prefencoding
        except (UnicodeDecodeError, LookupError):
            text = text.decode('latin1')
            return text, 'latin1'


def guess_decode_from_terminal(text, term):
    """Decode *text* coming from terminal *term*.

    First try the terminal encoding, if given.
    Then try UTF-8.  Then try the preferred locale encoding.
    Fall back to latin-1, which always works.
    """
    pass


def terminal_encoding(term):
    """Return our best guess of encoding for the given *term*."""
    pass


class UnclosingTextIOWrapper(TextIOWrapper):
    # Don't close underlying buffer on destruction.
    def close(self):
        self.flush()
