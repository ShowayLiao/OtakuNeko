def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "capability_contract(name, version, scenario): required public contract observation",
    )
