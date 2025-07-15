import os
from tqdm import tqdm
from acdh_cidoc_pyutils import (
    make_birth_death_entities,
    make_entity_label,
)
from utils.utilities import (
    make_e42_identifiers_utils,
    create_triple_from_node,
    create_birth_death_settlement_graph
)
from acdh_cidoc_pyutils.namespaces import CIDOC, FRBROO
from acdh_tei_pyutils.tei import TeiReader
from rdflib import Graph, Namespace, URIRef, plugin, ConjunctiveGraph, Literal
from rdflib.namespace import RDF, RDFS
from rdflib.store import Store


LK = Namespace("https://sk.acdh.oeaw.ac.at/project/legal-kraus")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")

store = plugin.get("Memory", Store)()
project_store = plugin.get("Memory", Store)()

if os.environ.get("NO_LIMIT"):
    LIMIT = False
    print("no limit")
else:
    LIMIT = 100

rdf_dir = "./rdf"
os.makedirs(rdf_dir, exist_ok=True)
domain = "https://sk.acdh.oeaw.ac.at/"
SK = Namespace(domain)

project_uri = URIRef(f"{SK}project/legal-kraus")
g = Graph(identifier=project_uri, store=project_store)
g.bind("cidoc", CIDOC)
g.bind("frbroo", FRBROO)
g.bind("sk", SK)
g.bind("lk", LK)
g.bind("geo", GEO)
entity_type = "person"
index_file = f"./data/indices/list{entity_type}.xml"
doc = TeiReader(index_file)
nsmap = doc.nsmap
items = doc.any_xpath(f".//tei:{entity_type}")
if LIMIT:
    items = items[:LIMIT]

g.add((URIRef(f"{SK}types/place/placename"), RDF.type, CIDOC["E55_Type"]))
g.add((URIRef(f"{SK}types/idno/xml-id"), RDF.type, CIDOC["E55_Type"]))
g.add((URIRef(f"{SK}types/idno/URL/geonames"), RDF.type, CIDOC["E55_Type"]))
g.add((URIRef(f"{SK}types/idno/URL/wikidata"), RDF.type, CIDOC["E55_Type"]))
g.add((URIRef(f"{SK}types/person/persname/female"), RDF.type, CIDOC["E55_Type"]))
g.add((URIRef(f"{SK}types/person/persname/male"), RDF.type, CIDOC["E55_Type"]))
# g.add((URIRef(f"{SK}types/person/persname/pref"), RDF.type, CIDOC["E55_Type"]))

print(f"converting {entity_type}s derived from {index_file}")
for x in tqdm(items, total=len(items)):
    xml_id = x.attrib["{http://www.w3.org/XML/1998/namespace}id"]
    item_id = f"{SK}{xml_id}"
    subj = URIRef(item_id)
    name_node = x.xpath(".//tei:persName", namespaces=nsmap)
    item_label = make_entity_label(name_node[0])[0]
    g.add((subj, RDF.type, CIDOC["E21_Person"]))
    g.add((subj, RDFS.label, Literal(item_label)))
    g += make_e42_identifiers_utils(
        subj, x, type_domain=f"{SK}types", default_lang="en", same_as=False
    )
    # g += make_appellations(subj, x, type_domain=f"{SK}types", woke_type="pref", default_lang="und")
    # create appellations
    g += create_triple_from_node(
        node=x,
        subj=subj,
        subj_suffix="appellation",
        pred=CIDOC["P2_has_type"],
        sbj_class=CIDOC["E33_E41_Linguistic_Appellation"],
        obj_class=CIDOC["E55_Type"],
        obj_node_xpath="./tei:persName",
        obj_node_value_xpath="./@type",
        obj_node_value_alt_xpath_or_str="pref",
        obj_prefix=f"{SK}types",
        default_lang="und",
        value_literal=True,
        identifier=CIDOC["P1_is_identified_by"]
    )
    # add additional type for appellations
    g += create_triple_from_node(
        node=x,
        subj=subj,
        subj_suffix="appellation",
        pred=CIDOC["P2_has_type"],
        obj_class=CIDOC["P2_has_type"],
        obj_node_xpath="./tei:persName",
        obj_node_value_xpath="./@sex",
        obj_node_value_alt_xpath_or_str="./parent::tei:person/tei:sex/@value",
        obj_prefix=f"{SK}types",
        skip_value="not-set"
    )
    # add occupations
    g += create_triple_from_node(
        node=x,
        subj=subj,
        subj_suffix="occupation",
        pred=CIDOC["P10_falls_within"],
        sbj_class=FRBROO["F51_Pursuit"],
        obj_node_xpath="./tei:occupation",
        obj_node_value_xpath=None,
        obj_process_condition="./@type='sk'",
        obj_class=CIDOC["E4_Period"],
        default_lang="en",
        label_prefix="Employment with: ",
        identifier=CIDOC["P14i_performed"],
        custom_obj_uri="period",
        obj_prefix="https://sk.acdh.oeaw.ac.at",
    )
    # g += make_affiliations(
    #     subj,
    #     x,
    #     domain,
    #     person_label=item_label,
    #     org_id_xpath="./tei:orgName[1]/@key",
    #     org_label_xpath="./tei:orgName[1]//text()",
    # )
    if x.xpath("./tei:birth", namespaces=nsmap):
        try:
            date_node = x.xpath("./tei:birth/tei:date[@type]", namespaces=nsmap)[0]
        except IndexError:
            date_node = None
        if date_node is not None:
            date_type = date_node.attrib["type"]
            if date_type == "approx":
                date_type_uri = URIRef(f"{SK}types/date/{date_type}")
        else:
            date_type_uri = False
        birth_g, birth_uri, birth_timestamp = make_birth_death_entities(
            subj,
            x,
            domain=SK,
            event_type="birth",
            type_uri=date_type_uri,
            verbose=False,
            default_prefix="Birth of",
            default_lang="en",
            date_node_xpath="/tei:date[1]",
            place_id_xpath="//tei:settlement[1]/@key",
        )
        g += birth_g
    if x.xpath("./tei:birth[./tei:settlement]", namespaces=nsmap):
        try:
            birth_place_node = x.xpath(
                "./tei:birth/tei:settlement", namespaces=nsmap
            )[0]
        except IndexError:
            birth_place_node = None
        if birth_place_node is not None:
            g += create_birth_death_settlement_graph(
                node=birth_place_node,
                namespaces=nsmap,
                uri_prefix=SK,
                node_attrib="key"
            )
    if x.xpath("./tei:death", namespaces=nsmap):
        try:
            date_node = x.xpath("./tei:death/tei:date[@type]", namespaces=nsmap)[0]
        except IndexError:
            date_node = None
        if date_node is not None:
            date_type = date_node.attrib["type"]
            if date_type == "approx":
                date_type_uri = URIRef(f"{SK}types/date/{date_type}")
        else:
            date_type_uri = False
        death_g, death_uri, death_timestamp = make_birth_death_entities(
            subj,
            x,
            domain=SK,
            event_type="death",
            type_uri=date_type_uri,
            verbose=False,
            default_prefix="Death of",
            default_lang="en",
            date_node_xpath="/tei:date[1]",
            place_id_xpath="//tei:settlement[1]/@key",
        )
        g += death_g
    if x.xpath("./tei:death[./tei:settlement]", namespaces=nsmap):
        try:
            death_place_node = x.xpath(
                "./tei:death/tei:settlement", namespaces=nsmap
            )[0]
        except IndexError:
            death_place_node = None
        if death_place_node is not None:
            g += create_birth_death_settlement_graph(
                node=death_place_node,
                namespaces=nsmap,
                uri_prefix=SK,
                node_attrib="key"
            )

