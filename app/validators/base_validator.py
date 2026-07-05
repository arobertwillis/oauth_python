"""
Base class for custom configuration validators.

To create a custom validator:
1. Create a new .py file in app/validators/
2. Subclass BaseValidator
3. Implement the validate() method

The validator will be automatically discovered and executed during file uploads.
"""

from abc import ABC, abstractmethod
from typing import Any, List


class BaseValidator(ABC):
    """
    Abstract base class for custom file validators.

    Subclasses are discovered automatically and run after JSON Schema
    validation passes.  They allow deep, programmatic checks that go
    beyond structural validation (e.g. verifying a connection string
    is reachable, or enforcing business logic rules).
    """

    @abstractmethod
    def should_validate(self, filename: str, file_ext: str) -> bool:
        """Return True if this validator should run for the given file."""
        ...

    @abstractmethod
    def validate(self, filename: str, data: Any) -> List[str]:
        """
        Validate the parsed file data.

        Args:
            filename: The relative path of the uploaded file.
            data: The parsed content (dict for JSON/YAML, DataFrame for CSV, str for others).

        Returns:
            A list of error messages.  Return an empty list if validation passes.
        """
        ...
