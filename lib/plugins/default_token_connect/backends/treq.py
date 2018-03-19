# Copyright (c) 2018 Charles University, Faculty of Arts,
#                    Institute of the Czech National Corpus
# Copyright (c) 2018 Tomas Machalek <tomas.machalek@gmail.com>
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

import json
import logging

from plugins.default_token_connect.backends.cache import cached
from plugins.default_token_connect.backends import HTTPBackend


AVAIL_GROUPS = {
    'cs': ('ACQUIS', 'CORE', 'EUROPARL', 'PRESSEUROP', 'SUBTITLES', 'SYNDICATE'),
    'en': ('ACQUIS', 'CORE', 'EUROPARL', 'PRESSEUROP', 'SUBTITLES', 'SYNDICATE'),
    'pl': ('ACQUIS', 'CORE', 'EUROPARL', 'PRESSEUROP', 'SUBTITLES'),
    'mk': ('CORE', 'SUBTITLES')
}

AVAIL_LANG_MAPPINGS = {   # TODO
    'en': ['cs', 'pl', 'de', 'mk'],
    'cs': ['en', 'mk', 'pl', 'de']
}


class TreqBackend(HTTPBackend):
    """
    Treq args:
        jazyk1:cs
        jazyk2:en
        hledejKde[]:ACQUIS
        hledejKde[]:CORE
        hledejKde[]:EUROPARL
        hledejKde[]:PRESSEUROP
        hledejKde[]:SUBTITLES
        hledejKde[]:SYNDICATE
        hledejCo:obnova
        searchGo:
    """

    DEFAULT_MAX_RESULT_LINES = 20

    def __init__(self, conf, ident):
        super(TreqBackend, self).__init__(conf, ident)
        self._conf = conf

    @staticmethod
    def _lang_from_corpname(corpname):
        return corpname.split('_')[-1]

    def _find_second_lang(self, corpora):
        """
        Find a first language+corpus with available translations
        for the primary language (= corpora[0]).
        """
        primary_lang = self._lang_from_corpname(corpora[0])
        translations = AVAIL_LANG_MAPPINGS.get(primary_lang, [])
        for cn in corpora[1:]:
            lang = self._lang_from_corpname(cn)
            if lang in translations:
                return cn, lang
        return None, None

    def enabled_for_corpora(self, corpora):
        corp1 = corpora[0]
        corp2 = corpora[1] if len(corpora) > 1 else None
        if corp2 is None:
            return False
        lang1 = self._lang_from_corpname(corp1)
        lang2 = self._lang_from_corpname(corp2)
        return lang1 in AVAIL_LANG_MAPPINGS and lang2 in AVAIL_LANG_MAPPINGS[lang1]

    @staticmethod
    def mk_uri_args(lang1, lang2, groups, word, lemma, pos):
        return (u'left={lang1}&right={lang2}&viceslovne=false&regularni=true&lemma=true&aJeA=true&hledejKde={groups}'
                u'&hledejCo={word}&order=percDesc').format(lang1=lang1, lang2=lang2, groups=groups, word=word).encode('utf-8')

    def mk_api_path(self, lang1, lang2, groups, word, lemma, pos):
        return '/api.php?api=true&' + self.mk_uri_args(lang1, lang2, groups, word, lemma, pos)

    def mk_page_path(self, lang1, lang2, groups, word, lemma, pos):
        return '/index.php?' + self.mk_uri_args(lang1, lang2, groups, word, lemma, pos)

    def find_lang_common_groups(self, lang1, lang2):
        g1 = set(AVAIL_GROUPS.get(lang1, []))
        g2 = set(AVAIL_GROUPS.get(lang2, []))
        return g1.intersection(g2)

    def mk_server_addr(self):
        if self._conf.get('ssl', False):
            return ('https://' + self._conf['server']).encode('utf-8')
        return ('http://' + self._conf['server']).encode('utf-8')

    @cached
    def fetch_data(self, word, lemma, pos, corpora, lang):
        """
        """
        primary_lang = self._lang_from_corpname(corpora[0])
        translat_corp, translat_lang = self._find_second_lang(corpora)
        treq_link = None
        if translat_corp and translat_lang:
            common_groups = ','.join(self.find_lang_common_groups(primary_lang, translat_lang))
            args = dict(word=word, lemma=lemma, pos=pos, lang1=primary_lang, lang2=translat_lang,
                        groups=common_groups)
            tmp = self.mk_page_path(**args)
            treq_link = self.mk_server_addr() + tmp
            connection = self.create_connection()
            try:
                logging.getLogger(__name__).debug(u'Treq request args: {0}'.format(args))
                connection.request('GET', self.mk_api_path(**args))
                data, status = self.process_response(connection)
                data = json.loads(data)
                max_items = self._conf.get('maxResultItems', self.DEFAULT_MAX_RESULT_LINES)
                data['lines'] = data['lines'][:max_items]
            finally:
                connection.close()
        else:
            data = dict(sum=0, lines=[])
        return json.dumps(dict(treq_link=treq_link,
                               sum=data.get('sum', 0),
                               translations=data.get('lines', []),
                               primary_corp=corpora[0],
                               translat_corp=translat_corp)), True
