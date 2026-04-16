#
# Copyright (C) 2012-2023 The Python Software Foundation.
# See LICENSE.txt and CONTRIBUTORS.txt.
#
import codecs
from collections import deque
import contextlib
import csv
from glob import iglob as std_iglob
import io
import json
import logging
import os
import py_compile
import re
import socket
try:
    import ssl
except ImportError:  # pragma: no cover
    ssl = None
import subprocess
import sys
import tarfile
import tempfile
import textwrap

try:
    import threading
except ImportError:  # pragma: no cover
    import dummy_threading as threading
import time

from . import DistlibException
from .compat import (string_types, text_type, shutil, raw_input, StringIO, cache_from_source, urlopen, urljoin, httplib,
                     xmlrpclib, HTTPHandler, BaseConfigurator, valid_ident, Container, configparser, URLError, ZipFile,
                     fsdecode, unquote, urlparse)

logger = logging.getLogger(__name__)

#
# Requirement parsing code as per PEP 508
#

IDENTIFIER = re.compile(r'^([\w\.-]+)\s*')
VERSION_IDENTIFIER = re.compile(r'^([\w\.*+-]+)\s*')
COMPARE_OP = re.compile(r'^(<=?|>=?|={2,3}|[~!]=)\s*')
MARKER_OP = re.compile(r'^((<=?)|(>=?)|={2,3}|[~!]=|in|not\s+in)\s*')
OR = re.compile(r'^or\b\s*')
AND = re.compile(r'^and\b\s*')
NON_SPACE = re.compile(r'(\S+)\s*')
STRING_CHUNK = re.compile(r'([\s\w\.{}()*+#:;,/?!~`@$%^&=|<>\[\]-]+)')


def parse_marker(marker_string):
    """
    Parse a marker string and return a dictionary containing a marker expression.

    The dictionary will contain keys "op", "lhs" and "rhs" for non-terminals in
    the expression grammar, or strings. A string contained in quotes is to be
    interpreted as a literal string, and a string not contained in quotes is a
    variable (such as os_name).
    """

    def marker_var(remaining):
        # either identifier, or literal string
        m = IDENTIFIER.match(remaining)
        if m:
            result = m.groups()[0]
            remaining = remaining[m.end():]
        elif not remaining:
            raise SyntaxError('unexpected end of input')
        else:
            q = remaining[0]
            if q not in '\'"':
                raise SyntaxError('invalid expression: %s' % remaining)
            oq = '\'"'.replace(q, '')
            remaining = remaining[1:]
            parts = [q]
            while remaining:
                # either a string chunk, or oq, or q to terminate
                if remaining[0] == q:
                    break
                elif remaining[0] == oq:
                    parts.append(oq)
                    remaining = remaining[1:]
                else:
                    m = STRING_CHUNK.match(remaining)
                    if not m:
                        raise SyntaxError('error in string literal: %s' % remaining)
                    parts.append(m.groups()[0])
                    remaining = remaining[m.end():]
            else:
                s = ''.join(parts)
                raise SyntaxError('unterminated string: %s' % s)
            parts.append(q)
            result = ''.join(parts)
            remaining = remaining[1:].lstrip()  # skip past closing quote
        return result, remaining

    def marker_expr(remaining):
        if remaining and remaining[0] == '(':
            result, remaining = marker(remaining[1:].lstrip())
            if remaining[0] != ')':
                raise SyntaxError('unterminated parenthesis: %s' % remaining)
            remaining = remaining[1:].lstrip()
        else:
            lhs, remaining = marker_var(remaining)
            while remaining:
                m = MARKER_OP.match(remaining)
                if not m:
                    break
                op = m.groups()[0]
                remaining = remaining[m.end():]
                rhs, remaining = marker_var(remaining)
                lhs = {'op': op, 'lhs': lhs, 'rhs': rhs}
            result = lhs
        return result, remaining

    def marker_and(remaining):
        lhs, remaining = marker_expr(remaining)
        while remaining:
            m = AND.match(remaining)
            if not m:
                break
            remaining = remaining[m.end():]
            rhs, remaining = marker_expr(remaining)
            lhs = {'op': 'and', 'lhs': lhs, 'rhs': rhs}
        return lhs, remaining

    def marker(remaining):
        lhs, remaining = marker_and(remaining)
        while remaining:
            m = OR.match(remaining)
            if not m:
                break
            remaining = remaining[m.end():]
            rhs, remaining = marker_and(remaining)
            lhs = {'op': 'or', 'lhs': lhs, 'rhs': rhs}
        return lhs, remaining

    return marker(marker_string)


def parse_requirement(req):
    """
    Parse a requirement passed in as a string. Return a Container
    whose attributes contain the various parts of the requirement.
    """
    pass


