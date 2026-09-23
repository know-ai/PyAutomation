"""Generic registry: duplicate keys, decorator registration, two threads."""

import threading
import unittest

from automation.opcua_server.registry import Registry, register_exposer


class TestRegistry(unittest.TestCase):
    def test_duplicate_key_raises(self):
        registry = Registry("probe")
        registry.register("a", object())
        with self.assertRaises(ValueError):
            registry.register("a", object())

    def test_same_object_twice_is_idempotent(self):
        registry = Registry("probe")
        item = object()
        registry.register("a", item)
        registry.register("a", item)
        self.assertIs(registry.get("a"), item)

    def test_decorator_registers_a_class(self):
        @register_exposer
        class Extra:
            entity_kind = "probe-extra"

        from automation.opcua_server.registry import exposer_registry

        self.assertIs(exposer_registry.get("probe-extra"), Extra)

    def test_two_threads_do_not_drop_distinct_keys(self):
        registry = Registry("threads")
        errors = []

        def add(key):
            try:
                registry.register(key, key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add, args=(f"k{i}",)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(registry.all()), 2)
