# coding=utf-8
import l10n
from functools import partial
from argmapping import Args
import kwiclib
from controller.kontext import Kontext
from controller import exposed
import conclib
import plugins
import settings
import urlparse
import logging
import math
import xml.etree.ElementTree as ET
from collections import OrderedDict
import sys
from pprint import pprint


_logger = logging.getLogger(__name__)

MAX_INT  = sys.maxint

class Actions(Kontext):
    """
    An action controller providing services related to the Federated Content Search support
    """

    def __init__(self, request, ui_lang):
        """
        arguments:
        request -- Werkzeug's request object
        ui_lang -- a language code in which current action's result will be presented
        """
        super(Actions, self).__init__(request=request, ui_lang=ui_lang)
        self.search_attrs = settings.get('fcs', 'search_attributes', ['word'])

    def get_mapping_url_prefix(self):
        """
        This is required as it maps the controller to request URLs. In this case,
        all the requests of the form /fcs/[action name]?[parameters] are mapped here.
        """
        return '/fcs/'

    def _check_args(self, req, supported_default, supported):
        supported_default.extend(supported)
        unsupported_args = set(req.args.keys()) - set(supported_default)
        if 0 < len(unsupported_args):
            raise Exception(8, list(unsupported_args)[0], 'Unsupported parameter')

    def _corpus_info(self, corpname):
        """
        Returns info about specified corpus.
        :param corpname: str, corpus identifier
        :return: dict, corpus parameters
        """
        corpus = self.cm.get_Corpus(corpname)
        import_str = partial(l10n.import_string, from_encoding=corpus.get_conf('ENCODING'))
        data = {}
        data['corpname'] = corpname
        data['result'] = corpus.get_conf('ATTRLIST').split(',')
        data['corpus_desc'] = u'Corpus {0} ({1} tokens) {2}'.format(
            import_str(corpus.get_conf('NAME')),
            l10n.simplify_num(corpus.size()),
            import_str(corpus.get_info())
        )
        data['corpus_lang'] = Languages.get_iso_code(corpus.get_conf('LANGUAGE'))

        return data

    def _corpora_info(self, value, max_items):
        resources = []
        corpora_d = {value: value}
        if value == 'root':
            corpora_d = plugins.runtime.AUTH.instance.permitted_corpora(self.session_get(
                'user'))

        for i, corpus_id in enumerate(corpora_d):
            if i >= max_items:
                break
            resource_info = {}
            c = self.cm.get_Corpus(corpus_id)
            import_str = partial(l10n.import_string, from_encoding=c.get_conf('ENCODING'))
            corpus_title = import_str(c.get_conf('NAME'))
            resource_info['title'] = corpus_title
            resource_info['landingPageURI'] = c.get_conf('INFOHREF')
            # TODO(jm) - Languages copied (and slightly fixed) from 0.5 - should be checked
            resource_info['language'] = Languages.get_iso_code(c.get_conf('LANGUAGE'))
            resource_info['description'] = import_str(c.get_conf('INFO'))
            resources.append((corpus_id, corpus_title, resource_info))
        return resources

    def fcs_search(self, corp, corpname, fcs_query, max_rec, start):
        """
            aux function for federated content search: operation=searchRetrieve
        """
        query = fcs_query.replace('+', ' ')  # convert URL spaces
        exact_match = True  # attr=".*value.*"
        if 'exact' in query.lower() and '=' not in query:  # lemma EXACT "dog"
            pos = query.lower().index('exact')  # first occurrence of EXACT
            query = query[:pos] + '=' + query[pos + 5:]  # 1st exact > =
            exact_match = True

        attrs = corp.get_conf('ATTRLIST').split(',')  # list of available attrs
        try:  # parse query
            if '=' in query:  # lemma=word | lemma="word" | lemma="w1 w2" | word=""
                attr, term = query.split('=')
                attr = attr.strip()
                term = term.strip()
            else:  # "w1 w2" | "word" | word
                attr = 'word'
                # use one of search attributes if in corpora attributes
                # otherwise use `word` - fails below if not valid
                for sa in self.search_attrs:
                    if sa in attrs:
                        attr = sa
                        break
                term = query.strip()
            if '"' in attr:
                raise Exception
            if '"' in term:  # "word" | "word1 word2" | "" | "it is \"good\""
                if term[0] != '"' or term[-1] != '"':  # check q. marks
                    raise Exception
                term = term[1:-1].strip()  # remove quotation marks
                if ' ' in term:  # multi-word term
                    if exact_match:
                        rq = ' '.join(['[%s="%s"]' % (attr, t)
                                       for t in term.split()])
                    else:
                        rq = ' '.join(['[%s=".*%s.*"]' % (attr, t)
                                       for t in term.split()])
                elif term.strip() == '':  # ""
                    raise Exception  # empty term
                else:  # one-word term
                    if exact_match:
                        rq = '[%s="%s"]' % (attr, term)
                    else:
                        rq = '[%s=".*%s.*"]' % (attr, term)
            else:  # must be single-word term
                if ' ' in term:
                    raise Exception
                if exact_match:  # build query
                    rq = '[%s="%s"]' % (attr, term)
                else:
                    rq = '[%s=".*%s.*"]' % (attr, term)
        except:  # there was a problem when parsing
            raise Exception(10, query, 'Query syntax error')
        if attr not in attrs:
            raise Exception(16, attr, 'Unsupported index')

        fromp = int(math.floor((start - 1) / max_rec)) + 1
        # try to get concordance
        try:
            anon_id = plugins.runtime.AUTH.instance.anonymous_user()['id']
            q = ['q' + rq]
            conc = conclib.get_conc(corp, anon_id, q=q, fromp=fromp, pagesize=max_rec, async=0)
        except Exception as e:
            raise Exception(10, repr(e), 'Query syntax error')

        kwic = kwiclib.Kwic(corp, corpname, conc)
        kwic_args = kwiclib.KwicPageArgs(Args(), base_attr=Kontext.BASE_ATTR)
        kwic_args.fromp = fromp
        kwic_args.pagesize = max_rec
        kwic_args.leftctx = '-{0}'.format(settings.get_int('fcs', 'kwic_context', 5))
        kwic_args.rightctx = '{0}'.format(settings.get_int('fcs', 'kwic_context', 5))
        page = kwic.kwicpage(kwic_args)  # convert concordance

        local_offset = (start - 1) % max_rec
        if conc.size() == 0:
            return [], 0
        if start > conc.size():
            raise Exception(61, 'startRecord', 'First record position out of range')
        rows = [
            (
                kwicline['Left'][0]['str'],
                kwicline['Kwic'][0]['str'],
                kwicline['Right'][0]['str'],
                kwicline['ref']
            )
            for kwicline in page['Lines']
        ][local_offset:local_offset + max_rec]
        return rows, conc.size()

    @exposed(return_type='template', template='fcs/v1_complete.tmpl', skip_corpus_init=True, http_method=('GET', 'HEAD'))
    def v1(self, req):
        self._headers['Content-Type'] = 'application/xml'
        current_version = 1.2

        default_corp_list = settings.get('corpora', 'default_corpora', [])
        corpname = None
        if 0 == len(default_corp_list):
            _logger.critical('FCS cannot work properly without a default_corpora set')
        else:
            corpname = default_corp_list[0]

        pr = urlparse.urlparse(req.host_url)
        # None values should be filled in later
        data = {
            'corpname': corpname,
            'corppid': None,
            'version': current_version,
            'recordPacking': 'xml',
            'result': [],
            'operation': None,
            'numberOfRecords': 0,
            'server_name': pr.hostname,
            'server_port': pr.port or 80,
            'database': req.path,
            'maximumRecords': None,
            'maximumTerms': None,
            'startRecord': None,
            'responsePosition': None,
        }
        # supported parameters for all operations
        supported_args = ['operation', 'stylesheet', 'version', 'extraRequestData']

        try:
            # check operation
            operation = req.args.get('operation', 'explain')
            data['operation'] = operation

            # check version
            version = req.args.get('version', None)
            if version is not None and current_version < float(version):
                raise Exception(5, version, 'Unsupported version')

            # check integer parameters
            maximumRecords = req.args.get('maximumRecords', 250)
            if 'maximumRecords' in req.args:
                try:
                    maximumRecords = int(maximumRecords)
                    if maximumRecords <= 0:
                        raise Exception(6, 'maximumRecords', 'Unsupported parameter value')
                except:
                    raise Exception(6, 'maximumRecords', 'Unsupported parameter value')
            data['maximumRecords'] = maximumRecords

            maximumTerms = req.args.get('maximumTerms', 100)
            if 'maximumTerms' in req.args:
                try:
                    maximumTerms = int(maximumTerms)
                except:
                    raise Exception(6, 'maximumTerms', 'Unsupported parameter value')
            data['maximumTerms'] = maximumTerms

            startRecord = req.args.get('startRecord', 1)
            if 'startRecord' in req.args:
                try:
                    startRecord = int(startRecord)
                    if startRecord <= 0:
                        raise Exception(6, 'startRecord', 'Unsupported parameter value')
                except:
                    raise Exception(6, 'startRecord', 'Unsupported parameter value')
            data['startRecord'] = startRecord

            responsePosition = req.args.get('responsePosition', 0)
            if 'responsePosition' in req.args:
                try:
                    responsePosition = int(responsePosition)
                except:
                    raise Exception(6, 'responsePosition', 'Unsupported parameter value')
            data['responsePosition'] = responsePosition

            # set content-type in HTTP header
            recordPacking = req.args.get('recordPacking', 'xml')
            if recordPacking == 'xml':
                pass
            elif recordPacking == 'string':
                # TODO(jm)!!!
                self._headers['Content-Type'] = 'text/plain; charset=utf-8'
            else:
                raise Exception(71, 'recordPacking', 'Unsupported record packing')

            # provide info about service
            if operation == 'explain':
                self._check_args(
                    req, supported_args,
                    ['recordPacking', 'x-fcs-endpoint-description']
                )
                corpus = self.cm.get_Corpus(corpname)
                import_str = partial(l10n.import_string, from_encoding=corpus.get_conf('ENCODING'))
                data['result'] = corpus.get_conf('ATTRLIST').split(',')
                data['numberOfRecords'] = len(data['result'])
                data['corpus_desc'] = u'Corpus {0} ({1} tokens)'.format(
                    import_str(corpus.get_conf('NAME')), l10n.simplify_num(corpus.size()))
                data['corpus_lang'] = Languages.get_iso_code(corpus.get_conf('LANGUAGE'))
                data['show_endpoint_desc'] = (True if req.args.get('x-fcs-endpoint-description', 'false') == 'true'
                                              else False)

            # wordlist for a given attribute
            elif operation == 'scan':
                self._check_args(
                    req, supported_args,
                    ['scanClause', 'responsePosition', 'maximumTerms', 'x-cmd-resource-info']
                )
                data['resourceInfoRequest'] = req.args.get('x-cmd-resource-info', '') == 'true'
                scanClause = req.args.get('scanClause', '')
                if scanClause.startswith('fcs.resource='):
                    value = scanClause.split('=')[1]
                    data['result'] = self._corpora_info(value, maximumTerms)
                else:
                    data['result'] = conclib.fcs_scan(
                        corpname, scanClause, maximumTerms, responsePosition)

            # simple concordancer
            elif operation == 'searchRetrieve':
                # TODO we should review the args here (especially x-cmd-context, resultSetTTL)
                self._check_args(
                    req, supported_args,
                    ['query', 'startRecord', 'maximumRecords', 'recordPacking',
                        'recordSchema', 'resultSetTTL', 'x-cmd-context', 'x-fcs-context']
                )
                if 'x-cmd-context' in req.args:
                    req_corpname = req.args['x-cmd-context']
                    user_corpora = plugins.runtime.AUTH.instance.permitted_corpora(
                        self.session_get('user'))
                    if req_corpname in user_corpora:
                        corpname = req_corpname
                    else:
                        _logger.warning(
                            'Requested unavailable corpus [%s], defaulting to [%s]', req_corpname, corpname)
                    data['corpname'] = corpname

                corp_conf_info = plugins.runtime.CORPARCH.instance.get_corpus_info('en_US',
                                                                                   corpname)
                data['corppid'] = corp_conf_info.get('web', '')
                query = req.args.get('query', '')
                corpus = self.cm.get_Corpus(corpname)
                if 0 == len(query):
                    raise Exception(7, 'fcs_query', 'Mandatory parameter not supplied')
                data['result'], data['numberOfRecords'] = self.fcs_search(
                    corpus, corpname, query, maximumRecords, startRecord)

            # unsupported operation
            else:
                # show within explain template
                data['operation'] = 'explain'
                raise Exception(4, '', 'Unsupported operation')

        # catch exception and amend diagnostics in template
        except Exception as e:
            data['message'] = ('error', repr(e))
            try:
                data['code'], data['details'], data['msg'] = e
            except ValueError:
                data['code'], data['details'] = 1, repr(e)
                data['msg'] = 'General system error'

        return data

    @exposed(return_type='template', template='fcs/fcs2html.tmpl', skip_corpus_init=True)
    def fcs2html(self, req):
        """
            Returns XSL template for rendering FCS XML.
        """
        self._headers['Content-Type'] = 'text/xsl; charset=utf-8'
        custom_hd_inject_path = settings.get('fcs', 'template_header_inject_file', None)
        if custom_hd_inject_path:
            with open(custom_hd_inject_path) as fr:
                custom_hdr_inject = fr.read()
        else:
            custom_hdr_inject = None

        return dict(fcs_provider_heading=settings.get('fcs', 'provider_heading', 'KonText FCS Data Provider'),
                    fcs_provider_website=settings.get('fcs', 'provider_website', None),
                    fcs_template_css_url=settings.get_list('fcs', 'template_css_url'),
                    fcs_custom_hdr_inject=custom_hdr_inject)


    def _get_element_tree(self, ns, title, data, attributes={}):
        """
        Creates xml.etree.ElementTree object from given data.
        :param ns: str, namespace
        :param title: str, root node title
        :param data: list, elements of different types
        :param attributes: dict, root node attributes,
        :return: xml.etree.ElementTree, created object
        """
        if not ns.endswith(':'):
            ns += ':'

        root = ET.Element(ns + title)
        root.attrib = attributes

        for elem in data:
            if elem is None:
                continue

            if type(elem) == ET.Element:
                root.insert(MAX_INT, elem)

            else:
                if len(elem) == 2:
                    attributes = {}
                    key, value = elem
                else:
                    key, value, attributes = elem

                if type(value) == list:
                    el = self._get_element_tree(ns, key, value, attributes)
                    root.insert(MAX_INT, el)

                else:
                    el = ET.SubElement(root, ns + key)
                    el.text = value
                    el.attrib = attributes

        return root

    def _get_endpoint_description_tree(self, parameters, ns='ed'):
        """
        Creates xml.etree.ElementTree object for fcs endpoint description site.
        :param parameters: dict
        :param ns: str, namespace
        :return: xml.etree.ElementTree
        """
        default_corpus_info = self._corpus_info(parameters['corpname'])

        data = [
            ('Capabilities', [('Capability', 'http://clarin.eu/fcs/capability/basic-search')]),
            ('SupportedDataViews', [
                ('SupportedDataView', 'application/x-clarin-fcs-hits+xml', {
                    'id': 'hits', 'delivery-policy': 'send-by-default'})]),
            ('Resources', [
                ('Resource', [
                    ('Title', parameters['corpname'], {'xml:lang': 'en'}),
                    ('Description', default_corpus_info['corpus_desc'], {'xml:lang': 'en'}),
                    ('Languages', [('Language', default_corpus_info['corpus_lang'])]),
                    ('AvailableDataViews', '', {'ref': 'hits'}),
                    ('LandingPageUri', self.create_url('first_form', [('corpname', default_corpus_info['corpname'])]))
                ], {'pid': default_corpus_info['corpname']}),
            ])
        ]

        return self._get_element_tree(
            ns,
            'EndpointDescription',
            data, {
                'xmlns:ed': "http://clarin.eu/fcs/endpoint-description",
                'version': "2"
            })


    def v2_explain_response(self,
                            parameters,
                            explain_response=False):
        """
        Creates xml.etree.ElementTree object for fcs explain site.
        :param parameters: dict
        :param explain_response: boolean
        :param ns: str, namespace
        :return: xml.etree.ElementTree
        """
        default_corpus_info = self._corpus_info(parameters['corpname'])

        data = [
            ('version', parameters['version']),
            ('record', [
                ('recordSchema', 'http://explain.z3950.org/dtd/2.0/'),
                ('recordXMLEscaping', parameters['record_xml_escaping']),
                ('recordData', [
                    self._get_element_tree('zr', 'explain', [
                        ('serverInfo', [
                            ('host', parameters['server_name']),
                            ('port', parameters['server_port']),
                            ('database', parameters['database'])]),
                        ('databaseInfo', [
                            ('title', parameters['corpname'], {'lang': 'en', 'primary': 'true'}),
                            ('description', default_corpus_info['corpus_desc'], {'lang': 'en'})]),
                        ('indexInfo',
                         [('set', [
                             ('title', 'CLARIN Content Search', {'lang': 'en', 'primary': 'true'})
                         ], {'identifier': 'http://clarin.eu/fcs/resource', 'name': 'fcs'})] +
                         [('index', [('title', search_index)], {'search': 'true', 'scan': 'true', 'sort': 'true'}) for
                          search_index in default_corpus_info['result']]),
                        ('schemaInfo', [
                            ('schema', [
                                ('title', 'CLARIN Content Search', {'lang': 'en', 'name': 'fcs'})
                            ], {'identifier': 'http://clarin.eu/fcs/resource', 'name': 'fcs'}),
                        ]),
                        ('configInfo', [
                            ('default', '250', {'type': 'numberOfRecords'}),
                            ('setting', '250', {'type': 'maximumRecords'}),
                        ])
                    ], {'xmlns:zr': "http://explain.z3950.org/dtd/2.0/"})
                ]),
                ('echoedExplainRequest', [
                    ('version', parameters['version'])
                ])
            ])]

        if explain_response:
            data.append(
                ('extraResponseData',
                 [self._get_endpoint_description_tree(parameters)])
            )

        tree = self._get_element_tree('sruResponse', 'explainResponse', data,
                               {'xmlns:sruResponse': "http://docs.oasis-open.org/ns/search-ws/sruResponse"})

        return tree

    def _get_default_corpora(self):
        # Returns kontext default corpora from settings

        default_corp_list = settings.get('corpora', 'default_corpora', [])
        corpname = None
        if 0 == len(default_corp_list):
            _logger.critical('FCS cannot work properly without a default_corpora set')
        else:
            corpname = default_corp_list[0]
        return corpname

    def _get_search_retrieve_tree(self, parameters, results, number_of_records, start_row=1, max_records=250):
        """
        Creates xml.etree.ElementTree object for fcs search retrieve site.
        :param parameters: dict
        :param results: list
        :param number_of_records: int
        :param start_row: int
        :param max_records: int
        :return:
        """

        results = results[start_row-1:start_row-1+max_records]

        def _create_hit_element(pre, hit, post):
            el = ET.Element('hits:Result')
            el.text = pre
            el_hit = ET.SubElement(el, 'hits:Hit')
            el_hit.text = hit
            el_hit.tail = post
            el.attrib = {'xmlns:hits': "http://clarin.eu/fcs/dataview/hits"}
            return el

        records = self._get_element_tree('sruResponse', 'record', [
            ('recordSchema', 'http://clarin.eu/fcs/resource'),
            ('recordXMLEscaping', 'xml'),
            ('recordData', [
                self._get_element_tree('fcs', 'Resource', [
                    ('ResourceFragment', [
                        ('DataView', [
                            _create_hit_element(r[0], r[1], r[2])
                        ], {'type': "application/x-clarin-fcs-hits+xml"}),
                    ])], {'xmlns:fcs': 'http://clarin.eu/fcs/resource', 'pid': parameters['corpname']}) for r in results
            ])], {'xmlns:sruResponse': "http://docs.oasis-open.org/ns/search-ws/sruResponse"})

        data = [
            ('version', str(parameters['version'])),
            ('numberOfRecords', str(number_of_records)),
        ]

        if len(results) > 0:
            data.append(('records', [records]))

        return self._get_element_tree('sruResponse', 'searchRetrieveResponse', data,
                                     {'xmlns:sruResponse': "http://docs.oasis-open.org/ns/search-ws/sruResponse"})

    def _get_error_tree(self, error_code, details, message, operation, parameters):
        """
        Creates xml.etree.ElementTree object for fcs error message.
        :param error_code: str
        :param details: str
        :param message: str
        :param operation: str
        :param parameters: dict
        :return:
        """

        top_level_elements = [
            ('version', parameters['version'])
        ]

        ns = operation
        if operation == 'searchRetrieve':
            ns = 'sruResponse'
            operation = 'searchRetrieve'

            top_level_elements.append(('numberOfRecords', '0'))

        out = self._get_element_tree(ns, '{}Response'.format(operation),
            top_level_elements,
            {'xmlns:{}'.format(ns): 'http://docs.oasis-open.org/ns/search-ws/{}'.format(ns)})

        error_tree = self._get_element_tree(ns, 'diagnostics', [
            self._get_element_tree('diag', 'diagnostic', [
                ('uri', 'info:srw/diagnostic/1/{}'.format(error_code)),
                ('details', details),
                ('message', message),
            ])
        ], {
            'xmlns:diag': 'http://docs.oasis-open.org/ns/search-ws/diagnostic'})

        out.insert(MAX_INT, error_tree)
        return out

    def _create_scan_response(self, results):
        """
        Creates xml.etree.ElementTree object for fcs scan response.
        :param results:
        :return:
        """

        return self._get_element_tree('sruResponse', 'scanResponse', [
            self._get_element_tree('scan', 'terms', [
                ('term', [
                    ('value', term['value']),
                    ('numberOfRecords', str(term['freq'])) if 'freq' in term else None,
                    ('displayTerm', term['display']) if 'display' in term else None
                ]) for term in results
            ], {'xmlns:scan': 'http://docs.oasis-open.org/ns/search-ws/scan'})
        ], {'xmlns:sruResponse': "http://docs.oasis-open.org/ns/search-ws/sruResponse"})
        pass

    def _get_fcs_parameter(self, req, param_name):
        def check_value(param_name, value):
            if param_name == 'maximumRecords' or \
                    param_name  == 'maximumTerms' or \
                    param_name == 'startRecord':
                assert value > 0
            elif param_name == 'responsePosition':
                assert value >= 0
            elif param_name == 'queryType':
                assert value == 'cql'

        default_params = {
            'operation': ('explain', str),
            'version': ('2', str),
            'maximumRecords': (250, int),
            'maximumTerms': (100, int),
            'minimumTerms' : (100, int),
            'startRecord': (1, int),
            'responsePosition': (0, int),
            'x-fcs-endpoint-description': ('false', str),
            'queryType': ('cql', str),
            'query': ('', str),
            'scanClause': ('', str),
        }

        if param_name in req.args:
            try:
                # casting to desired value
                value = default_params[param_name][1](req.args[param_name])
                check_value(param_name, value)
                return value
            except:
                raise Exception(6, param_name, 'Unsupported parameter value')
        else:
            return default_params[param_name][0]

    @exposed(return_type='xml', skip_corpus_init=True, http_method=('GET', 'HEAD'))
    def v2(self, req):
        """
        Returns response for FCS, version 2 request by default.
        When version argument in request is set to 1.2 fcs is handled by self.v1 function.
        :param req: incoming request
        :return: str, FCS response
        """

        # supported parameters for all operations
        supported_args = ['operation', 'stylesheet', 'version', 'extraRequestData']

        operation = ''

        # setting operation based on other supplied arguments
        if 'operation' not in req.args:
            if 'scanClause' in req.args:
                operation = 'scan'
            elif 'query' in req.args:
                operation = 'searchRetrieve'

        # setting default operation if it's not specified
        if str(operation) == '':
            operation = self._get_fcs_parameter(req, 'operation')

        corpname = self._get_default_corpora()
        pr = urlparse.urlparse(req.host_url)
        data = {
            'corpname': corpname,
            'corppid': None,
            'version': '2.0',
            'recordPacking': 'xml',
            'result': [],
            'operation': None,
            'numberOfRecords': 0,
            'server_name': pr.hostname,
            'server_port': str(pr.port) or str(80),
            'database': req.path,
            'maximumRecords': None,
            'maximumTerms': None,
            'startRecord': None,
            'responsePosition': None,
            'record_xml_escaping': 'xml'
        }

        error_data = None

        try:
            # checking fcs version
            version = req.args.get('version', None)
            if float(version) == 1.2:
                return self.v1(req)
            if version is not None and float(data['version']) != float(version):
                raise Exception(5, version, 'Unsupported version')

            # set content-type in HTTP header
            recordXmlEscaping = req.args.get('recordXMLEscaping', 'xml')
            if recordXmlEscaping == 'string':
                self._headers['Content-Type'] = 'text/plain; charset=utf-8'
            elif recordXmlEscaping == 'xml':
                self._headers['Content-Type'] = 'application/xml'
            else:
                raise Exception(71, 'recordXMLEscaping', 'Unsupported value')

            if operation == 'explain':
                self._check_args(
                    req, supported_args,
                    ['x-fcs-endpoint-description']
                )
                response = self.v2_explain_response(
                    data,
                    explain_response=(self._get_fcs_parameter(req, 'x-fcs-endpoint-description') == 'true'))

            elif operation == 'searchRetrieve':
                self._check_args(
                    req, supported_args,
                    ['queryType', 'query', 'startRecord', 'maximumRecords' , 'recordXMLEscaping', 'recordSchema']
                )
                query_type = req.args.get('queryType', 'cql')
                if query_type != 'cql':
                    raise Exception(61, '', 'Supplied query type cannot be handled.')

                query = req.args.get('query')
                if query is None:
                    raise Exception(61, '', 'Query not specified.')

                corpus = self.cm.get_Corpus(corpname)
                maximum_records = self._get_fcs_parameter(req, 'maximumRecords')
                start_record = self._get_fcs_parameter(req, 'startRecord')

                # manatee parameters have to be 32-bit integers, not larger
                # but manatee returns error for smaller numbers as well
                if abs(maximum_records) > 0xffffffff:
                    raise Exception(61, '', 'Supplied maximumRecords parameter is too large')

                if abs(start_record) > 0xffffffff:
                    raise Exception(61, '', 'Supplied startRecord Parameter is too large')

                try:
                    results, number_of_records = self.fcs_search(corpus, corpname, query, maximum_records, start_record)
                except NotImplementedError:
                    raise Exception(61, 'One of supplied parameters is too large for the system to process.', 'Supplied parameter is too large')
                response = self._get_search_retrieve_tree(data, results, number_of_records)

            elif operation == 'scan':
                self._check_args(
                    req, supported_args,
                    ['scanClause', 'responsePosition', 'maximumTerms', 'x-cmd-resource-info']
                )
                data['resourceInfoRequest'] = req.args.get('x-cmd-resource-info', '') == 'true'

                scanClause = self._get_fcs_parameter(req, 'scanClause')
                maximumTerms = self._get_fcs_parameter(req, 'maximumTerms')
                responsePosition = self._get_fcs_parameter(req, 'responsePosition')

                if scanClause.startswith('fcs.resource='):
                    value = scanClause.split('=')[1]
                    result = [{'value': c[0], 'display': c[1], 'optional': c[2]} for c in
                              self._corpora_info(value, maximumTerms)]
                else:
                    result = [{'value': r[0], 'freq': r[1]} for r in conclib.fcs_scan(
                        corpname, scanClause, maximumTerms, responsePosition)]

                response = self._create_scan_response(result, data)

            else:
                operation = 'explain'
                raise Exception(4, '', 'Unsupported operation')

        except Exception as e:
            error_data = {'message': ('error', repr(e))}
            try:
                error_data['code'], error_data['details'], error_data['msg'] = e
            except ValueError:
                error_data['code'], error_data['details'] = 1, repr(e)
                error_data['msg'] = 'General system error'

        if error_data:
            response = self._get_error_tree(error_data['code'], error_data['details'], error_data['msg'],
                                            operation=operation, parameters=data)
        return ET.tostring(response, encoding='utf8', method='xml')


