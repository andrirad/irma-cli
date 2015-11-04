import requests
import json
from marshmallow import fields, Schema
import time
import urllib

# Warning this is a copy of IrmaScanStatus lib.irma.common.utils
# in order to get rid of this dependency
# KEEP SYNCHRONIZED


class IrmaScanStatus:
    """ All status codes and labels for IrmaScan
    """
    empty = 0
    ready = 10
    uploaded = 20
    launched = 30
    processed = 40
    finished = 50
    flushed = 60
    # cancel
    cancelling = 100
    cancelled = 110
    # errors
    error = 1000
    # Probes 101x
    error_probe_missing = 1010
    error_probe_na = 1011
    # FTP 102x
    error_ftp_upload = 1020

    label = {empty: "empty",
             ready: "ready",
             uploaded: "uploaded",
             launched: "launched",
             processed: "processed",
             finished: "finished",
             cancelling: "cancelling",
             cancelled: "cancelled",
             flushed: "flushed",
             error: "error",
             error_probe_missing: "probelist missing",
             error_probe_na: "probe(s) not available",
             error_ftp_upload: "ftp upload error"
             }


class IrmaError(Exception):
    """Error on cli script"""
    pass


class IrmaApiClient(object):
    """ Basic Api class that just deals with get and post requests
    """

    def __init__(self, url, max_tries=1, pause=3, verbose=False):
        self.url = url
        self.verbose = verbose
        self.max_tries = max_tries
        self.pause = pause

    def get_call(self, route, **extra_args):
        nb_try = 0
        while nb_try < self.max_tries:
            nb_try += 1
            try:
                dec_extra_args = {}
                for (k, v) in extra_args.items():
                    if type(v) == unicode or type(v) == str:
                        dec_extra_args[k] = v.encode("utf8")
                    else:
                        dec_extra_args[k] = v
                args = urllib.urlencode(dec_extra_args)
                resp = requests.get(self.url + route + "?" + args)
                return self._handle_resp(resp)
            except IrmaError as e:
                print "Try {0} Max {1}".format(nb_try, self.max_tries)
                if nb_try < self.max_tries:
                    print "Exception Raised {0} retry #{1}".format(e, nb_try)
                    time.sleep(self.pause)
                    continue
                else:
                    raise

    def post_call(self, route, **extra_args):
        nb_try = 0
        while nb_try < self.max_tries:
            nb_try += 1
            try:
                resp = requests.post(self.url + route, **extra_args)
                return self._handle_resp(resp)
            except IrmaError as e:
                if nb_try < self.max_tries:
                    print "Exception Raised {0} retry #{1}".format(e, nb_try)
                    time.sleep(self.pause)
                    continue
                else:
                    raise
        raise ValueError

    def _handle_resp(self, resp):
        if self.verbose:
            print "http code : {0}".format(resp.status_code)
            print "content : {0}".format(resp.content)
        if resp.status_code == 200:
            return json.loads(resp.content)
        else:
            reason = "Error {0}".format(resp.status_code)
            try:
                data = json.loads(resp.content)
                if 'message' in data and data['message'] is not None:
                    reason += ": {0}".format(data['message'])
            except:
                pass
            raise IrmaError(reason)


class IrmaProbesApi(object):
    """ Probes Api
    """

    def __init__(self, apiclient):
        self._apiclient = apiclient
        return

    def list(self):
        route = '/probes'
        res = self._apiclient.get_call(route)
        return res['data']


class IrmaScansApi(object):
    """ IrmaScans Api
    """

    def __init__(self, apiclient):
        self._apiclient = apiclient
        self._scan_schema = IrmaScanSchema()
        self._results_schema = IrmaResultsSchema()
        return

    def new(self):
        route = '/scans'
        data = self._apiclient.post_call(route)
        return self._scan_schema.make_object(data)

    def get(self, scan_id):
        route = '/scans/{0}'.format(scan_id)
        data = self._apiclient.get_call(route)
        return self._scan_schema.make_object(data)

    def add(self, scan_id, filelist):
        route = '/scans/{0}/files'.format(scan_id)
        data = None
        for filepath in filelist:
            postfile = dict()
            with open(filepath, 'rb') as f:
                postfile[filepath] = f.read()
            data = self._apiclient.post_call(route, files=postfile)
        return self._scan_schema.make_object(data)

    def launch(self, scan_id, force, probe=None,
               mimetype_filtering=None, resubmit_files=None):
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        params = {'force': force}
        if mimetype_filtering is not None:
            params['mimetype_filtering'] = mimetype_filtering
        if resubmit_files is not None:
            params['resubmit_files'] = resubmit_files
        if probe is not None:
            params['probes'] = ','.join(probe)
        route = "/scans/{0}/launch".format(scan_id)
        data = self._apiclient.post_call(route,
                                         data=json.dumps(params),
                                         headers=headers)
        return self._scan_schema.make_object(data)

    def cancel(self, scan_id):
        route = '/scans/{0}/cancel'.format(scan_id)
        data = self._apiclient.post_call(route)
        return self._scan_schema.make_object(data)

    def result(self, scan_id):
        route = '/scans/{0}/results'.format(scan_id)
        data = self._apiclient.get_call(route)
        return self._scan_schema.make_object(data)

    def file_results(self, result_id, formatted=True):
        extra_args = {}
        if not formatted:
            extra_args['formatted'] = 'no'
        route = '/results/{0}'.format(result_id)
        data = self._apiclient.get_call(route, **extra_args)
        return self._results_schema.make_object(data)


