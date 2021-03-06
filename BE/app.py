# simple app to allow GraphiQL interaction with the schema and verify it is
# structured how it ought to be. 
from flask import Flask, jsonify, request, abort, redirect, make_response
from flask_graphql import GraphQLView
from flask.views import MethodView
from sum_schema import sum_schema
from ac_schema import ac_schema
from files_schema import files_schema
from table_schema import table_schema
from indiv_files_schema import indiv_files_schema
from indiv_cases_schema import indiv_cases_schema
from models import get_url_for_download, convert_gdc_to_osdf,get_all_proj_data,get_all_proj_counts,get_manifest_data,get_all_study_data
from autocomplete_map import gql_map
import graphene
import urllib2, sys, json, re, os

application = Flask(__name__)
application.debug = True

# Function to handle access control allow headers
def add_cors_headers(response):
    fe_url = "http://%s" % (os.environ["FE_HOST"])
    response.headers['Access-Control-Allow-Origin'] = fe_url
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    if request.method == 'OPTIONS':
        response.headers['Access-Control-Allow-Methods'] = 'DELETE, GET, POST, PUT'
        headers = request.headers.get('Access-Control-Request-Headers')
        if headers:
            response.headers['Access-Control-Allow-Headers'] = headers
    return response

application.after_request(add_cors_headers)

@application.route('/gql/_mapping', methods=['GET'])
def get_maps():
    add_cors_headers
    res = jsonify({"sample.Project_name": gql_map['project_name'],
        "sample.Project_subtype": gql_map['project_subtype'],
        "sample.Study_center": gql_map['study_center'],
        "sample.Study_contact": gql_map['study_contact'],
        "sample.Study_description": gql_map['study_description'],
        "sample.Study_name": gql_map['study_name'],
        "sample.Study_srp_id": gql_map['study_srp_id'],
        "sample.Study_subtype": gql_map['study_subtype'],
        "sample.Subject_gender": gql_map['subject_gender'],
        "sample.Subject_race": gql_map['subject_race'],
        "sample.Subject_subtype": gql_map['subject_subtype'],
        "sample.Visit_date": gql_map['visit_date'],
        "sample.Visit_id": gql_map['visit_id'],
        "sample.Visit_interval": gql_map['visit_interval'],
        "sample.Visit_number": gql_map['visit_number'],
        "sample.Visit_subtype": gql_map['visit_subtype'],
        "sample.Sample_id": gql_map['sample_id'], 
        "sample.Sample_fma_body_site": gql_map['sample_fma_body_site'], 
        "sample.Sample_biome": gql_map['sample_biome'],
        "sample.Sample_body_product": gql_map['sample_body_product'],
        "sample.Sample_collection_date": gql_map['sample_collection_date'],
        "sample.Sample_env_package": gql_map['sample_env_package'],
        "sample.Sample_feature": gql_map['sample_feature'],
        "sample.Sample_geo_loc_name": gql_map['sample_geo_loc_name'],
        "sample.Sample_lat_lon": gql_map['sample_lat_lon'],
        "sample.Sample_material": gql_map['sample_material'],
        "sample.Sample_project_name": gql_map['sample_project_name'],
        "sample.Sample_rel_to_oxygen": gql_map['sample_rel_to_oxygen'],
        "sample.Sample_samp_collect_device": gql_map['sample_samp_collect_device'],
        "sample.Sample_samp_mat_process": gql_map['sample_samp_mat_process'],
        "sample.Sample_size": gql_map['sample_size'],
        "sample.Sample_subtype": gql_map['sample_subtype'],
        "sample.Sample_supersite": gql_map['sample_supersite'], 
        "file.File_format": gql_map['file_format'],
        "file.File_node_type": gql_map['file_node_type'],
        "file.File_id": gql_map['file_id']
        })
    return res

