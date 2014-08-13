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

"""
A simple implementation of conc_persistence plug-in. It does not need any
database backend. Although it is not resistant to race conditions when accessing
a concrete data key, during normal operation this should be no problem as there
are no updates (new data are always written under a new key).

required config.xml entries:
<plugins>
...
    <conc_persistence>
        <module>default_conc_persistence</module>
    </conc_persistence>
...
</plugins>
"""

import hashlib
import time
import re

from abstract.conc_persistence import AbstractConcPersistence


def id_exists(id):
    """
    Tests whether passed id exists
    """
    # currently we assume that id (= prefix of md5 hash with 52^6 possible values)
    #  conflicts are very unlikely
    return False


def mk_short_id(s, min_length=6):
    """
    Generates a hash based on md5 but using [a-zA-Z0-9] characters and with
    limited length.

    arguments:ucnk_op_persistence
    s -- a string to be hashed
    min_length -- minimum length of the output hash
    """
    chars = (
        'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
        'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
        'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
        'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
    )
    x = long('0x' + hashlib.md5(s).hexdigest(), 16)
    ans = []
    while x > 0:
        p = x % len(chars)
        ans.append(chars[p])
        x /= len(chars)
    ans = ''.join([str(x) for x in ans])
    max_length = len(ans)
    i = min_length
    while id_exists(ans[:i]) and i < max_length:
        i += 1
    return ans[:i]


class ConcPersistence(AbstractConcPersistence):
    """
    This class stores user's queries in their internal form (see conccgi.q attribute).
    """

    def __init__(self, db):
        self.db = db

    def _mk_key(self, code):
        return 'concordance:%s' % (code, )

    def is_valid_id(self, data_id):
        """
        Returns True if data_id is a valid data identifier else False is returned

        arguments:
        data_id -- identifier to be tested
        """
        return bool(re.match(r'~[0-9a-zA-Z]+', data_id))

    def open(self, data_id):
        """
        Loads operation data according to the passed data_id argument.
        The data are assumed to be public (as are URL parameters of a query).

        arguments:
        data_id -- an unique ID of operation data

        returns:
        a dictionary containing operation data or None if nothing is found
        """
        return self.db.get(self._mk_key(data_id))

    def store(self, user_id, curr_data, prev_data=None):
        """
        Stores current operation (defined in curr_data) into the database. If also prev_date argument is
        provided then a comparison is performed and based on the result, new record is created and new
        ID is returned on nothing is done and current ID is returned.

        arguments:
        user_id -- database ID of the current user
        curr_data -- a dictionary containing operation data to be stored; currently at least 'q' entry must be present
        prev_data -- optional dictionary with previous operation data; again, 'q' entry must be there

        returns:
        new operation ID if a new record is created or current ID if no new operation is defined
        """
        if prev_data is None or curr_data['q'] != prev_data['q']:
            time_created = time.time()
            data_id = mk_short_id('%s' % time_created)
            curr_data['id'] = data_id

            self.db.set(self._mk_key(data_id), curr_data)
            latest_id = curr_data['id']
        else:
            latest_id = prev_data['id']

        return latest_id


def create_instance(settings, db):
    """
    Creates a plugin instance.
    """
    return ConcPersistence(db)