def get_resources_dests(resources_root, rules):
    """Find destinations for resources files"""
    pass


def in_venv():
    if hasattr(sys, 'real_prefix'):
        # virtualenv venvs
        result = True
    else:
        # PEP 405 venvs
        result = sys.prefix != getattr(sys, 'base_prefix', sys.prefix)
    return result


def get_executable():
    # The __PYVENV_LAUNCHER__ dance is apparently no longer needed, as
    # changes to the stub launcher mean that sys.executable always points
    # to the stub on OS X
    #    if sys.platform == 'darwin' and ('__PYVENV_LAUNCHER__'
    #                                     in os.environ):
    #        result =  os.environ['__PYVENV_LAUNCHER__']
    #    else:
    #        result = sys.executable
    #    return result
    # Avoid normcasing: see issue #143
    # result = os.path.normcase(sys.executable)
    result = sys.executable
    if not isinstance(result, text_type):
        result = fsdecode(result)
    return result


def proceed(prompt, allowed_chars, error_prompt=None, default=None):
    pass


def extract_by_key(d, keys):
    pass


def read_exports(stream):
    pass


def write_exports(exports, stream):
    pass


@contextlib.contextmanager
def tempdir():
    pass


@contextlib.contextmanager
def chdir(d):
    cwd = os.getcwd()
    try:
        os.chdir(d)
        yield
    finally:
        os.chdir(cwd)


@contextlib.contextmanager
def socket_timeout(seconds=15):
    pass


class cached_property(object):

    def __init__(self, func):
        self.func = func
        # for attr in ('__name__', '__module__', '__doc__'):
        #     setattr(self, attr, getattr(func, attr, None))

    def __get__(self, obj, cls=None):
        if obj is None:
            return self
        value = self.func(obj)
        object.__setattr__(obj, self.func.__name__, value)
        # obj.__dict__[self.func.__name__] = value = self.func(obj)
        return value


def convert_path(pathname):
    """Return 'pathname' as a name that will work on the native filesystem.

    The path is split on '/' and put back together again using the current
    directory separator.  Needed because filenames in the setup script are
    always supplied in Unix style, and have to be converted to the local
    convention before we can actually use them in the filesystem.  Raises
    ValueError on non-Unix-ish systems if 'pathname' either starts or
    ends with a slash.
    """
    if os.sep == '/':
        return pathname
    if not pathname:
        return pathname
    if pathname[0] == '/':
        raise ValueError("path '%s' cannot be absolute" % pathname)
    if pathname[-1] == '/':
        raise ValueError("path '%s' cannot end with '/'" % pathname)

    paths = pathname.split('/')
    while os.curdir in paths:
        paths.remove(os.curdir)
    if not paths:
        return os.curdir
    return os.path.join(*paths)


