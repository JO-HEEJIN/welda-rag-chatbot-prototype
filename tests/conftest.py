"""Pytest configuration: register custom marks used in the test suite."""


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests that hit live external APIs (cost). "
        "Set RUN_INTEGRATION=1 to actually execute them.",
    )
