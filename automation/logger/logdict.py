# -*- coding: utf-8 -*-
"""automation/logger/logdict.py

This module implements a dictionary-based helper class to organize and validate
tags that need to be logged, grouping them by sampling period.
"""


class LogTable(dict):
    r"""
    A specialized dictionary for managing logging configurations.

    Structure:
    `{ period (float): [tag_name_1, tag_name_2, ...] }`

    It validates entries and provides helper methods to retrieve tags by group or individually.
    """

    def __init__(self):

        pass

    def validate(self, period, tag):
        r"""
        Validates a period-tag pair.

        **Parameters:**

        * **period** (int|float): Sampling period.
        * **tag** (str): Tag name.

        **Returns:**

        * **bool**: True if valid.
        """
        if not type(period) in [int, float]:
            return False
        
        if type(tag) != str:
            return False

        return True

    def get_groups(self):
        r"""
        Retrieves all defined sampling periods (groups).

        **Returns:**

        * **list**: List of periods.
        """
        return list(self.keys())

    def get_tags(self, group):
        r"""
        Retrieves all tags for a specific sampling period.

        **Parameters:**

        * **group** (float): Sampling period.

        **Returns:**

        * **list**: List of tag names.
        """
        return self[group]

    def get_all_tags(self):
        r"""
        Retrieves a flat list of all tags across all groups.

        **Returns:**

        * **list**: List of tag names.
        """
        result = list()

        for group in self.get_groups():

            result += self.get_tags(group)

        return result

    def get_period(self, tag):
        r"""
        Finds the sampling period for a given tag.

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **float**: The period if found, else None.
        """
        for key, value in self.items():

            if tag in value:
                return key

    def serialize(self):
        r"""
        Returns the dictionary representation of the LogTable.
        """
        return self