# Note the multiple endpoints going to the same "cases endpoint to accommodate GDC syntax"
@application.route('/cases', methods=['GET','OPTIONS','POST'])
@application.route('/sample', methods=['GET','OPTIONS','POST'], endpoint='sample_alt_ep')
@application.route('/file', methods=['GET','OPTIONS','POST'], endpoint='file_alt_ep')
def get_cases():
    
    filters = request.args.get('filters')
    from_num = request.args.get('from')
    size = request.args.get('size')
    order = request.args.get('sort')
    url = ""

    # Processing autocomplete here as well as finding counts for the set category
    if(request.args.get('facets') and not request.args.get('expand')):
        beg = "http://localhost:80/ac_schema?query=%7Bpagination%7Bcount%2Csort%2Cfrom%2Cpage%2Ctotal%2Cpages%2Csize%7D%2Chits%7Bproject%7Bproject_id%2Cstudy_name%2Cstudy_full_name%2Cprimary_site%7D%7Daggregations%7B"
        mid = request.args.get('facets')
        end = "%7Bbuckets%7Bkey%2Cdoc_count%7D%7D%7D%7D"
        url = '%s%s%s' % (beg,mid,end)
        response = urllib2.urlopen(url)
        r = response.read()
        data = ('%s, "warnings": {}}' % r[:-1])
        return make_json_response(data)

    else:
        if not filters:
            filters = ""
            size = 20
            from_num = 1
    #elif(request.args.get('expand') or request.args.get('filters')): # Here need to process simple/advanced queries, handling happens at GQL
        p1 = "http://localhost:80/ac_schema?query=%7Bpagination(cy%3A%22"
        p2 = "%22%2Cs%3A"
        p3 = "%2Cf%3A"
        p4 = ")%7Bcount%2Csort%2Cfrom%2Cpage%2Ctotal%2Cpages%2Csize%7D%2Chits(cy%3A%22"
        p5 = "%22%2Cs%3A"
        p6 = "%2Co%3A%22"
        p7 = "%22%2Cf%3A"
        p8 = ")%7Bproject%7Bproject_id%2Cstudy_name%2Cstudy_full_name%2Cprimary_site%7D%2Ccase_id%7Daggregations%7BProject_name%7Bbuckets%7Bkey%2Cdoc_count%7D%7DSubject_gender%7Bbuckets%7Bkey%2Cdoc_count%7D%7DSample_fma_body_site%7Bbuckets%7Bkey%2Cdoc_count%7D%7D%7D%7D"
        if len(filters) < 3:
            url = "%s%s%s%s%s%s%s%s%s%s%s%s" % (p1,p2,size,p3,from_num,p4,p5,size,p6,p7,from_num,p8)
            if request.get_data():
                f1 = request.get_data()
                f2 = json.loads(f1)
                filters = f2['filters']
                from_num = f2['from']
                order = f2['sort']
                size = f2['size']
                filters = json.dumps(filters)
                filters = convert_gdc_to_osdf(filters)
                url = "%s%s%s%s%s%s%s%s%s%s%s%s%s%s" % (p1,filters,p2,size,p3,from_num,p4,filters,p5,size,p6,p7,from_num,p8)
        else:
            filters = convert_gdc_to_osdf(filters)
            url = "%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s" % (p1,filters,p2,size,p3,from_num,p4,filters,p5,size,p6,order,p7,from_num,p8)
        response = urllib2.urlopen(url)
        r = response.read()
        data = ('%s, "warnings": {}}' % r[:-1])
        return make_json_response(data)

# Route for specific cases endpoints that associates with various files
@application.route('/cases/<case_id>', methods=['GET','OPTIONS'])
def get_case_files(case_id):
    id = '"%s"' % case_id
    if not request.args.get('expand'):
        p1 = 'http://localhost:80/files_schema?query=%7Bproject(id%3A'
        p2 = ')%7Bproject_id%2Cname%7D%2Cfiles(id%3A'
        p3 = ')%7Bdata_type%2Cfile_name%2Cdata_format%2Caccess%2Cfile_id%2Cfile_size%7D%2Ccase_id(id%3A'
        p4 = ')%2Csubmitter_id%7D'
        url = '%s%s%s%s%s%s%s' % (p1,id,p2,id,p3,id,p4) # inject ID into query
        response = urllib2.urlopen(url)
        r = response.read()
        data = ('%s, "warnings": {}}' % r[:-1])
        return make_json_response(data)
    else:
        p1 = 'http://localhost:80/indiv_cases_schema?query=%7Bcase_id(id%3A'
        p2 = ')%2Cproject(id%3A'
        p3 = ')%7Bproject_id%7D%7D'
        url = '%s%s%s%s%s' % (p1,id,p2,id,p3)
        response = urllib2.urlopen(url)
        r = response.read()
        data = ('%s, "warnings": {}}' % r[:-1])
        return make_json_response(data)

@application.route('/files/<file_id>', methods=['GET','OPTIONS'])
def get_file_metadata(file_id):
    beg = "http://localhost:80/indiv_files_schema?query=%7BfileHit(id%3A%22"
    end = "%22)%7Bdata_type%2Cfile_name%2Cfile_size%2Cdata_format%2Canalysis%7Bupdated_datetime%2Cworkflow_type%2Canalysis_id%2Cinput_files%7Bfile_id%7D%7D%2Csubmitter_id%2Caccess%2Cstate%2Cfile_id%2Cdata_category%2Cassociated_entities%7Bentity_id%2Ccase_id%2Centity_type%7D%2Ccases%7Bproject%7Bproject_id%7D%2Ccase_id%7D%2Cexperimental_strategy%7D%7D"
    url = "%s%s%s" % (beg,file_id,end)
    response = urllib2.urlopen(url)
    r = response.read()
    trimmed_r = r.replace(':{"fileHit"',"") # HACK for formatting
    final_r = trimmed_r[:-1]
    data = ('%s, "warnings": {}}' % final_r[:-1])
    return make_json_response(data)