class IrmaFilesApi(object):
    """ IrmaFiles Api
    """

    def __init__(self, apiclient):
        self._apiclient = apiclient
        self._results_schema = IrmaResultsSchema()
        return

    def search(self, name=None, hash=None, offset=None, limit=None):
        extra_args = {}
        if name is not None:
            extra_args['name'] = name
        elif hash is not None:
            extra_args['hash'] = hash
        if offset is not None:
            extra_args['offset'] = offset
        if limit is not None:
            extra_args['limit'] = limit
        route = '/search/files'
        data = self._apiclient.get_call(route, **extra_args)
        res_list = []
        items = data.get('items', list())
        for res in items:
            res_obj = self._results_schema.make_object(res)
            res_list.append(res_obj)
        return res_list

# =============
#  Deserialize
# =============


class IrmaFileInfoSchema(Schema):
    class Meta:
        fields = ('size', 'sha1', 'timestamp_first_scan',
                  'timestamp_last_scan', 'sha256', 'id', 'md5', 'mimetype')

    def make_object(self, data):
        return IrmaFileInfo(**data)


class IrmaFileInfo(object):
    """ IrmaFileInfo
    Description for class

    :ivar id:      id
    :ivar timestamp_first_scan: timestamp when file was first scanned in IRMA
    :ivar timestamp_last_scan: timestamp when file was last scanned in IRMA
    :ivar size:    size in bytes
    :ivar md5:     md5 hexdigest
    :ivar sha1:    sha1 hexdigest
    :ivar sha256:  sha256 hexdigest
    :ivar tags:  list of tags
    """

    def __init__(self, id, size, timestamp_first_scan,
                 timestamp_last_scan, sha1, sha256, md5, mimetype, tags):
        self.size = size
        self.sha1 = sha1
        self.timestamp_first_scan = timestamp_first_scan
        self.timestamp_last_scan = timestamp_last_scan
        self.sha256 = sha256
        self.id = id
        self.md5 = md5
        self.mimetype = mimetype
        self.tags = tags

    def __repr__(self):
        ret = "Size: {0}\n".format(self.size)
        ret += "Sha1: {0}\n".format(self.sha1)
        ret += "Sha256: {0}\n".format(self.sha256)
        ret += "Md5: {0}s\n".format(self.md5)
        ret += "First Scan: {0}\n".format(self.timestamp_first_scan)
        ret += "Last Scan: {0}\n".format(self.timestamp_last_scan)
        ret += "Id: {0}\n".format(self.id)
        ret += "Mimetype: {0}\n".format(self.mimetype)
        ret += "Tags: {0}\n".format(self.tags)
        return ret

    def raw(self):
        return IrmaFileInfoSchema()


class IrmaProbeResult(object):
    """ IrmaProbeResult
    Description for class

    :ivar status: int probe specific
        (usually -1 is error, 0 nothing found 1 something found)
    :ivar name: probe name
    :ivar type: one of IrmaProbeType
        ('antivirus', 'external', 'database', 'metadata'...)
    :ivar version: probe version
    :ivar duration: analysis duration in seconds
    :ivar results: probe results (could be str, list, dict)
    :ivar error:  error string
        (only relevant in error case when status == -1)
    :ivar external_url: remote url if available
        (only relevant when type == 'external')
    :ivar database: antivirus database digest
        (need unformatted results)
        (only relevant when type == 'antivirus')
    :ivar platform:  'linux' or 'windows'
        (need unformatted results)
    """

    def __init__(self, **kwargs):
        self.status = kwargs.pop('status')
        self.name = kwargs.pop('name')
        self.version = kwargs.pop('version', None)
        self.type = kwargs.pop('type')
        self.results = kwargs.pop('results', None)
        self.duration = kwargs.pop('duration', 0)
        self.error = kwargs.pop('error', None)
        self.external_url = kwargs.pop('external_url', None)
        self.database = kwargs.pop('database', None)
        self.platform = kwargs.pop('platform', None)
        if len(kwargs) != 0:
            print 'unmap keys: ', ','.join(kwargs.keys())

    def to_json(self):
        return IrmaProbeResultSchema().dumps(self).data

    def __str__(self):
        ret = "Status: {0}\n".format(self.status)
        ret += "Name: {0}\n".format(self.name)
        ret += "Category: {0}\n".format(self.type)
        ret += "Version: {0}\n".format(self.version)
        ret += "Duration: {0}s\n".format(self.duration)
        if self.error is not None:
            ret += "Error: {0}\n".format(self.error)
        ret += "Results: {0}\n".format(self.results)
        if self.external_url is not None:
            ret += "External URL: {0}".format(self.external_url)
        return ret


