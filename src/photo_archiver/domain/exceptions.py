"""Domain exceptions for PhotoArchiver."""


class PhotoArchiverDomainError(Exception):
    """Base exception for domain-layer errors."""


class ValidationError(PhotoArchiverDomainError):
    """Raised when a domain value violates business validation rules."""


class RepositoryError(PhotoArchiverDomainError):
    """Raised by repository abstractions for persistence-related failures."""


class ImageUnreadableError(PhotoArchiverDomainError):
    """Raised when an image file cannot be read or decoded.

    Distinct from "no faces detected": an unreadable file (missing, locked,
    partial download, unsupported encoding) is an input problem the user can
    act on, so the recognition pipeline surfaces it per-photo instead of
    silently treating it as a faceless photo (AUDIT 2026-09-20: cv2.imread
    returned None for every Chinese-path photo and 473/473 were silently
    dropped). Lives in the domain layer so both ``ai`` adapters (raise) and
    ``application`` services (handle) may reference it per DEP rules.
    """