@application.route('/status', methods=['GET','OPTIONS'])
def get_status():
    return 'OK'

@application.route('/status/user', methods=['GET','OPTIONS','POST'])
def get_status_user_unauthorized():
    return 'OK'

@application.route('/status/api/data', methods=['GET','OPTIONS','POST'])
def get_status_api_data():
    id = request.form.get('ids')
    return redirect(get_url_for_download(id))

@application.route('/files', methods=['GET','OPTIONS','POST'])
def get_files():
    filters, url = ("" for i in range(2))
    if request.args.get('filters'):
        filters = request.args.get('filters')
    elif request.get_data():
        f1 = request.get_data().decode('utf-8')
        f2 = json.loads(f1)
        filters = f2['filters']
    else: # beyond my understanding why this works at the moment
        if request.method == 'POST':
            return 'OK'
        elif request.method == 'OPTIONS':
            return 'OK'
    from_num = request.args.get('from')
    size = request.args.get('size')
    order = request.args.get('sort')
    if len(filters) < 3:
        p1 = "http://localhost:80/table_schema?query=%7Bpagination(cy%3A%22"
        p2 = "%22%2Cs%3A"
        p3 = "%2Cf%3A"
        p4 = ")%7Bcount%2Csort%2Cfrom%2Cpage%2Ctotal%2Cpages%2Csize%7D%2Chits(cy%3A%22"
        p5 = "%22%2Cs%3A"
        p6 = "%2Co%3A%22"
        p7 = "%22%2Cf%3A"
        p8 = ")%7Bdata_type%2Cfile_name%2Cdata_format%2Csubmitter_id%2Caccess%2Cstate%2Cfile_id%2Cdata_category%2Cfile_size%2Ccases%7Bproject%7Bproject_id%2Cname%7D%2Ccase_id%7Dexperimental_strategy%7D%2Caggregations%7Bdata_type%7Bbuckets%7Bkey%2Cdoc_count%7D%7Ddata_format%7Bbuckets%7Bkey%2Cdoc_count%7D%7D%7D%7D"
        url = "%s%s%s%s%s%s%s%s%s%s%s%s%s" % (p1,p2,size,p3,from_num,p4,p5,size,p6,order,p7,from_num,p8)
        if '"op"' in filters or "op" in filters:
            f1 = request.get_data()
            f2 = json.loads(f1)
            from_num = f2['from']
            order = f2['sort']
            size = f2['size']
            filters = json.dumps(filters)
            filters = convert_gdc_to_osdf(filters)
            url = "%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s" % (p1,filters,p2,size,p3,from_num,p4,filters,p5,size,p6,order,p7,from_num,p8)
    else:
        filters = convert_gdc_to_osdf(filters)
        p1 = "http://localhost:80/table_schema?query=%7Bpagination(cy%3A%22"
        p2 = "%22%2Cs%3A"
        p3 = "%2Cf%3A"
        p4 = ")%7Bcount%2Csort%2Cfrom%2Cpage%2Ctotal%2Cpages%2Csize%7D%2Chits(cy%3A%22"
        p5 = "%22%2Cs%3A"
        p6 = "%2Co%3A%22"
        p7 = "%22%2Cf%3A"
        p8 = ")%7Bdata_type%2Cfile_name%2Cdata_format%2Csubmitter_id%2Caccess%2Cstate%2Cfile_id%2Cdata_category%2Cfile_size%2Ccases%7Bproject%7Bproject_id%2Cname%7D%2Ccase_id%7Dexperimental_strategy%7D%2Caggregations%7Bdata_type%7Bbuckets%7Bkey%2Cdoc_count%7D%7Ddata_format%7Bbuckets%7Bkey%2Cdoc_count%7D%7D%7D%7D"
        url = "%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s" % (p1,filters,p2,size,p3,from_num,p4,filters,p5,size,p6,order,p7,from_num,p8)
    response = urllib2.urlopen(url)
    r = response.read()
    data = ('%s, "warnings": {}}' % r[:-1])
    return make_json_response(data)