class IrmaProbeResultSchema(Schema):
    class Meta:
        fields = ('status', 'name', 'results', 'version',
                  'duration', 'type', 'error')

    def make_object(self, data):
        return IrmaProbeResult(**data)


class IrmaResults(object):
    """ IrmaResults
    Description for class

    :ivar status: int
        (0 means clean 1 at least one AV report this file as a virus)
    :ivar probes_finished: number of finished probes analysis for current file
    :ivar probes_total: number of total probes analysis for current file
    :ivar scan_id: id of the scan
    :ivar name: filename
    :ivar result_id: id of specific results for this file and this scan
     used to fetch probe_results through file_results helper function
    :ivar file_infos: IrmaFileInfo object
    :ivar probe_results: list of IrmaProbeResults objects
    """

    def __init__(self, status, probes_finished, scan_id, name,
                 probes_total, result_id, file_sha256, parent_file_sha256,
                 file_infos=None, probe_results=None):
        self.status = status
        self.probes_finished = probes_finished
        self.scan_id = scan_id
        self.name = name
        self.file_sha256 = file_sha256
        self.parent_file_sha256 = parent_file_sha256
        self.probe_results = []
        if probe_results is not None:
            for pres in probe_results:
                pobj = IrmaProbeResultSchema().make_object(pres)
                self.probe_results.append(pobj)
        else:
            self.probe_results = None
        self.probes_total = probes_total
        if file_infos is not None:
            self.file_infos = IrmaFileInfoSchema().make_object(file_infos)
        else:
            self.file_infos = None
        self.result_id = result_id

    def to_json(self):
        return IrmaResultsSchema().dumps(self).data

    def __str__(self):
        ret = "Status: {0}\n".format(self.status)
        ret += "Probes finished: {0}\n".format(self.probes_finished)
        ret += "Probes Total: {0}\n".format(self.probes_total)
        ret += "Scanid: {0}\n".format(self.scan_id)
        ret += "Filename: {0}\n".format(self.name)
        ret += "ParentFile SHA256: {0}\n".format(self.parent_file_sha256)
        ret += "Resultid: {0}\n".format(self.result_id)
        ret += "FileInfo: \n{0}\n".format(self.file_infos)
        ret += "Results: {0}\n".format(self.probe_results)
        return ret


class IrmaResultsSchema(Schema):
    probe_results = fields.Nested(IrmaProbeResultSchema, many=True)
    file_infos = fields.Nested(IrmaFileInfoSchema)

    class Meta:
        fields = ('status', 'probes_total', 'probes_finished', 'scan_id',
                  'name', 'result_id')

    def make_object(self, data):
        return IrmaResults(**data)


class IrmaScan(object):
    """ IrmaScan
    Description for class

    :ivar id: id of the scan
    :ivar status: int (one of IrmaScanStatus)
    :ivar probes_finished: number of finished probes analysis for current scan
    :ivar probes_total: number of total probes analysis for current scan
    :ivar date: scan creation date
    :ivar results: list of IrmaResults objects
    """

    def __init__(self, id, status, probes_finished,
                 probes_total, date, force, resubmit_files,
                 mimetype_filtering, results=[]):
        self.status = status
        self.probes_finished = probes_finished
        self.results = []
        if len(results) > 0:
            schema = IrmaResultsSchema()
            for r in results:
                self.results.append(schema.make_object(r))
        self.probes_total = probes_total
        self.date = date
        self.id = id
        self.force = force
        self.resubmit_files = resubmit_files
        self.mimetype_filtering = mimetype_filtering

    def is_launched(self):
        return self.status == IrmaScanStatus.launched

    def is_finished(self):
        return self.status == IrmaScanStatus.finished

    @property
    def pstatus(self):
        return IrmaScanStatus.label[self.status]

    def __repr__(self):
        ret = "Scanid: {0}\n".format(self.id)
        ret += "Status: {0}\n".format(self.pstatus)
        ret += "Options: Force [{0}] ".format(self.force)
        ret += "Mimetype [{0}] ".format(self.mimetype_filtering)
        ret += "Resubmit [{0}]\n".format(self.resubmit_files)
        ret += "Probes finished: {0}\n".format(self.probes_finished)
        ret += "Probes Total: {0}\n".format(self.probes_total)
        ret += "Date: {0}\n".format(self.date)
        ret += "Results: {0}\n".format(self.results)
        return ret


class IrmaScanSchema(Schema):
    results = fields.Nested(IrmaResultsSchema, many=True)

    class Meta:
        fields = ('status', 'probes_finished', 'date',
                  'probes_total', 'date', 'id', 'force',
                  'resumbit_files', 'mimetype_filtering')

    def make_object(self, data):
        return IrmaScan(**data)
