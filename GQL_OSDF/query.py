import urllib2, re, json
from multiprocessing import Process, Queue, Pool
import models
#from py2neo import Graph

# The match var is the base query to prepend all queries. The idea is to traverse
# the graph entirely and use filters to return a subset of the total traversal. 
match = "MATCH (Project)<-[:PART_OF]-(Study)<-[:PARTICIPATES_IN]-(Subject)<-[:BY]-(Visit)<-[:COLLECTED_DURING]-(Sample)<-[:PREPARED_FROM]-(pf)<-[:SEQUENCED_FROM]-(sf)<-[:COMPUTED_FROM]-(cf) WHERE"

# test strings with roughly increasing complexity
tstr = '{"op":"and","content":[{"op":"in","content":{"field":"cases.Project.name","value":["Human Microbiome Project (HMP)"]}}]}'
tstr2 = '{"op":"and","content":[{"op":"AND","content":[{"op":"in","content":{"field":"cases.Project.name","value":["Human Microbiome Project (HMP)"]}},{"op":"OR","content":[{"op":"=","content":{"field":"cases.Sample.fma_body_site","value":"right cubital fossa [FMA:39849]"}},{"op":"=","content":{"field":"cases.Sample.fma_body_site","value":"Gingiva [FMA:59762]"}}]}]}]}'
tstr3 = '{"op":"and","content":[{"op":"OR","content":[{"op":"=","content":{"field":"cases.project.disease_type","value":"Acute Myeloid Leukemia"}},{"op":"OR","content":[{"op":"=","content":{"field":"cases.project.name","value":"Neuroblastoma"}},{"op":"=","content":{"field":"cases.case_id","value":"0004d251-3f70-4395-b175-c94c2f5b1b81"}}]}]}]}'
tstr4 = '{"op":"and","content":[{"op":"OR","content":[{"op":"=","content":{"field":"cases.project.disease_type","value":"Acute Myeloid Leukemia"}},{"op":"OR","content":[{"op":"=","content":{"field":"cases.project.name","value":"Neuroblastoma"}},{"op":"OR","content":[{"op":"=","content":{"field":"cases.case_id","value":"0004d251-3f70-4395-b175-c94c2f5b1b81"}},{"op":"=","content":{"field":"cases.demographic.ethnicity","value":"not reported"}}]}]}]}]}'
tstr5 = '{"op":"and","content":[{"op":"in","content":{"field":"cases.project.primary_site","value":["Kidney","Brain","Nervous System"]}}]}'
tstr6 = '{"op":"and","content":[{"op":"in","content":{"field":"cases.project.primary_site","value":["Kidney","Brain","Nervous System"]}},{"op":"in","content":{"field":"cases.project.program.name","value":["TCGA"]}}]}'
tstr7 = '{"op":"and","content":[{"op":"AND","content":[{"op":"in","content":{"field":"cases.ProjectName","value":["Human Microbiome Project (HMP)","iHMP"]}},{"op":"=","content":{"field":"cases.SampleFmabodysite","value":"Vagina [FMA:19949]"}}]}]}'

comp_ops = ["=",">",">=","<","<=","!=","EXCLUDE","IN","in","IS","NOT"] # only found in advanced search
comp_ops2 = ["AND","OR"] # separate group to delineate when to combine left/right halves of string
comps = set(comp_ops)
comps2 = set(comp_ops2)

# This is a recursive function originally used to traverse and find the depth 
# of nested JSON. Now used to traverse the op/filters query from GDC and 
# ultimately aims to provide input to build the WHERE clause of a Cypher query. 
# Accepts input of json.loads parsed GDC portal query input and an empty array.
def get_depth(x, arr):
    if type(x) is dict and x:
        if 'op' in x:
            arr.append(x['op'])
        if 'field' in x:
            left = x['field']
            right = x['value']
            if type(x['value']) is list:
                l = x['value']
                l = ["'{0}'".format(element) for element in l] # need to add quotes around each element to make Cypher happy
                right = ",".join(l)
            else:
                right = "'{0}'".format(right) # again, quotes for Cypher
            arr.append(left)
            arr.append(right)
        return max(get_depth(x[a], arr) for a in x)
    if type(x) is list and x: 
        return max(get_depth(a, arr) for a in x)
    return arr # give the array back after traversal is complete