class FileOperator(object):

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.ensured = set()
        self._init_record()

    def _init_record(self):
        self.record = False
        self.files_written = set()
        self.dirs_created = set()

    def record_as_written(self, path):
        if self.record:
            self.files_written.add(path)

    def newer(self, source, target):
        """Tell if the target is newer than the source.

        Returns true if 'source' exists and is more recently modified than
        'target', or if 'source' exists and 'target' doesn't.

        Returns false if both exist and 'target' is the same age or younger
        than 'source'. Raise PackagingFileError if 'source' does not exist.

        Note that this test is not very accurate: files created in the same
        second will have the same "age".
        """
        if not os.path.exists(source):
            raise DistlibException("file '%r' does not exist" % os.path.abspath(source))
        if not os.path.exists(target):
            return True

        return os.stat(source).st_mtime > os.stat(target).st_mtime

    def copy_file(self, infile, outfile, check=True):
        """Copy a file respecting dry-run and force flags.
        """
        self.ensure_dir(os.path.dirname(outfile))
        logger.info('Copying %s to %s', infile, outfile)
        if not self.dry_run:
            msg = None
            if check:
                if os.path.islink(outfile):
                    msg = '%s is a symlink' % outfile
                elif os.path.exists(outfile) and not os.path.isfile(outfile):
                    msg = '%s is a non-regular file' % outfile
            if msg:
                raise ValueError(msg + ' which would be overwritten')
            shutil.copyfile(infile, outfile)
        self.record_as_written(outfile)

    def copy_stream(self, instream, outfile, encoding=None):
        pass

    def write_binary_file(self, path, data):
        self.ensure_dir(os.path.dirname(path))
        if not self.dry_run:
            if os.path.exists(path):
                os.remove(path)
            with open(path, 'wb') as f:
                f.write(data)
        self.record_as_written(path)

    def write_text_file(self, path, data, encoding):
        pass

    def set_mode(self, bits, mask, files):
        if os.name == 'posix' or (os.name == 'java' and os._name == 'posix'):
            # Set the executable bits (owner, group, and world) on
            # all the files specified.
            for f in files:
                if self.dry_run:
                    logger.info("changing mode of %s", f)
                else:
                    mode = (os.stat(f).st_mode | bits) & mask
                    logger.info("changing mode of %s to %o", f, mode)
                    os.chmod(f, mode)

    set_executable_mode = lambda s, f: s.set_mode(0o555, 0o7777, f)

    def ensure_dir(self, path):
        path = os.path.abspath(path)
        if path not in self.ensured and not os.path.exists(path):
            self.ensured.add(path)
            d, f = os.path.split(path)
            self.ensure_dir(d)
            logger.info('Creating %s' % path)
            if not self.dry_run:
                os.mkdir(path)
            if self.record:
                self.dirs_created.add(path)

    def byte_compile(self, path, optimize=False, force=False, prefix=None, hashed_invalidation=False):
        pass

    def ensure_removed(self, path):
        pass

    def is_writable(self, path):
        pass

    def commit(self):
        """
        Commit recorded changes, turn off recording, return
        changes.
        """
        assert self.record
        result = self.files_written, self.dirs_created
        self._init_record()
        return result

    def rollback(self):
        if not self.dry_run:
            for f in list(self.files_written):
                if os.path.exists(f):
                    os.remove(f)
            # dirs should all be empty now, except perhaps for
            # __pycache__ subdirs
            # reverse so that subdirs appear before their parents
            dirs = sorted(self.dirs_created, reverse=True)
            for d in dirs:
                flist = os.listdir(d)
                if flist:
                    assert flist == ['__pycache__']
                    sd = os.path.join(d, flist[0])
                    os.rmdir(sd)
                os.rmdir(d)  # should fail if non-empty
        self._init_record()


def resolve(module_name, dotted_path):
    if module_name in sys.modules:
        mod = sys.modules[module_name]
    else:
        mod = __import__(module_name)
    if dotted_path is None:
        result = mod
    else:
        parts = dotted_path.split('.')
        result = getattr(mod, parts.pop(0))
        for p in parts:
            result = getattr(result, p)
    return result


class ExportEntry(object):

    def __init__(self, name, prefix, suffix, flags):
        self.name = name
        self.prefix = prefix
        self.suffix = suffix
        self.flags = flags

    @cached_property
    def value(self):
        return resolve(self.prefix, self.suffix)

    def __repr__(self):  # pragma: no cover
        return '<ExportEntry %s = %s:%s %s>' % (self.name, self.prefix, self.suffix, self.flags)

    def __eq__(self, other):
        if not isinstance(other, ExportEntry):
            result = False
        else:
            result = (self.name == other.name and self.prefix == other.prefix and self.suffix == other.suffix and
                      self.flags == other.flags)
        return result

    __hash__ = object.__hash__


ENTRY_RE = re.compile(
    r'''(?P<name>([^\[]\S*))
                      \s*=\s*(?P<callable>(\w+)([:\.]\w+)*)
                      \s*(\[\s*(?P<flags>[\w-]+(=\w+)?(,\s*\w+(=\w+)?)*)\s*\])?
                      ''', re.VERBOSE)


def get_export_entry(specification):
    m = ENTRY_RE.search(specification)
    if not m:
        result = None
        if '[' in specification or ']' in specification:
            raise DistlibException("Invalid specification "
                                   "'%s'" % specification)
    else:
        d = m.groupdict()
        name = d['name']
        path = d['callable']
        colons = path.count(':')
        if colons == 0:
            prefix, suffix = path, None
        else:
            if colons != 1:
                raise DistlibException("Invalid specification "
                                       "'%s'" % specification)
            prefix, suffix = path.split(':')
        flags = d['flags']
        if flags is None:
            if '[' in specification or ']' in specification:
                raise DistlibException("Invalid specification "
                                       "'%s'" % specification)
            flags = []
        else:
            flags = [f.strip() for f in flags.split(',')]
        result = ExportEntry(name, prefix, suffix, flags)
    return result


