# -*- coding: utf-8 -*-
"""pyhades/logger/logdict.py

This module implements a dictionary based Class to hold
the tags to be logged.
"""


class LogTable(dict):

    def __init__(self):

        pass

    def validate(self, period, tag):
        
        if not type(period) in [int, float]:
            return False
        
        if type(tag) != str:
            return False

        return True

    def get_groups(self):

        return list(self.keys())

    def get_tags(self, group):

        return self[group]

    def get_all_tags(self):

        result = list()

        for group in self.get_groups():

            result += self.get_tags(group)

        return result

    def get_period(self, tag):

        for key, value in self.items():

            if tag in value:
                return key

    def serialize(self):

        return self
    
