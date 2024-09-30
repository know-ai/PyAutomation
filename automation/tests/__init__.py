
def assert_dict_contains_subset(subset, superset, msg=None):
        """
        Custom assertion to check if `subset` is a subset of `superset`.
        """
        missing_keys = {key for key in subset if key not in superset}
        assert not missing_keys, f"{msg or 'Dictionary subset check failed'}: Missing keys {missing_keys}"

        for key, value in subset.items():
            assert superset[key] == value, f"{msg or 'Dictionary subset check failed'}: Value mismatch for key '{key}'"