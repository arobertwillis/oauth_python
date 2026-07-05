"""
Auto-discovery of custom validators.

All concrete subclasses of BaseValidator found in this package
are automatically collected and made available for the upload pipeline.
"""

import importlib
import inspect
import logging
import pkgutil
from typing import List

from app.validators.base_validator import BaseValidator

logger = logging.getLogger(__name__)

_validators: List[BaseValidator] | None = None


def get_validators() -> List[BaseValidator]:
    """
    Discover and instantiate all BaseValidator subclasses in this package.
    Results are cached after the first call.
    """
    global _validators
    if _validators is not None:
        return _validators

    _validators = []
    package_path = __path__  # type: ignore[name-defined]
    for _importer, modname, _ispkg in pkgutil.iter_modules(package_path):
        if modname == "base_validator":
            continue
        try:
            module = importlib.import_module(f"app.validators.{modname}")
            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseValidator) and obj is not BaseValidator:
                    _validators.append(obj())
                    logger.info("Registered custom validator: %s", obj.__name__)
        except Exception as e:
            logger.error("Failed to load validator module %s: %s", modname, e)

    return _validators
