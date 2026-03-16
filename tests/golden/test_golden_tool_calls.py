"""Golden tests for tool call parsing.

Tests known prompt -> tool call mappings using fixture files.
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock

from agent_host.tool_parser import ToolCallParser, ToolCall
from agent_host.schema_validator import SchemaValidator


def load_fixture(fixture_path: Path) -> Dict[str, Any]:
    """Load a golden test fixture from JSON file.
    
    Args:
        fixture_path: Path to the fixture JSON file.
    
    Returns:
        Dictionary containing fixture data.
    """
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_fixture_files(fixtures_dir: Path) -> List[Path]:
    """Get all fixture files from the fixtures directory.
    
    Args:
        fixtures_dir: Path to the fixtures directory.
    
    Returns:
        List of paths to fixture JSON files.
    """
    return sorted(fixtures_dir.glob("*.json"))


def create_mock_raw_response(fixture: Dict[str, Any]) -> Mock:
    """Create a mock raw Gemini response from fixture data.
    
    Args:
        fixture: Fixture data containing mock_gemini_response.
    
    Returns:
        Mock object mimicking Gemini SDK response structure.
    """
    mock_response = fixture["mock_gemini_response"]
    candidates_data = mock_response.get("candidates", [])
    
    if not candidates_data:
        mock = Mock()
        mock.candidates = []
        return mock
    
    candidate_data = candidates_data[0]
    content_data = candidate_data.get("content", {})
    parts_data = content_data.get("parts", [])
    
    mock_parts = []
    for part in parts_data:
        mock_part = Mock()
        
        if "functionCall" in part:
            fc_data = part["functionCall"]
            mock_fc = Mock()
            mock_fc.name = fc_data.get("name", "")
            mock_fc.args = fc_data.get("args", {})
            mock_part.function_call = mock_fc
        else:
            mock_part.function_call = None
        
        if "text" in part:
            mock_part.text = part["text"]
        else:
            mock_part.text = None
        
        mock_parts.append(mock_part)
    
    mock_content = Mock()
    mock_content.parts = mock_parts
    
    mock_candidate = Mock()
    mock_candidate.content = mock_content
    
    mock_response_obj = Mock()
    mock_response_obj.candidates = [mock_candidate]
    
    return mock_response_obj


def create_dict_response(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """Create a dictionary response (GeminiClient format) from fixture.
    
    Args:
        fixture: Fixture data containing expected_tool_call.
    
    Returns:
        Dictionary in GeminiClient processed response format.
    """
    expected = fixture["expected_tool_call"]
    return {
        "function_call": {
            "name": expected["name"],
            "args": expected["arguments"],
        },
        "text": None,
    }


class TestGoldenToolCalls:
    """Golden tests for tool call parsing from fixtures."""
    
    @pytest.fixture
    def parser(self) -> ToolCallParser:
        """Create a ToolCallParser instance."""
        return ToolCallParser()
    
    @pytest.fixture
    def validator(self, schemas_dir: Path) -> SchemaValidator:
        """Create a SchemaValidator instance."""
        return SchemaValidator(schemas_dir)
    
    def test_fixture_files_exist(self, fixtures_dir: Path) -> None:
        """Verify fixture files exist."""
        fixture_files = get_fixture_files(fixtures_dir)
        
        # Filter out non-fixture files like .gitkeep
        json_fixtures = [f for f in fixture_files if f.suffix == ".json"]
        
        assert len(json_fixtures) > 0, "No fixture files found"
    
    @pytest.mark.parametrize("fixture_name", [
        "search_files_001.json",
        "get_metadata_001.json",
        "open_item_001.json",
    ])
    def test_parse_fixture_dict_response(
        self,
        fixtures_dir: Path,
        parser: ToolCallParser,
        fixture_name: str,
    ) -> None:
        """Test parsing dict responses from fixtures."""
        fixture_path = fixtures_dir / fixture_name
        
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture_name} not found")
        
        fixture = load_fixture(fixture_path)
        dict_response = create_dict_response(fixture)
        
        result = parser.parse_response(dict_response)
        
        assert result is not None
        assert result.name == fixture["expected_tool_call"]["name"]
        assert result.arguments == fixture["expected_tool_call"]["arguments"]
    
    @pytest.mark.parametrize("fixture_name", [
        "search_files_001.json",
        "get_metadata_001.json",
        "open_item_001.json",
    ])
    def test_parse_fixture_raw_response(
        self,
        fixtures_dir: Path,
        parser: ToolCallParser,
        fixture_name: str,
    ) -> None:
        """Test parsing raw responses from fixtures."""
        fixture_path = fixtures_dir / fixture_name
        
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture_name} not found")
        
        fixture = load_fixture(fixture_path)
        mock_response = create_mock_raw_response(fixture)
        
        result = parser.parse_response(mock_response)
        
        assert result is not None
        assert result.name == fixture["expected_tool_call"]["name"]
        assert result.arguments == fixture["expected_tool_call"]["arguments"]
    
    @pytest.mark.parametrize("fixture_name", [
        "search_files_001.json",
        "get_metadata_001.json",
        "open_item_001.json",
    ])
    def test_validate_fixture_tool_calls(
        self,
        fixtures_dir: Path,
        schemas_dir: Path,
        validator: SchemaValidator,
        fixture_name: str,
    ) -> None:
        """Test that fixture tool calls pass schema validation."""
        fixture_path = fixtures_dir / fixture_name
        
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture_name} not found")
        
        fixture = load_fixture(fixture_path)
        expected = fixture["expected_tool_call"]
        
        # Should not raise
        result = validator.validate_tool_call(
            expected["name"],
            expected["arguments"],
        )
        
        assert result is True


class TestGoldenFixtureFormat:
    """Tests to validate fixture file format."""
    
    def test_all_fixtures_have_required_fields(self, fixtures_dir: Path) -> None:
        """Test that all fixtures have required fields."""
        required_fields = {
            "test_id",
            "description",
            "mock_gemini_response",
            "expected_tool_call",
        }
        
        fixture_files = get_fixture_files(fixtures_dir)
        
        for fixture_path in fixture_files:
            if fixture_path.suffix != ".json":
                continue
            
            fixture = load_fixture(fixture_path)
            
            for field in required_fields:
                assert field in fixture, \
                    f"Fixture {fixture_path.name} missing field: {field}"
    
    def test_all_fixtures_have_valid_expected_tool_call(
        self,
        fixtures_dir: Path,
    ) -> None:
        """Test that all fixtures have valid expected_tool_call format."""
        fixture_files = get_fixture_files(fixtures_dir)
        
        for fixture_path in fixture_files:
            if fixture_path.suffix != ".json":
                continue
            
            fixture = load_fixture(fixture_path)
            expected = fixture.get("expected_tool_call", {})
            
            assert "name" in expected, \
                f"Fixture {fixture_path.name} missing expected_tool_call.name"
            assert "arguments" in expected, \
                f"Fixture {fixture_path.name} missing expected_tool_call.arguments"
            assert isinstance(expected["arguments"], dict), \
                f"Fixture {fixture_path.name} arguments must be a dict"


class TestGoldenEndToEnd:
    """End-to-end tests using fixtures."""
    
    def test_complete_flow_search_files(
        self,
        fixtures_dir: Path,
        schemas_dir: Path,
    ) -> None:
        """Test complete flow: parse response -> validate -> extract tool call."""
        fixture_path = fixtures_dir / "search_files_001.json"
        
        if not fixture_path.exists():
            pytest.skip("search_files_001.json fixture not found")
        
        fixture = load_fixture(fixture_path)
        
        # Step 1: Parse response
        parser = ToolCallParser()
        dict_response = create_dict_response(fixture)
        tool_call = parser.parse_response(dict_response)
        
        assert tool_call is not None
        
        # Step 2: Validate tool call
        validator = SchemaValidator(schemas_dir)
        is_valid = validator.validate_tool_call(
            tool_call.name,
            tool_call.arguments,
        )
        
        assert is_valid is True
        
        # Step 3: Verify matches expected
        assert tool_call.name == fixture["expected_tool_call"]["name"]
        assert tool_call.arguments == fixture["expected_tool_call"]["arguments"]
        
        # Step 4: Verify to_dict output
        tool_dict = tool_call.to_dict()
        assert tool_dict["name"] == "search_files"
        assert "query" in tool_dict["arguments"]
    
    def test_complete_flow_all_fixtures(
        self,
        fixtures_dir: Path,
        schemas_dir: Path,
    ) -> None:
        """Test complete flow for all available fixtures."""
        fixture_files = get_fixture_files(fixtures_dir)
        parser = ToolCallParser()
        validator = SchemaValidator(schemas_dir)
        
        processed = 0
        
        for fixture_path in fixture_files:
            if fixture_path.suffix != ".json":
                continue
            
            fixture = load_fixture(fixture_path)
            dict_response = create_dict_response(fixture)
            
            # Parse
            tool_call = parser.parse_response(dict_response)
            assert tool_call is not None, \
                f"Failed to parse {fixture_path.name}"
            
            # Validate
            is_valid, errors = validator.validate_tool_call_safe(
                tool_call.name,
                tool_call.arguments,
            )
            assert is_valid, \
                f"Validation failed for {fixture_path.name}: {errors}"
            
            # Verify
            assert tool_call.name == fixture["expected_tool_call"]["name"]
            assert tool_call.arguments == fixture["expected_tool_call"]["arguments"]
            
            processed += 1
        
        assert processed > 0, "No fixtures were processed"


class TestGoldenToolCallRoundtrip:
    """Tests for ToolCall serialization roundtrip."""
    
    @pytest.mark.parametrize("fixture_name", [
        "search_files_001.json",
        "get_metadata_001.json",
        "open_item_001.json",
    ])
    def test_to_dict_roundtrip(
        self,
        fixtures_dir: Path,
        fixture_name: str,
    ) -> None:
        """Test that ToolCall.to_dict() produces valid data."""
        fixture_path = fixtures_dir / fixture_name
        
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture_name} not found")
        
        fixture = load_fixture(fixture_path)
        expected = fixture["expected_tool_call"]
        
        # Create ToolCall from expected data
        tool_call = ToolCall(
            name=expected["name"],
            arguments=expected["arguments"],
        )
        
        # Convert to dict
        result = tool_call.to_dict()
        
        # Verify roundtrip
        assert result["name"] == expected["name"]
        assert result["arguments"] == expected["arguments"]
        
        # Create another ToolCall from dict
        tool_call_2 = ToolCall(
            name=result["name"],
            arguments=result["arguments"],
        )
        
        assert tool_call_2.name == tool_call.name
        assert tool_call_2.arguments == tool_call.arguments
