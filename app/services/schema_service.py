"""
Schema validation service for master configuration files.

Supports:
- JSON Schema validation for .json / .yaml / .yml files
- CSV validation via pandas + pandera
- Filename-to-schema auto-mapping via mapping.json
- CRUD operations for schema management
- Custom validator plugin execution
"""

import importlib
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


class SchemaValidationException(Exception):
    pass


class SchemaService:
    """Loads, manages, and applies JSON/CSV schemas for uploaded files."""

    def __init__(self, schemas_dir: str = "data/schemas", mapping_file: str = "data/schemas/mapping.json"):
        self.schemas_dir = Path(schemas_dir).resolve()
        self.schemas_dir.mkdir(parents=True, exist_ok=True)
        self.mapping_file = Path(mapping_file).resolve()

        self.schemas: Dict[str, Any] = {}
        self.filename_mapping: Dict[str, str] = {}  # regex pattern -> schema name
        self.load_schemas()
        self.load_mapping()

    # ── loading ──────────────────────────────────────────────────

    def load_schemas(self):
        """Load all .json schema files from the schemas directory (excluding mapping.json)."""
        self.schemas.clear()
        for schema_file in self.schemas_dir.glob("*.json"):
            if schema_file.name == "mapping.json":
                continue
            try:
                with open(schema_file, "r") as f:
                    self.schemas[schema_file.stem] = json.load(f)
            except Exception as e:
                logger.error("Error loading schema %s: %s", schema_file, e)

    def load_mapping(self):
        """Load filename-to-schema regex mapping from mapping.json."""
        self.filename_mapping.clear()
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, "r") as f:
                    self.filename_mapping = json.load(f)
            except Exception as e:
                logger.error("Error loading schema mapping: %s", e)

    def _save_mapping(self):
        """Persist the current mapping to disk."""
        with open(self.mapping_file, "w") as f:
            json.dump(self.filename_mapping, f, indent=2)

    # ── schema CRUD ──────────────────────────────────────────────

    def get_available_schemas(self) -> List[str]:
        return sorted(self.schemas.keys())

    def get_schema(self, name: str) -> Optional[Dict]:
        return self.schemas.get(name)

    def create_or_update_schema(self, name: str, schema_data: Dict):
        """Save a schema to disk and reload."""
        path = self.schemas_dir / f"{name}.json"
        with open(path, "w") as f:
            json.dump(schema_data, f, indent=2)
        self.schemas[name] = schema_data
        logger.info("Schema '%s' saved", name)

    def delete_schema(self, name: str) -> bool:
        """Delete a schema file from disk."""
        path = self.schemas_dir / f"{name}.json"
        if path.exists():
            path.unlink()
            self.schemas.pop(name, None)
            logger.info("Schema '%s' deleted", name)
            return True
        return False

    # ── mapping CRUD ─────────────────────────────────────────────

    def get_mapping(self) -> Dict[str, str]:
        return dict(self.filename_mapping)

    def set_mapping(self, mapping: Dict[str, str]):
        self.filename_mapping = mapping
        self._save_mapping()

    # ── auto-resolution ──────────────────────────────────────────

    def resolve_schema_name(self, filename: str) -> Optional[str]:
        """
        Given a filename (e.g. "app_settings.json"), try to match it
        against the regex patterns in mapping.json and return the
        corresponding schema name.  Returns None if no match.
        """
        for pattern, schema_name in self.filename_mapping.items():
            if re.search(pattern, filename):
                if schema_name in self.schemas:
                    return schema_name
        return None

    # ── validation ───────────────────────────────────────────────

    def validate_content(
        self,
        content_str: str,
        filename: str,
        file_ext: str,
        schema_name: Optional[str] = None,
    ) -> dict:
        """
        Validate file content.  Returns a result dict:
        {"valid": True, "schema_used": "...", "method": "..."}

        Raises SchemaValidationException on failure.

        Resolution order:
        1. Explicit schema_name if provided
        2. Auto-resolved from filename mapping
        3. Syntax-only check (no schema)
        """
        resolved_schema = schema_name
        method = "explicit"

        if not resolved_schema:
            resolved_schema = self.resolve_schema_name(filename)
            method = "auto-mapped" if resolved_schema else "none"

        # CSV files — use pandera
        if file_ext.lower() == ".csv":
            return self._validate_csv(content_str, resolved_schema, method)

        # JSON / YAML files — use jsonschema
        data = self._parse_structured(content_str, file_ext)

        if resolved_schema and resolved_schema in self.schemas:
            schema = self.schemas[resolved_schema]
            try:
                jsonschema.validate(instance=data, schema=schema)
            except jsonschema.exceptions.ValidationError as e:
                raise SchemaValidationException(f"Schema validation failed: {e.message}")
            return {"valid": True, "schema_used": resolved_schema, "method": method}

        # No schema — syntax was already validated by _parse_structured
        return {"valid": True, "schema_used": None, "method": method}

    def _parse_structured(self, content_str: str, file_ext: str) -> Any:
        """Parse JSON or YAML content.  Raises SchemaValidationException on syntax errors."""
        try:
            if file_ext.lower() == ".json":
                return json.loads(content_str)
            elif file_ext.lower() in (".yaml", ".yml"):
                return yaml.safe_load(content_str)
            else:
                # Unrecognised structured format — return raw string
                return content_str
        except Exception as e:
            raise SchemaValidationException(f"Invalid file format: {e}")

    def _validate_csv(self, content_str: str, schema_name: Optional[str], method: str) -> dict:
        """Validate a CSV file using pandas for parsing and pandera for schema checks."""
        import pandera as pa
        try:
            df = pd.read_csv(io.StringIO(content_str))
        except Exception as e:
            raise SchemaValidationException(f"Invalid CSV format: {e}")

        if not schema_name or schema_name not in self.schemas:
            return {"valid": True, "schema_used": None, "method": method}

        schema_def = self.schemas[schema_name]
        
        pa_cols = {}
        if "columns" in schema_def:
            for col_name, rules in schema_def["columns"].items():
                dtype_str = rules.get("dtype", "str")
                nullable = rules.get("nullable", True)
                
                if dtype_str == "int":
                    pa_type = pa.Int
                elif dtype_str == "float":
                    pa_type = pa.Float
                elif dtype_str == "bool":
                    pa_type = pa.Bool
                else:
                    pa_type = pa.String
                
                pa_cols[col_name] = pa.Column(pa_type, nullable=nullable)

        pa_schema = pa.DataFrameSchema(pa_cols)

        try:
            pa_schema.validate(df)
        except (pa.errors.SchemaError, pa.errors.SchemaErrors) as e:
            raise SchemaValidationException(f"CSV validation failed: {e}")

        return {"valid": True, "schema_used": schema_name, "method": method}
