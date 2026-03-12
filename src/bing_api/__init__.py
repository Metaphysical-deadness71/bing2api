__version__ = "0.1.0"


def create_app():
    from bing_api.api.app import create_app as app_factory

    return app_factory()


__all__ = ["__version__", "create_app"]
