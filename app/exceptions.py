class AuthError(Exception):
    """Base auth error"""


class UserAlreadyExists(AuthError):
    pass


class InactiveUserException(AuthError):
    pass


class IncorrectEmailOrPasswordException(AuthError):
    pass


class AppException(Exception):
    """Базовое доменное исключение"""

    pass


class NotFoundException(AppException):
    pass


class InvalidPageException(AppException):
    pass


class OperationNotPermittedException(AppException):
    pass


class ForbiddenException(AppException):
    pass


class InvalidCredentials(AppException):
    pass


class LLMConfigurationException(AppException):
    pass


class LLMServiceException(AppException):
    pass


class LLMRequestException(AppException):
    pass