class Languages(object):
    """
        Class wrapping conversion maps between language name and ISO 639-3 three letter language codes
    """
    language2iso = {
        'Abkhazian': 'abk',
        'Adyghe': 'ady',
        'Afar': 'aar',
        'Afrikaans': 'afr',
        'Aghem': 'agq',
        'Akan': 'aka',
        'Albanian': 'sqi',
        'Amharic': 'amh',
        'Ancient Greek': 'grc',
        'Arabic': 'ara',
        'Armenian': 'hye',
        'Assamese': 'asm',
        'Asturian': 'ast',
        'Asu': 'asa',
        'Atsam': 'cch',
        'Avaric': 'ava',
        'Aymara': 'aym',
        'Azerbaijani': 'aze',
        'Bafia': 'ksf',
        'Bambara': 'bam',
        'Bashkir': 'bak',
        'Basque': 'eus',
        'Belarusian': 'bel',
        'Bemba': 'bem',
        'Bena': 'yun',
        'Bengali': 'ben',
        'Bislama': 'bis',
        'Blin': 'byn',
        'Bodo': 'boy',
        'Bosnian': 'bos',
        'Breton': 'bre',
        'Bulgarian': 'bul',
        'Burmese': 'mya',
        'Catalan': 'cat',
        'Cebuano': 'ceb',
        'Chamorro': 'cha',
        'Chechen': 'che',
        'Cherokee': 'chr',
        'Chiga': 'cgg',
        'Chinese': 'zho',
        'Chuukese': 'chk',
        'Congo Swahili': 'swc',
        'Cornish': 'cor',
        'Croatian': 'hrv',
        'Czech': 'ces',
        'Danish': 'dan',
        'Divehi': 'div',
        'Duala': 'dua',
        'Dutch': 'nld',
        'Dzongkha': 'dzo',
        'Efik': 'efi',
        'Embu': 'ebu',
        'English': 'eng',
        'Erzya': 'myv',
        'Estonian': 'est',
        'Ewe': 'ewe',
        'Ewondo': 'ewo',
        'Faroese': 'fao',
        'Fijian': 'fij',
        'Filipino': 'fil',
        'Finnish': 'fin',
        'French': 'fra',
        'Friulian': 'fur',
        'Fulah': 'ful',
        'Gagauz': 'gag',
        'Galician': 'glg',
        'Ganda': 'lug',
        'Georgian': 'kat',
        'German': 'deu',
        'Gilbertese': 'gil',
        'Guarani': 'grn',
        'Gujarati': 'guj',
        'Gusii': 'guz',
        'Haitian': 'hat',
        'Hausa': 'hau',
        'Hawaiian': 'haw',
        'Hebrew': 'heb',
        'Hiligaynon': 'hil',
        'Hindi': 'hin',
        'Hiri Motu': 'hmo',
        'Hungarian': 'hun',
        'Icelandic': 'isl',
        'Igbo': 'ibo',
        'Iloko': 'ilo',
        'Indonesian': 'ind',
        'Ingush': 'inh',
        'Irish': 'gle',
        'Italian': 'ita',
        'Japanese': 'jpn',
        'Javanese': 'jav',
        'Jju': 'kaj',
        'Jola-Fonyi': 'dyo',
        'Kabardian': 'kbd',
        'Kabuverdianu': 'kea',
        'Kabyle': 'kab',
        'Kalaallisut': 'kal',
        'Kalenjin': 'kln',
        'Kamba': 'kam',
        'Kannada': 'kan',
        'Karachay-Balkar': 'krc',
        'Kashmiri': 'kas',
        'Kazakh': 'kaz',
        'Khasi': 'kha',
        'Khmer': 'khm',
        'Kikuyu': 'kik',
        'Kinyarwanda': 'kin',
        'Kirghiz': 'kir',
        'Komi-Permyak': 'koi',
        'Komi-Zyrian': 'kpv',
        'Kongo': 'kon',
        'Konkani': 'knn',
        'Korean': 'kor',
        'Kosraean': 'kos',
        'Koyraboro Senni': 'ses',
        'Koyra Chiini': 'khq',
        'Kpelle': 'kpe',
        'Kuanyama': 'kua',
        'Kumyk': 'kum',
        'Kurdish': 'kur',
        'Kwasio': 'nmg',
        'Lahnda': 'lah',
        'Lak': 'lbe',
        'Langi': 'lag',
        'Lao': 'lao',
        'Latin': 'lat',
        'Latvian': 'lav',
        'Lezghian': 'lez',
        'Lingala': 'lin',
        'Lithuanian': 'lit',
        'Low German': 'nds',
        'Luba-Katanga': 'lub',
        'Luba-Lulua': 'lua',
        'Luo': 'luo',
        'Luxembourgish': 'ltz',
        'Luyia': 'luy',
        'Macedonian': 'mkd',
        'Machame': 'jmc',
        'Maguindanaon': 'mdh',
        'Maithili': 'mai',
        'Makhuwa-Meetto': 'mgh',
        'Makonde': 'kde',
        'Malagasy': 'mlg',
        'Malay': 'msa',
        'Malayalam': 'mal',
        'Maltese': 'mlt',
        'Manx': 'glv',
        'Maori': 'mri',
        'Marathi': 'mar',
        'Marshallese': 'mah',
        'Masai': 'mas',
        'Meru': 'mer',
        'Modern Greek': 'ell',
        'Moksha': 'mdf',
        'Mongolian': 'mon',
        'Morisyen': 'mfe',
        'Nama': 'nmx',
        'Nauru': 'nau',
        'Nepali': 'npi',
        'Niuean': 'niu',
        'Northern Sami': 'sme',
        'Northern Sotho': 'nso',
        'North Ndebele': 'nde',
        'Norwegian Bokmål': 'nob',
        'Norwegian Nynorsk': 'nno',
        'Nuer': 'nus',
        'Nyanja': 'nya',
        'Nyankole': 'nyn',
        'Occitan': 'oci',
        'Oriya': 'ori',
        'Oromo': 'orm',
        'Ossetic': 'oss',
        'Palauan': 'pau',
        'Pangasinan': 'pag',
        'Papiamento': 'pap',
        'Pashto': 'pus',
        'Persian': 'fas',
        'Pohnpeian': 'pon',
        'Polish': 'pol',
        'Portuguese': 'por',
        'Punjabi': 'pan',
        'Quechua': 'que',
        'Romanian': 'ron',
        'Romansh': 'roh',
        'Rombo': 'rof',
        'Russian': 'rus',
        'Rwa': 'rwk',
        'Saho': 'ssy',
        'Samburu': 'saq',
        'Samoan': 'smo',
        'Sango': 'sag',
        'Sangu': 'sbp',
        'Sanskrit': 'san',
        'Santali': 'sat',
        'Scottish Gaelic': 'gla',
        'Sena': 'seh',
        'Serbian': 'srp',
        'Shambala': 'ksb',
        'Shona': 'sna',
        'Sichuan Yi': 'iii',
        'Sidamo': 'sid',
        'Sindhi': 'snd',
        'Sinhala': 'sin',
        'Slovak': 'slk',
        'Slovenian': 'slv',
        'Soga': 'xog',
        'Somali': 'som',
        'Southern Sotho': 'sot',
        'South Ndebele': 'nbl',
        'Spanish': 'spa',
        'Swahili': 'swa',
        'Swati': 'ssw',
        'Swedish': 'swe',
        'Swiss German': 'gsw',
        'Tachelhit': 'shi',
        'Tahitian': 'tah',
        'Taita': 'dav',
        'Tajik': 'tgk',
        'Tamil': 'tam',
        'Taroko': 'trv',
        'Tasawaq': 'twq',
        'Tatar': 'tat',
        'Tausug': 'tsg',
        'Telugu': 'tel',
        'Teso': 'teo',
        'Tetum': 'tet',
        'Thai': 'tha',
        'Tibetan': 'bod',
        'Tigre': 'tig',
        'Tigrinya': 'tir',
        'Tokelau': 'tkl',
        'Tok Pisin': 'tpi',
        'Tonga': 'ton',
        'Tsonga': 'tso',
        'Tswana': 'tsn',
        'Turkish': 'tur',
        'Turkmen': 'tuk',
        'Tuvalu': 'tvl',
        'Tuvinian': 'tyv',
        'Tyap': 'kcg',
        'Udmurt': 'udm',
        'Uighur': 'uig',
        'Ukrainian': 'ukr',
        'Ulithian': 'uli',
        'Urdu': 'urd',
        'Uzbek': 'uzb',
        'Vai': 'vai',
        'Venda': 'ven',
        'Vietnamese': 'vie',
        'Vunjo': 'vun',
        'Walser': 'wae',
        'Waray': 'wrz',
        'Welsh': 'cym',
        'Western Frisian': 'fry',
        'Wolof': 'wol',
        'Xhosa': 'xho',
        'Yangben': 'yav',
        'Yapese': 'yap',
        'Yoruba': 'yor',
        'Zarma': 'dje',
        'Zhuang': 'zha',
        'Zulu': 'zul'
    }

    @staticmethod
    def get_iso_code(language):
        code = ''
        if language in Languages.language2iso:
            code = Languages.language2iso[language]
        return code
