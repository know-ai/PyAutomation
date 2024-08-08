from .observer import Observer
import logging

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