# Fxn to build Cypher based on facet search, accepts output from get_depth
def build_facet_where(inp): 
    facets = [] # going to build an array of all the facets params present
    lstr, rstr = ("" for i in range(2))
    for x in reversed(range(0,len(inp))):
        if "'" in inp[x]: # found the values to search for
            rstr = "[%s]" % (inp[x]) # add brackets for Cypher
        elif "." in inp[x]: # found the fields to search on
            lstr = inp[x]
        elif "in" == inp[x]: # found the comparison op, build the full string
            facets.append("%s in %s" % (lstr, rstr))
    return " AND ".join(facets) # send back Cypher-ready WHERE clause

# Fxn to build Cypher based on advanced search, accepts output from get_depth
def build_advanced_where(inp): 
    skip_me = set()
    lstr, rstr = ("" for i in range(2)) # right/left strings to combine
    # Makes more sense to build up than it is to build down.
    for x in reversed(range(1,len(inp))):  
        if x in skip_me: # pass over elements we know are already consumed
            pass
        elif inp[x-2] in comps: # case to build comparison statement
            if inp[x-2] == "in": # need to add brackets for Cypher if list present
                inp[x] = "[%s]" % (inp[x])

            if lstr == "":
                lstr = "%s %s %s" % (inp[x-1],inp[x-2],inp[x])
            else:
                rstr = "%s %s %s" % (inp[x-1],inp[x-2],inp[x])
            skip_me.update(range(x-2,x))
        else: # process the overarching AND/OR of the WHERE
            if inp[x] in comps2: # check for clarity
                rstr = "%s %s %s" % (lstr,inp[x],rstr)
                lstr = "" # reset, rstr will be built upon
    return rstr # send back Cypher-ready WHERE clause

# Builds the Cypher WHERE clause, accepts output from GDC-portal filters argument
def build_where(filters): 
    arr = [] # need an empty array for depth recursion
    qtype = "facet" # by default, set as facet search
    q = json.loads(filters) # parse filters input into JSON (yields hashes of arrays)
    w1 = get_depth(q, arr) # first step of building where clause is the array of individual comparison elements
    w2 = "" # final where clause entity

    for x in reversed(range(1,len(w1))): # search for AND/OR which are unique syntax for advanced query
        if w1[x] in comps2:
            qtype = "advanced"
            break

    if qtype == "facet": # decide between which WHERE builder to use
        w2 = build_facet_where(w1)
    elif qtype == "advanced": # written for clarity
        w2 = build_advanced_where(w1)
    return w2

returns = {
    'cases': "RETURN Project.name, Project.subtype, Sample.fma_body_site, Sample._id, Study.name",
    'files': "RETURN Project, sf, cf, Sample._id",
    'project': "RETURN Project.name as prop, count(Project.name) as counts",
    'bodysite': "RETURN Sample.fma_body_site as prop, count(Sample.fma_body_site) as counts",
    'study': "RETURN Study.name as prop, count(Study.name) as counts",
    'gender': "RETURN Subject.gender as prop, count(Subject.gender) as counts",
    'race': "RETURN Subject.race as prop, count(Subject.race) as counts",
    'format': "RETURN sf.format as prop, count(sf.format) as counts",
    'size': "RETURN (SUM(toInt(sf.size))+SUM(toInt(cf.size))) as tot"
}

# Final function needed to build the entirety of the Cypher query. Accepts the following:
# match = base MATCH query for Cypher
# whereFilters = filters string passed from GDC portal
# order = parameters to order results by (needed for pagination)
# start = index of sort to start at
# size = number of results to return
# rtype = return type, want to be able to hit this for both cases, files, and aggregation counts.
def build_cypher(match,whereFilters,order,start,size,rtype):
    where = build_where(whereFilters) # build WHERE portion of Cypher
    where = where.replace("cases.","") # trim the GDC syntax, hack until we refactor cases/files syntax
    where = where.replace("files.","")
    order = order.replace("cases.","")
    order = order.replace("files.","")
    retval1 = returns[rtype] # actual RETURN portion of statement
    order = order.split(":")
    retval2 = "ORDER BY %s %s SKIP %s LIMIT %s" % (order[0],order[1].upper(),start-1,size) # handle pagination for RETURN

    print "%s %s %s %s" % (match,where,retval1,retval2)

build_cypher(match,tstr,"Sample._id:asc",1,20,"cases")

def parallel_exe(fxns):
    proc = []
    for fn in fxns:
        p = Process(target=fn) # assign each function a thread
        p.start() # initiate each thread as it goes
        proc.append(p)
    for p in proc:
        p.join() # wait for all to finish
