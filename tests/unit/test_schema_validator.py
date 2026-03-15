"""Unit tests for SchemaValidator.

Tests schema loading, tool call validation, and Gemini format conversion.
"""

import json
import pytest
from pathlib import Path

from agent_host.schema_validator import (
    SchemaValidator,
    SchemaLoadError,
    SchemaNotFoundError,
    ValidationFailedError,
)


class TestSchemaLoading:
    """Tests for schema loading functionality."""
    
    def test_load_schemas_from_directory(self, schemas_dir: Path) -> None:
        """Test that schemas are loaded from the directory."""
        validator = SchemaValidator(schemas_dir)
        
        assert len(validator.schemas) > 0
        assert len(validator.get_all_tool_names()) == len(validator.schemas)
    
    def test_load_all_core_schemas(self, schemas_dir: Path) -> None:
        """Test that all expected core tool schemas are loaded."""
        validator = SchemaValidator(schemas_dir)
        
        expected_tools = [
            "search_files",
            "read_document",
            "plan_ops",
            "planner",
            "apply_ops",
            "open_item",
            "run_automation",
            "create_directory",
        ]
        
        loaded_tools = validator.get_all_tool_names()
        
        for tool in expected_tools:
            assert tool in loaded_tools, f"Missing schema for tool: {tool}"
    
    def test_nonexistent_directory_raises_error(self, tmp_path: Path) -> None:
        """Test that loading from nonexistent directory raises error."""
        nonexistent = tmp_path / "does_not_exist"
        
        with pytest.raises(SchemaLoadError) as exc_info:
            SchemaValidator(nonexistent)
        
        assert "does not exist" in str(exc_info.value)
    
    def test_directory_is_file_raises_error(self, tmp_path: Path) -> None:
        """Test that a file path raises error."""
        file_path = tmp_path / "not_a_directory.json"
        file_path.write_text("{}")
        
        with pytest.raises(SchemaLoadError) as exc_info:
            SchemaValidator(file_path)
        
        assert "not a directory" in str(exc_info.value)
    
    def test_empty_directory_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Test that empty directory logs warning but doesn't raise."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        
        validator = SchemaValidator(empty_dir)
        
        assert len(validator.schemas) == 0
        assert "No schema files found" in caplog.text
    
    def test_invalid_json_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid JSON file raises error."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()
        
        invalid_file = schema_dir / "invalid.json"
        invalid_file.write_text("{ not valid json }")
        
        with pytest.raises(SchemaLoadError) as exc_info:
            SchemaValidator(schema_dir)
        
        assert "Failed to load schema" in str(exc_info.value)
    
    def test_invalid_schema_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid JSON Schema raises error."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()
        
        # Valid JSON but invalid schema (type must be a string, not integer)
        invalid_schema = schema_dir / "invalid_schema.json"
        invalid_schema.write_text(json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": 123  # Invalid - type must be a string
        }))
        
        with pytest.raises(SchemaLoadError) as exc_info:
            SchemaValidator(schema_dir)
        
        assert "Invalid JSON Schema" in str(exc_info.value)
    
    def test_reload_schemas(self, tmp_path: Path) -> None:
        """Test that schemas can be reloaded."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()
        
        # Create initial schema
        schema_file = schema_dir / "test_tool.json"
        schema_file.write_text(json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "test_tool",
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }))
        
        validator = SchemaValidator(schema_dir)
        assert "test_tool" in validator.schemas
        
        # Add another schema
        new_schema = schema_dir / "another_tool.json"
        new_schema.write_text(json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "another_tool",
            "type": "object",
            "properties": {"value": {"type": "integer"}}
        }))
        
        validator.reload_schemas()
        
        assert "test_tool" in validator.schemas
        assert "another_tool" in validator.schemas


class TestToolCallValidation:
    """Tests for tool call validation."""
    
    def test_validate_search_files_valid(self, schemas_dir: Path) -> None:
        """Test validating a valid search_files call."""
        validator = SchemaValidator(schemas_dir)
        
        result = validator.validate_tool_call("search_files", {
            "query": "Python files"
        })
        
        assert result is True
    
    def test_validate_search_files_with_optional(self, schemas_dir: Path) -> None:
        """Test search_files with optional parameters."""
        validator = SchemaValidator(schemas_dir)
        
        result = validator.validate_tool_call("search_files", {
            "query": "Python files",
            "path_filter": "Documents",
            "limit": 50,
            "mode": "auto",
            "time_budget_ms": 900,
            "include_hidden": False,
            "max_depth": 6,
            "continuation_token": "opaque-token",
        })
        
        assert result is True
    
    def test_validate_search_files_missing_required(self, schemas_dir: Path) -> None:
        """Test search_files missing required query parameter."""
        validator = SchemaValidator(schemas_dir)
        
        with pytest.raises(ValidationFailedError) as exc_info:
            validator.validate_tool_call("search_files", {})
        
        assert "'query' is a required property" in str(exc_info.value)
        assert len(exc_info.value.errors) > 0
    

    
    def test_validate_plan_ops_valid(self, schemas_dir: Path) -> None:
        """Test validating a valid plan_ops call."""
        validator = SchemaValidator(schemas_dir)
        
        result = validator.validate_tool_call("plan_ops", {
            "ops": [
                {
                    "op": "move",
                    "src": "/a/b.txt",
                    "dest": "/c/d.txt",
                    "overwrite_policy": "rename",
                }
            ]
        })
        
        assert result is True
    
    def test_validate_apply_ops_valid(self, schemas_dir: Path) -> None:
        """Test validating a valid apply_ops call."""
        validator = SchemaValidator(schemas_dir)
        
        result = validator.validate_tool_call("apply_ops", {
            "plan_id": "plan-12345",
            "dry_run": True,
            "stop_on_error": True,
            "verify_after": False,
            "idempotency_key": "request-abc",
        })
        
        assert result is True
    
    def test_validate_open_item_valid(self, schemas_dir: Path) -> None:
        """Test validating a valid open_item call."""
        validator = SchemaValidator(schemas_dir)
        
        result = validator.validate_tool_call("open_item", {
            "path": "/Users/test/document.pdf"
        })
        
        assert result is True
    
    def test_validate_run_automation_valid(self, schemas_dir: Path) -> None:
        """Test validating a valid run_automation call."""
        validator = SchemaValidator(schemas_dir)
        
        result = validator.validate_tool_call("run_automation", {
            "name": "My Shortcut"
        })
        
        assert result is True
    
    def test_validate_unknown_tool_raises_error(self, schemas_dir: Path) -> None:
        """Test that unknown tool raises SchemaNotFoundError."""
        validator = SchemaValidator(schemas_dir)
        
        with pytest.raises(SchemaNotFoundError) as exc_info:
            validator.validate_tool_call("nonexistent_tool", {"arg": "value"})
        
        assert "No schema found for tool" in str(exc_info.value)
    
    def test_validate_wrong_argument_type(self, schemas_dir: Path) -> None:
        """Test validation fails for wrong argument type."""
        validator = SchemaValidator(schemas_dir)
        
        with pytest.raises(ValidationFailedError) as exc_info:
            validator.validate_tool_call("search_files", {
                "query": 12345  # Should be string
            })
        
        assert "not of type 'string'" in str(exc_info.value)


class TestSafeValidation:
    """Tests for validate_tool_call_safe method."""
    
    def test_valid_returns_true_none(self, schemas_dir: Path) -> None:
        """Test that valid call returns (True, None)."""
        validator = SchemaValidator(schemas_dir)
        
        is_valid, errors = validator.validate_tool_call_safe("search_files", {
            "query": "test"
        })
        
        assert is_valid is True
        assert errors is None
    
    def test_invalid_returns_false_errors(self, schemas_dir: Path) -> None:
        """Test that invalid call returns (False, errors)."""
        validator = SchemaValidator(schemas_dir)
        
        is_valid, errors = validator.validate_tool_call_safe("search_files", {})
        
        assert is_valid is False
        assert errors is not None
        assert len(errors) > 0
        assert "'query' is a required property" in errors[0]
    
    def test_unknown_tool_returns_false(self, schemas_dir: Path) -> None:
        """Test that unknown tool returns (False, errors)."""
        validator = SchemaValidator(schemas_dir)
        
        is_valid, errors = validator.validate_tool_call_safe("unknown_tool", {})
        
        assert is_valid is False
        assert errors is not None
        assert "No schema found" in errors[0]


class TestGetSchema:
    """Tests for get_schema method."""
    
    def test_get_existing_schema(self, schemas_dir: Path) -> None:
        """Test retrieving an existing schema."""
        validator = SchemaValidator(schemas_dir)
        
        schema = validator.get_schema("search_files")
        
        assert "$id" in schema or "title" in schema
        assert "properties" in schema
        assert "query" in schema["properties"]
    
    def test_get_nonexistent_schema_raises_error(self, schemas_dir: Path) -> None:
        """Test that getting nonexistent schema raises error."""
        validator = SchemaValidator(schemas_dir)
        
        with pytest.raises(SchemaNotFoundError):
            validator.get_schema("nonexistent")


class TestGeminiFormat:
    """Tests for get_all_tools_for_gemini format."""
    
    def test_gemini_format_structure(self, schemas_dir: Path) -> None:
        """Test that Gemini format has correct structure."""
        validator = SchemaValidator(schemas_dir)
        
        tools = validator.get_all_tools_for_gemini()
        
        assert len(tools) > 0
        
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)
            assert isinstance(tool["parameters"], dict)
    
    def test_gemini_format_parameters(self, schemas_dir: Path) -> None:
        """Test that parameters are properly formatted for Gemini."""
        validator = SchemaValidator(schemas_dir)
        
        tools = validator.get_all_tools_for_gemini()
        
        # Find search_files tool
        search_tool = next((t for t in tools if t["name"] == "search_files"), None)
        
        assert search_tool is not None
        params = search_tool["parameters"]
        
        assert "type" in params
        assert params["type"] == "object"
        assert "properties" in params
        assert "query" in params["properties"]

    def test_gemini_retains_additional_properties_for_strict_tools(
        self,
        schemas_dir: Path,
    ) -> None:
        """Strict schemas should keep additionalProperties=false in Gemini params."""
        validator = SchemaValidator(schemas_dir)
        tools = {tool["name"]: tool for tool in validator.get_all_tools_for_gemini()}

        assert tools["search_files"]["parameters"]["additionalProperties"] is False
        assert tools["apply_ops"]["parameters"]["additionalProperties"] is False

    def test_gemini_retains_nested_enum_objects_when_representable(
        self,
        tmp_path: Path,
    ) -> None:
        """Nested enum constraints under additionalProperties should be preserved."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        schema_file = schema_dir / "nested_enum_tool.json"
        schema_file.write_text(json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "nested_enum_tool",
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["strict", "relaxed"],
                            }
                        },
                        "required": ["mode"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["filters"],
            "additionalProperties": False,
        }))

        validator = SchemaValidator(schema_dir)
        tools = validator.get_all_tools_for_gemini()

        assert len(tools) == 1
        params = tools[0]["parameters"]
        nested_schema = params["properties"]["filters"]["additionalProperties"]

        assert params["additionalProperties"] is False
        assert nested_schema["additionalProperties"] is False
        assert nested_schema["properties"]["mode"]["enum"] == ["strict", "relaxed"]
    
    def test_gemini_format_all_tools(self, schemas_dir: Path) -> None:
        """Test that all expected core tools are in Gemini format."""
        validator = SchemaValidator(schemas_dir)
        
        tools = validator.get_all_tools_for_gemini()
        tool_names = [t["name"] for t in tools]
        
        expected_tools = [
            "search_files",
            "read_document",
            "plan_ops",
            "planner",
            "apply_ops",
            "open_item",
            "run_automation",
            "create_directory",
        ]
        
        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool in Gemini format: {expected}"
    
    def test_gemini_format_descriptions_present(self, schemas_dir: Path) -> None:
        """Test that all tools have non-empty descriptions."""
        validator = SchemaValidator(schemas_dir)
        
        tools = validator.get_all_tools_for_gemini()
        
        for tool in tools:
            assert tool["description"], f"Tool {tool['name']} has empty description"
            assert len(tool["description"]) > 10, f"Tool {tool['name']} has too short description"


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    def test_schema_without_id_uses_filename(self, tmp_path: Path) -> None:
        """Test that schema without $id uses filename as identifier."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()
        
        # Schema without $id
        schema_file = schema_dir / "my_custom_tool.json"
        schema_file.write_text(json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "My Custom Tool",
            "type": "object",
            "properties": {"value": {"type": "string"}}
        }))
        
        validator = SchemaValidator(schema_dir)
        
        # Should use filename stem as identifier
        assert "my_custom_tool" in validator.schemas

    def test_gemini_name_uses_schema_id_not_title(self, tmp_path: Path) -> None:
        """Gemini function name should always use canonical schema id."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        schema_file = schema_dir / "canonical_tool.json"
        schema_file.write_text(json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "canonical_tool",
            "title": "Friendly Display Name",
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }))

        validator = SchemaValidator(schema_dir)
        tools = validator.get_all_tools_for_gemini()

        assert len(tools) == 1
        assert tools[0]["name"] == "canonical_tool"
    
    def test_multiple_validation_errors(self, schemas_dir: Path) -> None:
        """Test that multiple validation errors are captured."""
        validator = SchemaValidator(schemas_dir)
        
        # Missing required and wrong type in same call
        is_valid, errors = validator.validate_tool_call_safe("search_files", {
            # paths is missing and we have invalid extra field
        })
        
        assert is_valid is False
        assert errors is not None
    
    def test_extra_properties_rejected(self, schemas_dir: Path) -> None:
        """Test that unknown properties are rejected for strict tool schemas."""
        validator = SchemaValidator(schemas_dir)

        with pytest.raises(ValidationFailedError) as exc_info:
            validator.validate_tool_call("search_files", {
                "query": "test",
                "extra_field": "should be rejected"
            })

        assert "Additional properties are not allowed" in str(exc_info.value)
