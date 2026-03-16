"""JSON Schema validation for tool calls.

This module provides schema loading and validation functionality
for validating tool call arguments against JSON Schema definitions.
"""

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jsonschema import Draft7Validator, ValidationError, SchemaError

logger = logging.getLogger(__name__)


# Canonical definitions in contracts/types/errors.py; re-exported for backward compat.
from agent_host.contracts.types.errors import (  # noqa: F401
    SchemaValidatorError,
    SchemaLoadError,
    SchemaNotFoundError,
    ValidationFailedError,
)


class SchemaValidator:
    """Validates tool call arguments against JSON Schemas.
    
    This class loads JSON Schema files from a directory and provides
    methods to validate tool call arguments against the appropriate schema.
    It also provides functionality to format schemas for use with Gemini's
    function calling feature.
    
    Attributes:
        schemas_dir: Path to the directory containing JSON Schema files.
        schemas: Dictionary mapping tool names to their schemas.
    
    Example:
        >>> validator = SchemaValidator(Path("schemas"))
        >>> is_valid = validator.validate_tool_call("search_files", {"query": "python"})
        >>> print(is_valid)
        True
    """
    
    def __init__(self, schemas_dir: Path) -> None:
        """Initialize the schema validator.
        
        Args:
            schemas_dir: Path to directory containing JSON Schema files.
        
        Raises:
            SchemaLoadError: If the directory doesn't exist or is not a directory.
        """
        self.schemas_dir = Path(schemas_dir)
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self._validators: Dict[str, Draft7Validator] = {}
        
        self._load_schemas()
    
    def _load_schemas(self) -> None:
        """Load all JSON schemas from the schemas directory.
        
        Reads all .json files from the schemas directory and stores them
        in the schemas dictionary, indexed by the schema's $id or filename.
        
        Raises:
            SchemaLoadError: If the directory doesn't exist or a schema is invalid.
        """
        if not self.schemas_dir.exists():
            raise SchemaLoadError(f"Schemas directory does not exist: {self.schemas_dir}")
        
        if not self.schemas_dir.is_dir():
            raise SchemaLoadError(f"Schemas path is not a directory: {self.schemas_dir}")
        
        schema_files = list(self.schemas_dir.glob("*.json"))
        
        if not schema_files:
            logger.warning(f"No schema files found in {self.schemas_dir}")
            return
        
        for schema_file in schema_files:
            try:
                self._load_schema_file(schema_file)
            except Exception as e:
                raise SchemaLoadError(
                    f"Failed to load schema {schema_file.name}: {e}"
                ) from e
        
        logger.info(f"Loaded {len(self.schemas)} schemas from {self.schemas_dir}")
    
    def _load_schema_file(self, schema_file: Path) -> None:
        """Load a single schema file.
        
        Args:
            schema_file: Path to the JSON Schema file.
        
        Raises:
            json.JSONDecodeError: If the file is not valid JSON.
            SchemaError: If the schema is not valid JSON Schema.
        """
        with open(schema_file, "r", encoding="utf-8") as f:
            schema = json.load(f)
        
        # Get schema identifier (prefer $id, fall back to filename)
        schema_id = schema.get("$id", schema_file.stem)
        
        # Validate that the schema is valid JSON Schema
        try:
            Draft7Validator.check_schema(schema)
        except SchemaError as e:
            raise SchemaLoadError(
                f"Invalid JSON Schema in {schema_file.name}: {e.message}"
            )
        
        # Store schema and pre-compile validator
        self.schemas[schema_id] = schema
        self._validators[schema_id] = Draft7Validator(schema)
        
        logger.debug(f"Loaded schema: {schema_id}")
    
    def validate_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> bool:
        """Validate tool call arguments against the tool's schema.
        
        Args:
            tool_name: Name of the tool (must match a loaded schema $id).
            arguments: Dictionary of arguments to validate.
        
        Returns:
            True if validation passes.
        
        Raises:
            SchemaNotFoundError: If no schema exists for the tool.
            ValidationFailedError: If validation fails.
        
        Example:
            >>> validator.validate_tool_call("search_files", {"query": "python"})
            True
            >>> validator.validate_tool_call("search_files", {})  # missing required
            ValidationFailedError: Validation failed: 'query' is a required property
        """
        if tool_name not in self._validators:
            raise SchemaNotFoundError(f"No schema found for tool: {tool_name}")
        
        validator = self._validators[tool_name]
        errors = list(validator.iter_errors(arguments))
        
        if errors:
            error_messages = [self._format_validation_error(e) for e in errors]
            raise ValidationFailedError(
                f"Validation failed for '{tool_name}': {error_messages[0]}",
                errors=error_messages,
            )
        
        logger.debug(f"Validation passed for tool: {tool_name}")
        return True
    
    def validate_tool_call_safe(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Tuple[bool, Optional[List[str]]]:
        """Validate tool call arguments without raising exceptions.
        
        Args:
            tool_name: Name of the tool.
            arguments: Dictionary of arguments to validate.
        
        Returns:
            Tuple of (is_valid, error_messages).
            If valid, returns (True, None).
            If invalid, returns (False, list of error messages).
        
        Example:
            >>> is_valid, errors = validator.validate_tool_call_safe("search_files", {})
            >>> print(is_valid, errors)
            False ["'query' is a required property"]
        """
        try:
            self.validate_tool_call(tool_name, arguments)
            return True, None
        except SchemaNotFoundError as e:
            return False, [str(e)]
        except ValidationFailedError as e:
            return False, e.errors
    
    def _format_validation_error(self, error: ValidationError) -> str:
        """Format a validation error into a human-readable message.
        
        Args:
            error: The jsonschema ValidationError.
        
        Returns:
            Formatted error message string.
        """
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
        return f"{error.message} (at {path})"
    
    def get_schema(self, tool_name: str) -> Dict[str, Any]:
        """Get the schema for a specific tool.
        
        Args:
            tool_name: Name of the tool to get schema for.
        
        Returns:
            The JSON Schema dictionary for the tool.
        
        Raises:
            SchemaNotFoundError: If no schema exists for the tool.
        """
        if tool_name not in self.schemas:
            raise SchemaNotFoundError(f"No schema found for tool: {tool_name}")
        return self.schemas[tool_name]
    
    def get_all_tool_names(self) -> List[str]:
        """Get the names of all loaded tools.
        
        Returns:
            List of tool names with loaded schemas.
        """
        return list(self.schemas.keys())
    
    def get_all_tools_for_gemini(self) -> List[Dict[str, Any]]:
        """Format all schemas for Gemini's function calling configuration.
        
        Converts the loaded JSON Schemas into the format expected by
        Gemini's function calling feature. Each schema is converted to
        a function declaration with name, description, and parameters.
        
        Returns:
            List of tool definitions formatted for Gemini.
        
        Example:
            >>> tools = validator.get_all_tools_for_gemini()
            >>> print(tools[0].keys())
            dict_keys(['name', 'description', 'parameters'])
        """
        gemini_tools = []
        
        for tool_name, schema in self.schemas.items():
            tool_def = {
                # Use schema id/key as the canonical function name to keep
                # Gemini function calls aligned with validator lookup keys.
                "name": tool_name,
                "description": schema.get("description", f"Tool: {tool_name}"),
                "parameters": self._schema_to_gemini_parameters(schema),
            }
            gemini_tools.append(tool_def)
        
        return gemini_tools
    
    def _schema_to_gemini_parameters(
        self,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert a JSON Schema to Gemini parameter format.
        
        Args:
            schema: The JSON Schema to convert.
        
        Returns:
            Parameters object in Gemini format.
        """
        # Extract only the parameter-level schema for Gemini function declarations.
        # Top-level metadata (name, description, title) is already passed at the
        # FunctionDeclaration level and must not leak into parameters_json_schema.
        parameters: Dict[str, Any] = deepcopy(schema)
        for key in ("$schema", "$id", "name", "title", "description"):
            parameters.pop(key, None)
        parameters.setdefault("type", "object")

        return parameters
    
    def reload_schemas(self) -> None:
        """Reload all schemas from the directory.
        
        This clears the current schemas and reloads from disk.
        Useful if schemas have been modified.
        """
        self.schemas.clear()
        self._validators.clear()
        self._load_schemas()
        logger.info("Schemas reloaded")