# # ORGS
# entity_type = "org"
# index_file = f"./data/indices/list{entity_type}.xml"
# doc = TeiReader(index_file)
# nsmap = doc.nsmap
# items = doc.any_xpath(f".//tei:{entity_type}")
# if LIMIT:
#     items = items[:LIMIT]
# print(f"converting {entity_type}s derived from {index_file}")
# for x in tqdm(items, total=len(items)):
#     xml_id = x.attrib["{http://www.w3.org/XML/1998/namespace}id"]
#     item_id = f"{SK}{xml_id}"
#     subj = URIRef(item_id)
#     g.add((subj, RDF.type, CIDOC["E74_Group"]))
#     # g += make_appellations(subj, x, type_domain=f"{SK}types/", default_lang="und")
#     obj = x.xpath("./tei:orgName[1]", namespaces=nsmap)[0]
#     g1, label = create_object_literal_graph(
#         node=obj,
#         subject_uri=subj,
#         default_lang="und",
#         predicate=RDFS.label,
#         l_prefix=""
#     )
#     g += g1
#     g += make_e42_identifiers_utils(
#         subj, x, type_domain=f"{SK}types", default_lang="en", same_as=False
#     )

# # PLACES
# entity_type = "place"
# index_file = f"./data/indices/list{entity_type}.xml"
# doc = TeiReader(index_file)
# nsmap = doc.nsmap
# items = doc.any_xpath(f".//tei:{entity_type}")
# if LIMIT:
#     items = items[:LIMIT]
# print(f"converting {entity_type}s derived from {index_file}")
# for x in tqdm(items, total=len(items)):
#     xml_id = x.attrib["{http://www.w3.org/XML/1998/namespace}id"]
#     item_id = f"{SK}{xml_id}"
#     subj = URIRef(item_id)
#     g.add((subj, RDF.type, CIDOC["E53_Place"]))
#     g += coordinates_to_p168(subj, x)
#     g += make_appellations(subj, x, type_domain=f"{SK}types/", default_lang="und")
#     g += make_e42_identifiers(
#         subj, x, type_domain=f"{SK}types", default_lang="und", same_as=False
#     )
#     try:
#         pmb = x.xpath('.//tei:idno[@type="pmb"]/text()', namespaces=nsmap)[0]
#     except IndexError:
#         pmb = None
#     if pmb:
#         pmb_uri = URIRef(pmb)
#         g.add((subj, OWL["sameAs"], pmb_uri))
#         g.add((pmb_uri, RDF.type, CIDOC["E42_Identifier"]))

print("writing graph to file: data.trig")
g_all = ConjunctiveGraph(store=project_store)
g_all.serialize(f"{rdf_dir}/data.trig", format="trig")
g_all.serialize(f"{rdf_dir}/data.ttl", format="ttl")