def get_cache_base(suffix=None):
    """
    Return the default base location for distlib caches. If the directory does
    not exist, it is created. Use the suffix provided for the base directory,
    and default to '.distlib' if it isn't provided.

    On Windows, if LOCALAPPDATA is defined in the environment, then it is
    assumed to be a directory, and will be the parent directory of the result.
    On POSIX, and on Windows if LOCALAPPDATA is not defined, the user's home
    directory - using os.expanduser('~') - will be the parent directory of
    the result.

    The result is just the directory '.distlib' in the parent directory as
    determined above, or with the name specified with ``suffix``.
    """
    if suffix is None:
        suffix = '.distlib'
    if os.name == 'nt' and 'LOCALAPPDATA' in os.environ:
        result = os.path.expandvars('$localappdata')
    else:
        # Assume posix, or old Windows
        result = os.path.expanduser('~')
    # we use 'isdir' instead of 'exists', because we want to
    # fail if there's a file with that name
    if os.path.isdir(result):
        usable = os.access(result, os.W_OK)
        if not usable:
            logger.warning('Directory exists but is not writable: %s', result)
    else:
        try:
            os.makedirs(result)
            usable = True
        except OSError:
            logger.warning('Unable to create %s', result, exc_info=True)
            usable = False
    if not usable:
        result = tempfile.mkdtemp()
        logger.warning('Default location unusable, using %s', result)
    return os.path.join(result, suffix)


def path_to_cache_dir(path, use_abspath=True):
    """
    Convert an absolute path to a directory name for use in a cache.

    The algorithm used is:

    #. On Windows, any ``':'`` in the drive is replaced with ``'---'``.
    #. Any occurrence of ``os.sep`` is replaced with ``'--'``.
    #. ``'.cache'`` is appended.
    """
    d, p = os.path.splitdrive(os.path.abspath(path) if use_abspath else path)
    if d:
        d = d.replace(':', '---')
    p = p.replace(os.sep, '--')
    return d + p + '.cache'


def ensure_slash(s):
    pass


def parse_credentials(netloc):
    pass


def get_process_umask():
    pass


def is_string_sequence(seq):
    pass


PROJECT_NAME_AND_VERSION = re.compile('([a-z0-9_]+([.-][a-z_][a-z0-9_]*)*)-'
                                      '([a-z0-9_.+-]+)', re.I)
PYTHON_VERSION = re.compile(r'-py(\d\.?\d?)')


def split_filename(filename, project_name=None):
    """
    Extract name, version, python version from a filename (no extension)

    Return name, version, pyver or None
    """
    pass


# Allow spaces in name because of legacy dists like "Twisted Core"
NAME_VERSION_RE = re.compile(r'(?P<name>[\w .-]+)\s*'
                             r'\(\s*(?P<ver>[^\s)]+)\)$')


def parse_name_and_version(p):
    """
    A utility method used to get name and version from a string.

    From e.g. a Provides-Dist value.

    :param p: A value in a form 'foo (1.0)'
    :return: The name and version as a tuple.
    """
    pass


def get_extras(requested, available):
    pass


#
# Extended metadata functionality
#


def _get_external_data(url):
    pass


_external_data_base_url = 'https://www.red-dove.com/pypi/projects/'


def get_project_data(name):
    pass


def get_package_data(name, version):
    pass


class Cache(object):
    """
    A class implementing a cache for resources that need to live in the file system
    e.g. shared libraries. This class was moved from resources to here because it
    could be used by other modules, e.g. the wheel module.
    """

    def __init__(self, base):
        """
        Initialise an instance.

        :param base: The base directory where the cache should be located.
        """
        # we use 'isdir' instead of 'exists', because we want to
        # fail if there's a file with that name
        if not os.path.isdir(base):  # pragma: no cover
            os.makedirs(base)
        if (os.stat(base).st_mode & 0o77) != 0:
            logger.warning('Directory \'%s\' is not private', base)
        self.base = os.path.abspath(os.path.normpath(base))

    def prefix_to_dir(self, prefix, use_abspath=True):
        """
        Converts a resource prefix to a directory name in the cache.
        """
        return path_to_cache_dir(prefix, use_abspath=use_abspath)

    def clear(self):
        """
        Clear the cache.
        """
        not_removed = []
        for fn in os.listdir(self.base):
            fn = os.path.join(self.base, fn)
            try:
                if os.path.islink(fn) or os.path.isfile(fn):
                    os.remove(fn)
                elif os.path.isdir(fn):
                    shutil.rmtree(fn)
            except Exception:
                not_removed.append(fn)
        return not_removed


