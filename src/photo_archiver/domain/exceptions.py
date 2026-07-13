"""Domain exceptions for PhotoArchiver."""


class PhotoArchiverDomainError(Exception):
    """Base exception for domain-layer errors."""


class ValidationError(PhotoArchiverDomainError):
    """Raised when a domain value violates business validation rules."""


class RepositoryError(PhotoArchiverDomainError):
    """Raised by repository abstractions for persistence-related failures."""