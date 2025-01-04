class BooruException(Exception):
    """Base exception for booru operations."""
    pass

class SourceNotFound(BooruException):
    """Raised when a booru source is not found."""
    pass

class CredentialsRequired(BooruException):
    """Raised when credentials are required but not provided."""
    pass

class RequestError(BooruException):
    """Raised when a request to a booru site fails."""
    pass

class PostParseError(BooruException):
    """Raised when post data cannot be parsed."""
    pass