class EventMixin(object):
    """
    A very simple publish/subscribe system.
    """

    def __init__(self):
        self._subscribers = {}

    def add(self, event, subscriber, append=True):
        """
        Add a subscriber for an event.

        :param event: The name of an event.
        :param subscriber: The subscriber to be added (and called when the
                           event is published).
        :param append: Whether to append or prepend the subscriber to an
                       existing subscriber list for the event.
        """
        subs = self._subscribers
        if event not in subs:
            subs[event] = deque([subscriber])
        else:
            sq = subs[event]
            if append:
                sq.append(subscriber)
            else:
                sq.appendleft(subscriber)

    def remove(self, event, subscriber):
        """
        Remove a subscriber for an event.

        :param event: The name of an event.
        :param subscriber: The subscriber to be removed.
        """
        subs = self._subscribers
        if event not in subs:
            raise ValueError('No subscribers: %r' % event)
        subs[event].remove(subscriber)

    def get_subscribers(self, event):
        """
        Return an iterator for the subscribers for an event.
        :param event: The event to return subscribers for.
        """
        pass

    def publish(self, event, *args, **kwargs):
        """
        Publish a event and return a list of values returned by its
        subscribers.

        :param event: The event to publish.
        :param args: The positional arguments to pass to the event's
                     subscribers.
        :param kwargs: The keyword arguments to pass to the event's
                       subscribers.
        """
        pass


#
# Simple sequencing
#
class Sequencer(object):

    def __init__(self):
        self._preds = {}
        self._succs = {}
        self._nodes = set()  # nodes with no preds/succs

    def add_node(self, node):
        pass

    def remove_node(self, node, edges=False):
        pass

    def add(self, pred, succ):
        assert pred != succ
        self._preds.setdefault(succ, set()).add(pred)
        self._succs.setdefault(pred, set()).add(succ)

    def remove(self, pred, succ):
        assert pred != succ
        try:
            preds = self._preds[succ]
            succs = self._succs[pred]
        except KeyError:  # pragma: no cover
            raise ValueError('%r not a successor of anything' % succ)
        try:
            preds.remove(pred)
            succs.remove(succ)
        except KeyError:  # pragma: no cover
            raise ValueError('%r not a successor of %r' % (succ, pred))

    def is_step(self, step):
        pass

    def get_steps(self, final):
        pass

    @property
    def strong_connections(self):
        # http://en.wikipedia.org/wiki/Tarjan%27s_strongly_connected_components_algorithm
        pass

    @property
    def dot(self):
        pass


#
# Unarchiving functionality for zip, tar, tgz, tbz, whl
#

ARCHIVE_EXTENSIONS = ('.tar.gz', '.tar.bz2', '.tar', '.zip', '.tgz', '.tbz', '.whl')


def unarchive(archive_filename, dest_dir, format=None, check=True):

    pass


def zip_dir(directory):
    """zip a directory tree into a BytesIO object"""
    pass


#
# Simple progress bar
#

UNITS = ('', 'K', 'M', 'G', 'T', 'P')


class Progress(object):
    unknown = 'UNKNOWN'

    def __init__(self, minval=0, maxval=100):
        assert maxval is None or maxval >= minval
        self.min = self.cur = minval
        self.max = maxval
        self.started = None
        self.elapsed = 0
        self.done = False

    def update(self, curval):
        assert self.min <= curval
        assert self.max is None or curval <= self.max
        self.cur = curval
        now = time.time()
        if self.started is None:
            self.started = now
        else:
            self.elapsed = now - self.started

    def increment(self, incr):
        assert incr >= 0
        self.update(self.cur + incr)

    def start(self):
        self.update(self.min)
        return self

    def stop(self):
        if self.max is not None:
            self.update(self.max)
        self.done = True

    @property
    def maximum(self):
        pass

    @property
    def percentage(self):
        pass

    def format_duration(self, duration):
        pass

    @property
    def ETA(self):
        pass

    @property
    def speed(self):
        pass


#
# Glob functionality
#

RICH_GLOB = re.compile(r'\{([^}]*)\}')
_CHECK_RECURSIVE_GLOB = re.compile(r'[^/\\,{]\*\*|\*\*[^/\\,}]')
_CHECK_MISMATCH_SET = re.compile(r'^[^{]*\}|\{[^}]*$')


def iglob(path_glob):
    """Extended globbing function that supports ** and {opt1,opt2,opt3}."""
    pass


def _iglob(path_glob):
    pass


