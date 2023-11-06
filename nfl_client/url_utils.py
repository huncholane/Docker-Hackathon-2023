import yaml
from urllib.parse import urlparse, parse_qs
import re
import json
import inflect

def unpluralize_word(word):
    p = inflect.engine()
    singular_form = p.singular_noun(word)
    return singular_form if singular_form else word


def add_brackets(word):
    return '{'+word+'}'


id_re = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


def urlparse_json(url):
    r = urlparse(url)
    path = r.path
    query_params = {}
    for key, item in parse_qs(r.query).items():
        item_type = 'string'
        example = ''
        if len(item) > 1:
            item_type = 'array'
            example = ','.join(item)
        if len(item) == 1:
            example = item[0]
            try:
                example = float(item[0])
                item_type = 'number'
            except:
                pass
            try:
                example = int(item[0])
                item_type = 'integer'
            except:
                pass
            if item[0] in ['true', 'false']:
                item_type = 'boolean'
        query_params.update({
            key: {
                'type': item_type,
                'example': example
            }
        })
    
    # Extract path parameters
    path_params = {}
    last_ind = -1
    path_split = path.split('/')
    for item in path.split('/'):
        last = ''
        if last_ind > 0:
            last = path_split[last_ind]
        id_match = id_re.search(item)
        if id_match:
            uuid = id_match.group(0)
            name = unpluralize_word(last)+'_id'
            path = path.replace(uuid, add_brackets(name))
            path_params.update({name: {'type': 'string', 'example': uuid}})
        try: 
            int(item)
            name = unpluralize_word(last)
            path = path.replace(item, add_brackets(name))
            path_params.update({name: {'type': 'integer', 'example': int(item)}})
        except:
            pass
        if item.isupper():
            name = unpluralize_word(last)
            path = path.replace(item, add_brackets(name))
            path_params.update({name: {'type': 'string', 'example': item}})
        last_ind += 1

    return {
        path: {
            'query_parameters': query_params,
            'path_parameters': path_params
        }
    }


def har_entry_parse(entry):
    """Parses an entry from har file into openapi ready json"""
    url_data = urlparse_json(entry['request']['url'])
    endpoint = next(iter(url_data))
    url_data[endpoint]['response_sample'] = json.loads(entry['response']['content']['text'])
    return url_data


def add_api_component(openapi_spec, path, info):
    """Adds info for a single endpoint"""
    path_parameters = info['path_parameters']
    query_parameters = info['query_parameters']
    openapi_spec['paths'].update({
        path: {
            'get': {
                'parameters': [],
                'responses': {
                    '200': {
                        'description': 'Successful response',
                        'content': {
                            'application/json': {
                                'example': info['response_sample']
                            }
                        }
                    },
                },
            },
        },
    })

    if path_parameters:
        for param_name, param_details in path_parameters.items():
            openapi_spec['paths'][path]['get']['parameters'].append({
                'name': param_name,
                'in': 'path',
                'required': True,
                'schema': {
                    'type': param_details['type'],
                },
                'description': f'The {param_name} parameter',
                'example': param_details['example']
            })

    if query_parameters:
        for param_name, param_details in query_parameters.items():
            openapi_spec['paths'][path]['get']['parameters'].append({
                'name': param_name,
                'in': 'query',
                'schema': {
                    'type': param_details['type'],
                },
                'description': f'The {param_name} parameter',
                'example': param_details['example']
            })


def generate_openapi_spec(url_json):
    """Takes in a dict of url json data to format into openapi"""
    openapi_spec = {
        'openapi': '3.0.0',
        'info': {
            'title': 'NFL API',
            'version': '1.0.0',
        },
        'paths': {}
    } 
    for path, info in url_json.items():
        add_api_component(openapi_spec, path, info)
    return yaml.dump(openapi_spec, default_flow_style=False)
