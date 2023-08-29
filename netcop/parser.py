"""
Netcop - NETwork COnfig Parser

This Python library helps navigating and querying textual (CLI-style) configs of
network devices.
"""

import fnmatch
import re
import sys
from ipaddress import ip_address, ip_network
from typing import Dict, Iterator, List, Optional, Tuple


# ====
class Conf:
    """
    Get subnode of the config tree by a string key
    A key can be either a single keyword or space-separated sequence of them.

    Consider this example config:
        interface Ethernet1/0/1
            ip address 10.0.0.1/24
            ip address 10.0.0.100/24 secondary
            spanning-tree enable

    The conf['interface'] lookup will return the following node:
        Ethernet1/0/1
            ip address 10.0.0.1/24
            ip address 10.0.0.100/24 secondary
            spanning-tree enable

    In case we use a sequence of keywords as a key like that:
        conf['interface Ethernet1/0/1 ip address']
    then the result would be:
        10.0.0.1/24
        10.0.0.100/24 secondary

    Moreover, the same result could be retrieved by multiple sequential lookups:
        conf['interface']['Ethernet1/0/1']['ip']['address']
    """

    __slots__ = ("_line", "_orig_line", "_lineno", "_trace", "_children", "_index")

    def __init__(self, text: str = "", lines: Optional[List[str]] = None):
        """
        Parse given config into a tree.
        Config may be either a text or a sequence of lines (e.g. filehandle).
        """
        self._line: Optional[str] = None
        self._orig_line: str = ""
        self._lineno = 0
        self._trace: Tuple[str, ...] = ()
        self._children: List[Conf] = []
        self._index: Dict[str, Tuple[str, List[Conf]]] = {}
        if text:
            self._parse(text.splitlines())
        elif lines:
            self._parse(lines)
        if self._children:
            self._line = ""

    @classmethod
    def _new(cls, line, lineno, children=(), orig_line=None) -> "Conf":
        ret = cls()
        ret._line = line
        ret._orig_line = orig_line or line or ""
        ret._lineno = lineno
        ret._children = list(children)
        return ret

    def _parse(self, lines: List[str]) -> None:
        stack = [(self, "")]

        for lineno, line in enumerate(lines):
            line = line.rstrip()
            m = re.match(r"(\s*)", line)
            if not m:
                # if is used to avoid unnesessary string formatting
                assert m, "regexp must always match, line %r" % line
            indent = m.group(1)
            if line == indent:
                continue
            node = Conf._new(line, lineno)
            if len(indent) > len(stack[-1][1]):
                stack[-1][0]._children.append(node)
                stack.append((node, indent))
            else:
                while len(indent) <= len(stack[-1][1]) and stack[-1][0] is not self:
                    stack.pop()
                stack[-1][0]._children.append(node)
                stack.append((node, indent))

    @staticmethod
    def _next_token(string):
        no_more = ("", "", "")
        if not string:
            return no_more
        items = string.split(None, 1)
        if not items:
            return no_more
        token = items[0]
        if token in ("{", "}", "#", "!"):
            return no_more
        rest = ""
        if len(items) == 2:
            rest = items[1]
        if token.endswith(";") and (rest == "" or rest.startswith(("#", "!"))):
            token = token[:-1]
        return token.lower(), token, rest

    @property
    def trace(self):
        """
        Get the string index of the node agaisnt root of the tree
        """
        return " ".join(self._trace)

    def __repr__(self):
        fmt_line = ""
        if self._line:
            fmt_line = repr(self._line)
        ret = f"{self.__class__.__name__}({fmt_line})"
        if self._trace or self._line is not None:
            ret += "[%r]" % self.trace
        return ret

    def dump(self, file=None, indent="  ", show_header=True):
        """
        Write the indented config subtree to a given file
        sys.stdout is used if file argument is unspecified.
        """
        if self._line is None:
            return
        if file is None:
            file = sys.stdout

        def _put_line(line, level):
            if indent is None:
                file.write(line + "\n")
            else:
                file.write((indent * level) + line.strip() + "\n")

        if self._trace and show_header:
            file.write("[%s]" % (self.trace))
            file.write("\n" if not self._line else " ")

        for line, level in self._iter_lines(-1, False):
            _put_line(line, level)

    def _iter_lines(self, depth, orig_lines):
        if self._line:
            yield (self._orig_line if orig_lines else self._line), depth
        for c in self._children:
            yield from c._iter_lines(depth + 1, orig_lines)

    def lines(self) -> List[str]:
        """
        Returns list of matched lines, relative to match prefix
        """
        return [line for line, _ in self._iter_lines(0, False)]

    def orig_lines(self) -> List[str]:
        """
        Returns list of original lines from the config that matched the prefix
        """
        return [line for line, _ in self._iter_lines(0, True)]

    def _ensure_scalar(self):
        self._reindex()
        if len(self._index) == 0:
            raise KeyError(
                "No entries in node [%r], line %d" % (self.trace, self._lineno)
            )
        if len(self._index) > 1:
            raise KeyError(
                "Multiple entries (%d) match the key [%r], line %d"
                % (
                    len(self._index),
                    self.trace,
                    self._lineno,
                )
            )
        return next(iter(self._index))

    def _reindex(self):
        if self._index:
            return
        index = {}
        token_lc, token, rest = self._next_token(self._line)
        if token:
            new = Conf._new(rest, self._lineno, self._children, self._orig_line)
            index[token_lc] = (token, [new])
        else:
            for c in self._children:
                token_lc, token, rest = self._next_token(c._line)
                if token:
                    new = Conf._new(rest, c._lineno, c._children, c._orig_line)
                    index.setdefault(token_lc, (token, []))[1].append(new)
        self._index = index

    def expand(self, key: str, return_conf: bool = False) -> Iterator[Tuple]:
        """
        Iterates over all possible paths in config by given :key selector with wildcards
        Returns tuples with the length equal to the number of wildcard placeholders in
        the :key.
        If :return_conf is set, the resulting tuples also contain the trailing Conf()
        object at their last element.

        Example:
            for ifname, ip in Conf.expand('interface po* ip address *'):
                # prints all the IPs assigned to port-channel interfaces one per line
                print(ifname, ip)
            for ifname, ip, conf in Conf.expand('interface po* ip address *', True):
                # the same, but only for primary IPs
                if not conf['secondary']:
                    print(ifname, ip)
        """
        if not key:
            if return_conf:
                yield (self,)  # type: ignore
            else:
                yield ()
            return
        self._reindex()
        _, token, rest = self._next_token(key)
        if token == "~":
            if rest:
                raise ValueError("'~' should be the last token in query")
            if self._line:
                yield (
                    self._line.strip(),
                    self._expand_cfg(self.trace + " " + self._line),
                ) if return_conf else (self._line.strip(),)
            else:
                for c in self._children:
                    assert c._line
                    yield (
                        c._line.strip(),
                        c._expand_cfg(self.trace + " " + c._line),
                    ) if return_conf else (c._line.strip(),)
        elif any(x in token for x in "*?["):
            for k in fnmatch.filter(self, token):
                for ret in self[k].expand(rest, return_conf):
                    yield (k, *ret)
        elif self[token]:
            for ret in self[token].expand(rest, return_conf):
                yield ret

    def _expand_cfg(self, trace_str: str) -> "Conf":
        ret = self._new(
            None if not self._children else "",
            self._lineno,
            self._children,
            self._orig_line,
        )
        ret._trace = tuple(trace_str.split())
        return ret

    # ==== dict-like API
    def __getitem__(self, key: str) -> "Conf":
        token_lc, _, rest = self._next_token(key)
        if not token_lc:
            return self
        self._reindex()
        pair = self._index.get(token_lc)
        if not pair:
            return Conf()
        token, ret_list = pair

        if len(ret_list) == 1:
            ret = ret_list[0]
        else:
            # ret_list can not be empty
            ret = Conf._new("", ret_list[0]._lineno, ret_list, ret_list[0]._orig_line)

        ret._trace = (*self._trace, token)

        if rest:
            return ret[rest]
        return ret

    def __iter__(self):
        """
        Get the sequence of unique keywords following the node
        """
        self._reindex()
        return (x[0] for x in self._index.values())

    def __len__(self):
        """
        Number of the unique keywords following the node
        """
        self._reindex()
        return len(self._index)

    def __contains__(self, key):
        """
        Whether the [key] operator return a non-empty node
        """
        self._reindex()
        return bool(self[key])

    def __bool__(self):
        """
        Whether the node is empty
        """
        return self._line is not None

    def __nonzero__(self):
        return self.__bool__()

    def items(self):
        """
        Get a sequence of (key, value) pairs just as with dict.
        keys are direct descendant strings, values are Conf subtrees
        """
        self._reindex()
        return ((k, self[k]) for k in self)

    def keys(self):
        """
        Get a sequence of direct descendant strings just as with dict.
        """
        self._reindex()
        return (x for x in self)

    def values(self):
        """
        Get a sequence of Conf subtrees
        """
        self._reindex()
        return (x[1] for x in self._index.values())

    def get(self, key, default=None, type=None):
        """
        Get the following keyword by the given path (key)
        Optinal arguments are the default value and type convertion procedure.
        """
        try:
            ret = self[key].word
        except KeyError:
            return default
        if type:
            return type(ret)
        return ret

    # ==== scalar API
    @property
    def word(self):
        """
        Get the single following keyword.
        In case there is no one or there are multiple ones, a KeyError is raised.
        """
        return self._ensure_scalar()

    @property
    def tail(self):
        """
        Get the following keywords in the config line as a single string.
        In case there is no single assosiated line one or there are multiple ones, a
        KeyError is raised.
        """
        self._ensure_scalar()
        items = []
        rest = self._line
        while rest:
            _, token, rest = self._next_token(rest)
            if token:
                items.append(token)
        return " ".join(items)

    @property
    def tails(self):
        return [x for x, in self.expand("~")]

    @property
    def quoted(self):
        """
        Get the quoted string (without surrounding quotes) directly following the node.
        If there is no quoted string following, returns just the next keyword,
        like .word.
        In case there is no single assosiated line one or there are multiple ones,
        a KeyError is raised.
        """
        self._ensure_scalar()
        assert self._line is not None
        quote_char = self._line[:1]
        try:
            if quote_char in ['"', "'"]:
                return self._line[1 : self._line.index(quote_char, 1)]
        except ValueError:
            raise ValueError(
                "No ending <%s> found in [%r], line %d: %r"
                % (quote_char, self.trace, self._lineno, self._line)
            )
        return next(iter(self))

    @property
    def int(self):
        """
        Get the single following keyword casted to int.
        In case there is no one or there are multiple ones, a KeyError is raised.
        """
        return int(self.word)

    @property
    def ints(self):
        """
        Get the list of all following keywords casted to int.
        TypeError may be raised in case there is a keyword that can not be casted.
        """
        return [int(x) for x in self]

    @property
    def lineno(self):
        """
        Get the number of the line in initial config text
        KeyError may be raised in case there is no corresponding line
        """
        self._ensure_scalar()
        return self._lineno

    @property
    def junos_list(self):
        """
        Get the list of following keywords surrounded in [ ]
        If there is no surrounding [ ], return the list of the single keyword that
        follows
        """
        self._ensure_scalar()
        assert self._line is not None
        if self._line.startswith("["):
            items = self.tail.split()
            if items[0] == "[" and items[-1] == "]":
                return items[1:-1]
        return [self.word]

    if "ip_address" in globals():

        @property
        def ip(self):
            """
            Get the single following ip as an IPAddress object.
            In case there is no one or there are multiple ones, a KeyError is raised.
            TypeError may be raised in case there is a keyword that can not be casted to
            the IPAddress type.
            """
            return ip_address(self.word)

        @property
        def ips(self):
            """
            Get the list of all following keywords casted to IPAddress.
            TypeError may be raised in case there is a keyword that can not be casted.
            """
            return [ip_address(x) for x in self]

        @property
        def cidr(self):
            """
            Get the single following IP network as an IPNetwork object.
            In case there is no one or there are multiple ones, a KeyError is raised.
            TypeError may be raised in case there is a keyword that can not be casted to
            the IPNetwork type.
            """
            return ip_network(self.word)

        @property
        def cidrs(self):
            """
            Get the list of all following keywords casted to IPNetwork.
            TypeError may be raised in case there is a keyword that can not be casted.
            """
            return [ip_network(x) for x in self]