if ssl:
    from .compat import (HTTPSHandler as BaseHTTPSHandler, match_hostname, CertificateError)

    #
    # HTTPSConnection which verifies certificates/matches domains
    #

    class HTTPSConnection(httplib.HTTPSConnection):
        ca_certs = None  # set this to the path to the certs file (.pem)
        check_domain = True  # only used if ca_certs is not None

        # noinspection PyPropertyAccess
        def connect(self):
            sock = socket.create_connection((self.host, self.port), self.timeout)
            if getattr(self, '_tunnel_host', False):
                self.sock = sock
                self._tunnel()

            context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            if hasattr(ssl, 'OP_NO_SSLv2'):
                context.options |= ssl.OP_NO_SSLv2
            if getattr(self, 'cert_file', None):
                context.load_cert_chain(self.cert_file, self.key_file)
            kwargs = {}
            if self.ca_certs:
                context.verify_mode = ssl.CERT_REQUIRED
                context.load_verify_locations(cafile=self.ca_certs)
                if getattr(ssl, 'HAS_SNI', False):
                    kwargs['server_hostname'] = self.host

            self.sock = context.wrap_socket(sock, **kwargs)
            if self.ca_certs and self.check_domain:
                try:
                    match_hostname(self.sock.getpeercert(), self.host)
                    logger.debug('Host verified: %s', self.host)
                except CertificateError:  # pragma: no cover
                    self.sock.shutdown(socket.SHUT_RDWR)
                    self.sock.close()
                    raise

    class HTTPSHandler(BaseHTTPSHandler):

        def __init__(self, ca_certs, check_domain=True):
            BaseHTTPSHandler.__init__(self)
            self.ca_certs = ca_certs
            self.check_domain = check_domain

        def _conn_maker(self, *args, **kwargs):
            """
            This is called to create a connection instance. Normally you'd
            pass a connection class to do_open, but it doesn't actually check for
            a class, and just expects a callable. As long as we behave just as a
            constructor would have, we should be OK. If it ever changes so that
            we *must* pass a class, we'll create an UnsafeHTTPSConnection class
            which just sets check_domain to False in the class definition, and
            choose which one to pass to do_open.
            """
            pass

        def https_open(self, req):
            pass

    #
    # To prevent against mixing HTTP traffic with HTTPS (examples: A Man-In-The-
    # Middle proxy using HTTP listens on port 443, or an index mistakenly serves
    # HTML containing a http://xyz link when it should be https://xyz),
    # you can use the following handler class, which does not allow HTTP traffic.
    #
    # It works by inheriting from HTTPHandler - so build_opener won't add a
    # handler for HTTP itself.
    #
    class HTTPSOnlyHandler(HTTPSHandler, HTTPHandler):

        def http_open(self, req):
            raise URLError('Unexpected HTTP request on what should be a secure '
                           'connection: %s' % req)


#
# XML-RPC with timeouts
#
class Transport(xmlrpclib.Transport):

    def __init__(self, timeout, use_datetime=0):
        self.timeout = timeout
        xmlrpclib.Transport.__init__(self, use_datetime)

    def make_connection(self, host):
        pass


if ssl:

    class SafeTransport(xmlrpclib.SafeTransport):

        def __init__(self, timeout, use_datetime=0):
            self.timeout = timeout
            xmlrpclib.SafeTransport.__init__(self, use_datetime)

        def make_connection(self, host):
            pass


class ServerProxy(xmlrpclib.ServerProxy):

    def __init__(self, uri, **kwargs):
        self.timeout = timeout = kwargs.pop('timeout', None)
        # The above classes only come into play if a timeout
        # is specified
        if timeout is not None:
            # scheme = splittype(uri)  # deprecated as of Python 3.8
            scheme = urlparse(uri)[0]
            use_datetime = kwargs.get('use_datetime', 0)
            if scheme == 'https':
                tcls = SafeTransport
            else:
                tcls = Transport
            kwargs['transport'] = t = tcls(timeout, use_datetime=use_datetime)
            self.transport = t
        xmlrpclib.ServerProxy.__init__(self, uri, **kwargs)


#
# CSV functionality. This is provided because on 2.x, the csv module can't
# handle Unicode. However, we need to deal with Unicode in e.g. RECORD files.
#


def _csv_open(fn, mode, **kwargs):
    pass


class CSVBase(object):
    defaults = {
        'delimiter': str(','),  # The strs are used because we need native
        'quotechar': str('"'),  # str in the csv API (2.x won't take
        'lineterminator': str('\n')  # Unicode)
    }

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.stream.close()


class CSVReader(CSVBase):

    def __init__(self, **kwargs):
        if 'stream' in kwargs:
            stream = kwargs['stream']
            if sys.version_info[0] >= 3:
                # needs to be a text stream
                stream = codecs.getreader('utf-8')(stream)
            self.stream = stream
        else:
            self.stream = _csv_open(kwargs['path'], 'r')
        self.reader = csv.reader(self.stream, **self.defaults)

    def __iter__(self):
        return self

    def next(self):
        result = next(self.reader)
        if sys.version_info[0] < 3:
            for i, item in enumerate(result):
                if not isinstance(item, text_type):
                    result[i] = item.decode('utf-8')
        return result

    __next__ = next


class CSVWriter(CSVBase):

    def __init__(self, fn, **kwargs):
        self.stream = _csv_open(fn, 'w')
        self.writer = csv.writer(self.stream, **self.defaults)

    def writerow(self, row):
        pass


