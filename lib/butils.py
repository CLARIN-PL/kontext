# Copyright (c) 2003-2013  Pavel Rychly, Milos Jakubicek, Jan Busta
# Copyright (c) 2014 Institute of the Czech National Corpus
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
# dated June, 1991.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import re
import manatee


class CQLDetectWithin(object):
    """
    A simplified parser to detect 'within' part of a CQL query.
    """

    @staticmethod
    def split_by_parentheses(s):
        if type(s) is tuple:
            return [s]
        return [v1 for v2 in [re.split(r'(\])', x) for x in re.split(r'(\[)', s)] for v1 in v2]

    @staticmethod
    def split_by_whitespace(s):
        items = re.split(r'\s+', s)
        return [item for sublist in zip(items, len(items) * [' ']) for item in sublist][:-1]

    def parse_lex_elems(self, s):
        i = 0
        ans = []
        curr_piece = ''
        state = 0   # '1' = opened ", '2' = opened '
        while i < len(s):
            if s[i] == '\\':
                curr_piece += s[i+1]
                i += 2
                continue
            if s[i] == '"':
                if state == 0:
                    ans.extend(self.split_by_whitespace(curr_piece))
                    curr_piece = ''
                    state = 1
                elif state == 1:
                    ans.append((curr_piece, 's'))  # tuple => string part of the query
                    curr_piece = ''
                    state = 0
                else:
                    raise Exception('syntax error')
            else:
                curr_piece += s[i]
            i += 1
        if len(curr_piece) > 0:
            ans.extend(self.split_by_whitespace(curr_piece))
        return ans

    @staticmethod
    def get_next_token(struct, start):
        for i in range(start + 1, len(struct)):
            if len(struct[i].strip()) > 0:
                return struct[i]
        return None

    @staticmethod
    def next_token_matches(struct, start, pattern):
        token = CQLDetectWithin.get_next_token(struct, start)
        if token:
            return re.match(pattern, token) is not None
        return False

    def get_within_part(self, s):
        def join_items(contains, items, idx):
            if idx is None:
                return None
            ans = []
            for item in items[idx:]:
                if type(item) is tuple:
                    ans.append(u'"%s"' % (item[0],))
                else:
                    ans.append(item)
            return u''.join(ans)

        return self.analyze(s, join_items)

    def analyze(self, s, on_hit):
        if type(s) in (str, unicode):
            struct = self.parse(s)
        else:
            struct = s
        last_p = None
        for i, item in enumerate(struct):
            if item is None:
                continue
            if item in (']', '['):
                last_p = item
            elif item in ('within', '!within', 'within!'):
                if self.next_token_matches(struct, i, r'\w+:'):
                    pass  # aligned corpus search
                elif self.next_token_matches(struct, i, r'<.+'):
                    return on_hit(True, struct, i)
                elif last_p in (']', None):
                    return on_hit(True, struct, i)
        return on_hit(False, struct, None)

    def parse(self, s):
        result = []
        ans = self.parse_lex_elems(s)
        for item in ans:
            x = self.split_by_parentheses(item)
            result.extend(x)
        result = [x for x in result if x != '']
        return result


def get_stack(num_skip=1):
    """
    Returns a list of all function calls leading up to this one.

    arguments:
    num_skip -- number of items to be skipped (default = 1 which is the most recent one, i.e. the get_stack call itself)
    """
    import inspect
    import os
    c = []
    for item in inspect.stack()[num_skip:]:
        c.append('%s(%s): %s()' % (os.path.realpath(item[1]), item[2], item[3]))
    return c


def log_stack(level='debug'):
    """
    Works in the similar way as get_stack() but the result is logged instead.

    arguments:
    level -- logging level to be used (default is 'debug')
    """
    import threading
    import logging
    fn = getattr(logging.getLogger('STACK'), level)
    stack = '\n'.join([''] + ['    %s' % s for s in get_stack(num_skip=2)])
    fn(*('(thread %s) --> %s' % (threading.current_thread().ident, stack),))


def manatee_min_version(ver):
    """
    Tests whether the provided version string represents a newer or
    equal version than the one currently configured.

    arguments:
    ver -- a version signature string 'X.Y.Z' (e.g. '2.130.7')
    """
    ver = int(''.join(map(lambda x: '%03d' % int(x), ver.split('.'))))
    actual = int(''.join(map(lambda x: '%03d' % int(x), manatee.version().split('-')[-1].split('.'))))
    return ver <= actual
