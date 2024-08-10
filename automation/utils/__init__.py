from .observer import Observer
import logging
from automation.variables import VARIABLES

def log_detailed(e, message):
    
    logging.error(message)
    logging.error(e, exc_info=True)

def find_differences_between_lists(prev_list, curr_list):
    r"""
    Documentation here
    """
    
    differences = []

    for prev_dict, curr_dict in zip(prev_list, curr_list):
        diff = {'id': prev_dict['id']}
        for key in prev_dict:
            if prev_dict[key] != curr_dict[key]:
                diff[key] = curr_dict[key]
        if len(diff) > 1:  # Only add if there are differences other than 'id'
            differences.append(diff)
    
    return differences

def find_keys_values_by_unit(d, unit):
    r"""
    Documentation here
    """
    result = []
    
    for _, sub_dict in d.items():
        
        if unit in sub_dict.values():
            
            for k, v in sub_dict.items():
                
                result.append({'label': k, 'value': v})

    return result

def generate_dropdown_conditional():
    r"""
    Documentation here
    """
    data = VARIABLES
    dropdown_conditional = []

    for key, sub_dict in data.items():

        for unit in sub_dict.values():

            options = find_keys_values_by_unit(data, unit)
            
            dropdown_conditional.append({
                'if': {'column_id': 'unit', 'filter_query': f'{{unit}} eq "{unit}"'},
                'options': options
            })
    return dropdown_conditional