#
#   Configurator functionality
#


class Configurator(BaseConfigurator):

    value_converters = dict(BaseConfigurator.value_converters)
    value_converters['inc'] = 'inc_convert'

    def __init__(self, config, base=None):
        super(Configurator, self).__init__(config)
        self.base = base or os.getcwd()

    def configure_custom(self, config):

        def convert(o):
            if isinstance(o, (list, tuple)):
                result = type(o)([convert(i) for i in o])
            elif isinstance(o, dict):
                if '()' in o:
                    result = self.configure_custom(o)
                else:
                    result = {}
                    for k in o:
                        result[k] = convert(o[k])
            else:
                result = self.convert(o)
            return result

        c = config.pop('()')
        if not callable(c):
            c = self.resolve(c)
        props = config.pop('.', None)
        # Check for valid identifiers
        args = config.pop('[]', ())
        if args:
            args = tuple([convert(o) for o in args])
        items = [(k, convert(config[k])) for k in config if valid_ident(k)]
        kwargs = dict(items)
        result = c(*args, **kwargs)
        if props:
            for n, v in props.items():
                setattr(result, n, convert(v))
        return result

    def __getitem__(self, key):
        result = self.config[key]
        if isinstance(result, dict) and '()' in result:
            self.config[key] = result = self.configure_custom(result)
        return result

    def inc_convert(self, value):
        """Default converter for the inc:// protocol."""
        pass


class SubprocessMixin(object):
    """
    Mixin for running subprocesses and capturing their output
    """

    def __init__(self, verbose=False, progress=None):
        self.verbose = verbose
        self.progress = progress

    def reader(self, stream, context):
        """
        Read lines from a subprocess' output stream and either pass to a progress
        callable (if specified) or write progress information to sys.stderr.
        """
        progress = self.progress
        verbose = self.verbose
        while True:
            s = stream.readline()
            if not s:
                break
            if progress is not None:
                progress(s, context)
            else:
                if not verbose:
                    sys.stderr.write('.')
                else:
                    sys.stderr.write(s.decode('utf-8'))
                sys.stderr.flush()
        stream.close()

    def run_command(self, cmd, **kwargs):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        t1 = threading.Thread(target=self.reader, args=(p.stdout, 'stdout'))
        t1.start()
        t2 = threading.Thread(target=self.reader, args=(p.stderr, 'stderr'))
        t2.start()
        p.wait()
        t1.join()
        t2.join()
        if self.progress is not None:
            self.progress('done.', 'main')
        elif self.verbose:
            sys.stderr.write('done.\n')
        return p


def normalize_name(name):
    """Normalize a python package name a la PEP 503"""
    # https://www.python.org/dev/peps/pep-0503/#normalized-names
    return re.sub('[-_.]+', '-', name).lower()


# def _get_pypirc_command():
# """
# Get the distutils command for interacting with PyPI configurations.
# :return: the command.
# """
# from distutils.core import Distribution
# from distutils.config import PyPIRCCommand
# d = Distribution()
# return PyPIRCCommand(d)


class PyPIRCFile(object):

    DEFAULT_REPOSITORY = 'https://upload.pypi.org/legacy/'
    DEFAULT_REALM = 'pypi'

    def __init__(self, fn=None, url=None):
        if fn is None:
            fn = os.path.join(os.path.expanduser('~'), '.pypirc')
        self.filename = fn
        self.url = url

    def read(self):
        result = {}

        if os.path.exists(self.filename):
            repository = self.url or self.DEFAULT_REPOSITORY

            config = configparser.RawConfigParser()
            config.read(self.filename)
            sections = config.sections()
            if 'distutils' in sections:
                # let's get the list of servers
                index_servers = config.get('distutils', 'index-servers')
                _servers = [server.strip() for server in index_servers.split('\n') if server.strip() != '']
                if _servers == []:
                    # nothing set, let's try to get the default pypi
                    if 'pypi' in sections:
                        _servers = ['pypi']
                else:
                    for server in _servers:
                        result = {'server': server}
                        result['username'] = config.get(server, 'username')

                        # optional params
                        for key, default in (('repository', self.DEFAULT_REPOSITORY), ('realm', self.DEFAULT_REALM),
                                             ('password', None)):
                            if config.has_option(server, key):
                                result[key] = config.get(server, key)
                            else:
                                result[key] = default

                        # work around people having "repository" for the "pypi"
                        # section of their config set to the HTTP (rather than
                        # HTTPS) URL
                        if (server == 'pypi' and repository in (self.DEFAULT_REPOSITORY, 'pypi')):
                            result['repository'] = self.DEFAULT_REPOSITORY
                        elif (result['server'] != repository and result['repository'] != repository):
                            result = {}
            elif 'server-login' in sections:
                # old format
                server = 'server-login'
                if config.has_option(server, 'repository'):
                    repository = config.get(server, 'repository')
                else:
                    repository = self.DEFAULT_REPOSITORY
                result = {
                    'username': config.get(server, 'username'),
                    'password': config.get(server, 'password'),
                    'repository': repository,
                    'server': server,
                    'realm': self.DEFAULT_REALM
                }
        return result

    def update(self, username, password):
        # import pdb; pdb.set_trace()
        config = configparser.RawConfigParser()
        fn = self.filename
        config.read(fn)
        if not config.has_section('pypi'):
            config.add_section('pypi')
        config.set('pypi', 'username', username)
        config.set('pypi', 'password', password)
        with open(fn, 'w') as f:
            config.write(f)


