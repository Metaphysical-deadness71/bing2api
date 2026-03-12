class BingAPIError(Exception):
    """Base error for the async Bing API package."""


class AccountNotFoundError(BingAPIError):
    """Raised when an account is missing from storage."""


class InvalidAccountConfigError(BingAPIError):
    """Raised when account cookies or setup are invalid."""


class ParseError(BingAPIError):
    """Raised when a Bing response cannot be parsed."""


class SkeyMissingError(BingAPIError):
    """Raised when a video detail request requires skey but none exists."""


class VideoGenerationError(BingAPIError):
    """Raised when video generation fails or times out."""


class BootstrapError(BingAPIError):
    """Raised when automatic skey bootstrap fails."""