@application.route('/projects', methods=['GET','POST'])
def get_project():
    facets = request.args.get('facets')

    # /projects request WITHOUT facets parameter
    # 
    # e.g., like this one from the portal home page: 
    #  https://gdc-api.nci.nih.gov/v0/projects?filters=%7B%7D&from=1&size=100&sort=summary.case_count:desc
    #
    # which expects a response like the following (with one hit per project and a 1-1 mapping between Project and primary_site):
    #
    # {"data": {
    #    "hits": [
    #              {"dbgap_accession_number": "phs000467", "disease_type": "Neuroblastoma", "released": true, 
    #               "state": "legacy", "primary_site": "Nervous System", "project_id": "TARGET-NBL", "name": "Neuroblastoma"},
    #     ... 
    #    "pagination": {"count": 39, "sort": "summary.case_count:desc", "from": 1, "page": 1, "total": 39, "pages": 1, "size": 100}}, 
    #    "warnings": {}}
    #
    if facets is None:
        # HACK - should go through GQL endpoint
        pdata = get_all_proj_data()
        proj_list = []

        for p in pdata:
            proj_list.append({ "project_id": p["n"]["name"], "primary_site": "multiple", "disease_type": p["n"]["description"], "released": True, "name": p["n"]["description"] })

        np = len(proj_list)

        p_str = "{ \"count\": %s, \"sort\": \"\", \"from\": 1, \"page\": 1, \"total\": %s, \"pages\": 1, \"size\": 100 }" % (np, np)
        hit_str = json.dumps(proj_list)
        data = ("{\"data\" : {\"hits\" : [ %s ], \"pagination\": %s}, \"warnings\": {}}" % (hit_str, p_str))
        return make_json_response(data)

    # /projects request WITH facets parameter
    # 
    # e.g., like this one from the portal home page: 
    #  https://gdc-api.nci.nih.gov/v0/projects?facets=primary_site&fields=primary_site,project_id,summary.case_count,summary.file_count&filters=%7B%7D&from=1&size=1000&sort=summary.case_count:desc
    #
    # which expects a response like the following (with one hit per project and an 'aggregations' field that gives
    #    the number of _projects_ associated with each primary_site):
    #
    # {"data": {
    #  "pagination": {"count": 39, "sort": "summary.case_count:desc", "from": 1, "page": 1, "total": 39, "pages": 1, "size": 1000}, 
    #  "hits": [
    #     {"project_id": "TARGET-NBL", "primary_site": "Nervous System", "summary": {"case_count": 1120, "file_count": 2803}}, 
    #     ...
    # "aggregations": {"primary_site": {"buckets": [{"key": "Kidney", "doc_count": 6}, {"key": "Adrenal Gland", "doc_count": 2}, ... ]}}}, 
    # "warnings": {}}

    # HACK - should go through GQL endpoint
    if facets == 'primary_site':
        pd = get_all_proj_counts()

        npd = len(pd)
        p_str = "{ \"count\": %d, \"sort\": \"\", \"from\": 1, \"page\": 1, \"total\": %d, \"pages\": 1, \"size\": 100 }" % (npd, npd)
        counts = {}
        hit_list = []

        for p in pd:
            proj_id = p["Study.name"]
            psite = p["Sample.fma_body_site"]
            n_files = p["file_count"]
            n_cases = p["case_count"]
            if psite is None:
                psite = "None"
            if psite in counts:
                counts[psite] = counts[psite] + 1
            else:
                counts[psite] =  1
            hit_list.append({"primary_site" : psite, "project_id": proj_id , "summary": { "case_count": n_cases, "file_count": n_files} })

        buckets_list = []
        for ckey in counts:
            ccount = counts[ckey]
            buckets_list.append({ "key": ckey, "doc_count": ccount})

        buckets_str = json.dumps(buckets_list)
        hit_str = json.dumps(hit_list)
        agg_str = "{ \"primary_site\": { \"buckets\": %s }}" % (buckets_str)

        data = ("{\"data\" : {\"aggregations\": %s, \"hits\" : %s, \"pagination\": %s}, \"warnings\": {}}" % (agg_str, hit_str, p_str))
        return make_json_response(data)

    # Enter here if going to the projects tab
    else:
        pdata = get_all_study_data()
        proj_list = []
        print pdata

        for p in pdata:
            print p
            proj_list.append({ "project_id": p["Study.name"], "disease_type": p["Study.full_name"], "project_name": p["Project.subtype"], "summary": { "case_count": p["case_count"], "file_count": p["file_count"]} })
        np = len(proj_list)

        p_str = "{ \"count\": %s, \"sort\": \"\", \"from\": 1, \"page\": 1, \"total\": %s, \"pages\": 1, \"size\": 100 }" % (np, np)
        hit_str = json.dumps(proj_list)
        data = ("{\"data\" : {\"hits\" :  %s , \"pagination\": %s}, \"warnings\": {}}" % (hit_str, p_str))
        return make_json_response(data)