def _load_pypirc(index):
    """
    Read the PyPI access configuration as supported by distutils.
    """
    pass


def _store_pypirc(index):
    pass


#
# get_platform()/get_host_platform() copied from Python 3.10.a0 source, with some minor
# tweaks
#


def get_host_platform():
    """Return a string that identifies the current platform.  This is used mainly to
    distinguish platform-specific build directories and platform-specific built
    distributions.  Typically includes the OS name and version and the
    architecture (as supplied by 'os.uname()'), although the exact information
    included depends on the OS; eg. on Linux, the kernel version isn't
    particularly important.

    Examples of returned values:
       linux-i586
       linux-alpha (?)
       solaris-2.6-sun4u

    Windows will return one of:
       win-amd64 (64bit Windows on AMD64 (aka x86_64, Intel64, EM64T, etc)
       win32 (all others - specifically, sys.platform is returned)

    For other non-POSIX platforms, currently just returns 'sys.platform'.

    """
    if os.name == 'nt':
        if 'amd64' in sys.version.lower():
            return 'win-amd64'
        if '(arm)' in sys.version.lower():
            return 'win-arm32'
        if '(arm64)' in sys.version.lower():
            return 'win-arm64'
        return sys.platform

    # Set for cross builds explicitly
    if "_PYTHON_HOST_PLATFORM" in os.environ:
        return os.environ["_PYTHON_HOST_PLATFORM"]

    if os.name != 'posix' or not hasattr(os, 'uname'):
        # XXX what about the architecture? NT is Intel or Alpha,
        # Mac OS is M68k or PPC, etc.
        return sys.platform

    # Try to distinguish various flavours of Unix

    (osname, host, release, version, machine) = os.uname()

    # Convert the OS name to lowercase, remove '/' characters, and translate
    # spaces (for "Power Macintosh")
    osname = osname.lower().replace('/', '')
    machine = machine.replace(' ', '_').replace('/', '-')

    if osname[:5] == 'linux':
        # At least on Linux/Intel, 'machine' is the processor --
        # i386, etc.
        # XXX what about Alpha, SPARC, etc?
        return "%s-%s" % (osname, machine)

    elif osname[:5] == 'sunos':
        if release[0] >= '5':  # SunOS 5 == Solaris 2
            osname = 'solaris'
            release = '%d.%s' % (int(release[0]) - 3, release[2:])
            # We can't use 'platform.architecture()[0]' because a
            # bootstrap problem. We use a dict to get an error
            # if some suspicious happens.
            bitness = {2147483647: '32bit', 9223372036854775807: '64bit'}
            machine += '.%s' % bitness[sys.maxsize]
        # fall through to standard osname-release-machine representation
    elif osname[:3] == 'aix':
        from _aix_support import aix_platform
        return aix_platform()
    elif osname[:6] == 'cygwin':
        osname = 'cygwin'
        rel_re = re.compile(r'[\d.]+', re.ASCII)
        m = rel_re.match(release)
        if m:
            release = m.group()
    elif osname[:6] == 'darwin':
        import _osx_support
        try:
            from distutils import sysconfig
        except ImportError:
            import sysconfig
        osname, release, machine = _osx_support.get_platform_osx(sysconfig.get_config_vars(), osname, release, machine)

    return '%s-%s-%s' % (osname, release, machine)


_TARGET_TO_PLAT = {
    'x86': 'win32',
    'x64': 'win-amd64',
    'arm': 'win-arm32',
}


def get_platform():
    if os.name != 'nt':
        return get_host_platform()
    cross_compilation_target = os.environ.get('VSCMD_ARG_TGT_ARCH')
    if cross_compilation_target not in _TARGET_TO_PLAT:
        return get_host_platform()
    return _TARGET_TO_PLAT[cross_compilation_target]
