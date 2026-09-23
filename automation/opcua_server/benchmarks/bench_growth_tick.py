"""Embedded OPC UA server benchmarks. Not part of the fast CI suite."""

from automation.opcua_server.tests.test_growth_benchmarks import _p95_ms


def main() -> None:
    for size in (100, 1000, 10000):
        print(f"tick n={size} p95_ms={_p95_ms(size):.3f}")


if __name__ == "__main__":
    main()