@application.route('/annotations', methods=['GET','OPTIONS'])
def get_annotation():
    return 'hi'

# Calls sum_schema endpoint/GQL instance in order to return the necessary data
# to populate the pie charts
@application.route('/ui/search/summary', methods=['GET','OPTIONS','POST'])
def get_ui_search_summary():
    empty_cy = ("http://localhost:80/sum_schema?query="
        "%7BSampleFmabodysite(cy%3A%22%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7D"
        "ProjectName(cy%3A%22%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7D"
        "SubjectGender(cy%3A%22%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7D"
        "FileFormat(cy%3A%22%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7D"
        "FileSubtype(cy%3A%22%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7D"
        "StudyName(cy%3A%22%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7D"
        "%2Cfs(cy%3A%22%22)%7Bvalue%7D%7D"
        )
    p1 = "http://localhost:80/sum_schema?query=%7BSampleFmabodysite(cy%3A%22" # inject Cypher into ... body site query
    p2 = "%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7DProjectName(cy%3A%22" #     ... project name query
    p3 = "%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7DSubjectGender(cy%3A%22" #   ... subject gender query
    p4 = "%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7DFileFormat(cy%3A%22" #      ... file format query
    p5 = "%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7DFileSubtype(cy%3A%22" #     ... file subtype query
    p6 = "%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7DStudyName(cy%3A%22" #       ... study name query
    p7 = "%22)%7Bbuckets%7Bcase_count%2Cdoc_count%2Cfile_size%2Ckey%7D%7D%2Cfs(cy%3A%22" #           ... file size query
    p8 = "%22)%7Bvalue%7D%7D"
    filters = request.get_data()
    url = ""
    if filters: # only modify call if filters arg is present
        filters = filters[:-1] # hack to get rid of "filters" root of JSON data
        filters = filters[11:]
        filters = convert_gdc_to_osdf(filters)
        if len(filters) > 2: # need actual content in the JSON, not empty
            url = "%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s" % (p1,filters,p2,filters,p3,filters,p4,filters,p5,filters,p6,filters,p7,filters,p8) 
        else:
            url = empty_cy # no Cypher parameters entered
    else:
        url = empty_cy
    response = urllib2.urlopen(url)
    # another hack, remove "data" root from GQL results
    r1 = response.read()[8:]
    r2 = r1[:-1]
    data = r1[:-1]
    return make_json_response(data)

@application.route('/status/api/manifest', methods=['GET','OPTIONS','POST'])
def get_manifest():
    string = 'id\tfilename\tmd5\tsize' # header
    ids = request.form.getlist('ids')
    data = get_manifest_data(ids) # get all the relevant properties for this file
    
    for result in data:
        string += result

    response = make_response(string)

    # If we've processed the data, reset the cookie key for the cart.
    cookie = request.form.get('downloadCookieKey')
    response.set_cookie(cookie,'',expires=0)
    
    response.headers["Content-Disposition"] = "attachment; filename=result.tsv"
    return response

# Function to add a JSON content type to the response, takes in the data that 
# is to be returned
def make_json_response(data):
    response = make_response(data)
    response.headers['Content-Type'] = 'application/json'
    return response

application.add_url_rule(
    '/sum_schema',
    view_func=GraphQLView.as_view(
        'sum_graphql',
        schema=sum_schema,
        graphiql=True
    )
)

application.add_url_rule(
    '/ac_schema',
    view_func=GraphQLView.as_view(
        'ac_graphql',
        schema=ac_schema,
        graphiql=True
    )
)

application.add_url_rule(
    '/files_schema',
    view_func=GraphQLView.as_view(
        'files_graphql',
        schema=files_schema,
        graphiql=True
    )
)

application.add_url_rule(
    '/table_schema',
    view_func=GraphQLView.as_view(
        'table_graphql',
        schema=table_schema,
        graphiql=True
    )
)

application.add_url_rule(
    '/indiv_files_schema',
    view_func=GraphQLView.as_view(
        'indiv_files_graphql',
        schema=indiv_files_schema,
        graphiql=True
    )
)

application.add_url_rule(
    '/indiv_cases_schema',
    view_func=GraphQLView.as_view(
        'indiv_cases_graphql',
        schema=indiv_cases_schema,
        graphiql=True
    )
)

if __name__ == '__main__':
    application.run(host='0.0.0.0',port=80,threaded=True)
