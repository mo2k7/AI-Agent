"""Unit tests for ToolCallParser.

Tests parsing of Gemini API responses for function/tool calls.
"""

import pytest
from unittest.mock import Mock

from agent_host.tool_parser import (
    ToolCallParser,
    ToolCall,
    MalformedResponseError,
)


class TestToolCall:
    """Tests for the ToolCall dataclass."""
    
    def test_create_valid_tool_call(self) -> None:
        """Test creating a valid ToolCall."""
        tool_call = ToolCall(
            name="search_files",
            arguments={"query": "python"},
        )
        
        assert tool_call.name == "search_files"
        assert tool_call.arguments == {"query": "python"}
    
    def test_empty_name_raises_error(self) -> None:
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ToolCall(name="", arguments={})
        
        assert "cannot be empty" in str(exc_info.value)
    
    def test_invalid_arguments_type_raises_error(self) -> None:
        """Test that non-dict arguments raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ToolCall(name="test", arguments="not-a-dict")  # type: ignore
        
        assert "must be a dictionary" in str(exc_info.value)
    
    def test_to_dict(self) -> None:
        """Test ToolCall.to_dict() method."""
        tool_call = ToolCall(
            name="search_files",
            arguments={"query": "python", "limit": 10},
        )
        
        result = tool_call.to_dict()
        
        assert result == {
            "name": "search_files",
            "arguments": {"query": "python", "limit": 10},
        }
    
    def test_str_representation(self) -> None:
        """Test string representation of ToolCall."""
        tool_call = ToolCall(
            name="search_files",
            arguments={"query": "python"},
        )
        
        result = str(tool_call)
        
        assert "search_files" in result
        assert "query" in result
        assert "python" in result
    
    def test_default_arguments(self) -> None:
        """Test that arguments default to empty dict."""
        tool_call = ToolCall(name="test_tool")
        
        assert tool_call.arguments == {}
    
    def test_raw_response_stored(self) -> None:
        """Test that raw_response is stored."""
        raw = {"function_call": {"name": "test", "args": {}}}
        tool_call = ToolCall(
            name="test",
            arguments={},
            raw_response=raw,
        )
        
        assert tool_call.raw_response == raw


class TestParseValidResponse:
    """Tests for parsing valid function_call responses."""
    
    def test_parse_dict_with_args(self) -> None:
        """Test parsing dict response with 'args' key."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "search_files",
                "args": {"query": "python files", "limit": 10}
            }
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert result.name == "search_files"
        assert result.arguments == {"query": "python files", "limit": 10}
    
    def test_parse_dict_with_arguments(self) -> None:
        """Test parsing dict response with 'arguments' key."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "get_metadata",
                "arguments": {"paths": ["/Users/test/file.txt"]}
            }
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert result.name == "get_metadata"
        assert result.arguments == {"paths": ["/Users/test/file.txt"]}
    
    def test_parse_with_both_args_and_arguments(self) -> None:
        """Test that 'args' takes precedence over 'arguments'."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test",
                "args": {"from_args": True},
                "arguments": {"from_arguments": True}
            }
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        # 'args' should take precedence
        assert result.arguments == {"from_args": True}

    def test_parse_with_empty_args_and_arguments(self) -> None:
        """Test that empty 'args' still takes precedence over 'arguments'."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test",
                "args": {},
                "arguments": {"from_arguments": True}
            }
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert result.arguments == {}
    
    def test_parse_with_empty_args(self) -> None:
        """Test parsing response with empty arguments."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test_tool",
                "args": {}
            }
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert result.name == "test_tool"
        assert result.arguments == {}
    
    def test_parse_with_missing_args(self) -> None:
        """Test parsing response with no args/arguments key."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "simple_tool"
            }
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert result.name == "simple_tool"
        assert result.arguments == {}
    
    def test_parse_complex_arguments(self) -> None:
        """Test parsing response with complex nested arguments."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "plan_ops",
                "args": {
                    "ops": [
                        {"op": "move", "src": "/a.txt", "dest": "/b.txt"},
                        {"op": "rename", "src": "/c.txt", "dest": "/d.txt"}
                    ],
                    "dry_run": True
                }
            }
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert result.name == "plan_ops"
        assert len(result.arguments["ops"]) == 2
        assert result.arguments["dry_run"] is True


class TestParseMissingFunctionCall:
    """Tests for handling responses without function_call."""
    
    def test_none_response_returns_none(self) -> None:
        """Test that None response returns None."""
        parser = ToolCallParser()
        
        result = parser.parse_response(None)
        
        assert result is None
    
    def test_empty_dict_returns_none(self) -> None:
        """Test that empty dict returns None."""
        parser = ToolCallParser()
        
        result = parser.parse_response({})
        
        assert result is None
    
    def test_dict_without_function_call_returns_none(self) -> None:
        """Test that dict without function_call returns None."""
        parser = ToolCallParser()
        response = {
            "text": "I'll help you with that.",
            "other_field": "value"
        }
        
        result = parser.parse_response(response)
        
        assert result is None
    
    def test_function_call_is_none_returns_none(self) -> None:
        """Test that function_call=None returns None."""
        parser = ToolCallParser()
        response = {
            "function_call": None,
            "text": "Some text"
        }
        
        result = parser.parse_response(response)
        
        assert result is None


class TestParseMalformedResponse:
    """Tests for handling malformed responses."""
    
    def test_function_call_not_dict_raises_error(self) -> None:
        """Test that non-dict function_call raises error."""
        parser = ToolCallParser()
        response = {
            "function_call": "not-a-dict"
        }
        
        with pytest.raises(MalformedResponseError) as exc_info:
            parser.parse_response(response)
        
        assert "must be a dictionary" in str(exc_info.value)
    
    def test_function_call_is_list_raises_error(self) -> None:
        """Test that list function_call raises error."""
        parser = ToolCallParser()
        response = {
            "function_call": [{"name": "test", "args": {}}]
        }
        
        with pytest.raises(MalformedResponseError):
            parser.parse_response(response)
    
    def test_missing_name_raises_error(self) -> None:
        """Test that missing name raises error."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "args": {"query": "test"}
            }
        }
        
        with pytest.raises(MalformedResponseError) as exc_info:
            parser.parse_response(response)
        
        assert "missing required 'name' field" in str(exc_info.value)
    
    def test_empty_name_raises_error(self) -> None:
        """Test that empty name raises error."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "",
                "args": {}
            }
        }
        
        with pytest.raises(MalformedResponseError) as exc_info:
            parser.parse_response(response)
        
        assert "missing required 'name' field" in str(exc_info.value)
    
    def test_arguments_not_dict_raises_error(self) -> None:
        """Test that non-dict arguments raises error."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test",
                "args": "not-a-dict"
            }
        }
        
        with pytest.raises(MalformedResponseError) as exc_info:
            parser.parse_response(response)
        
        assert "must be a dictionary" in str(exc_info.value)
    
    def test_arguments_is_list_raises_error(self) -> None:
        """Test that list arguments raises error."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test",
                "args": ["arg1", "arg2"]
            }
        }
        
        with pytest.raises(MalformedResponseError):
            parser.parse_response(response)


class TestParseRawResponse:
    """Tests for parsing raw Gemini SDK response objects."""
    
    def test_parse_raw_response_with_function_call(self) -> None:
        """Test parsing raw Gemini response with function call."""
        parser = ToolCallParser()
        
        # Create mock raw response
        mock_function_call = Mock()
        mock_function_call.name = "search_files"
        mock_function_call.args = {"query": "python"}
        
        mock_part = Mock()
        mock_part.function_call = mock_function_call
        
        mock_content = Mock()
        mock_content.parts = [mock_part]
        
        mock_candidate = Mock()
        mock_candidate.content = mock_content
        
        mock_response = Mock()
        mock_response.candidates = [mock_candidate]
        
        result = parser.parse_response(mock_response)
        
        assert result is not None
        assert result.name == "search_files"
        assert result.arguments == {"query": "python"}
    
    def test_parse_raw_response_empty_candidates(self) -> None:
        """Test parsing raw response with empty candidates."""
        parser = ToolCallParser()
        
        mock_response = Mock()
        mock_response.candidates = []
        
        result = parser.parse_response(mock_response)
        
        assert result is None
    
    def test_parse_raw_response_no_content(self) -> None:
        """Test parsing raw response with no content."""
        parser = ToolCallParser()
        
        mock_candidate = Mock()
        mock_candidate.content = None
        
        mock_response = Mock()
        mock_response.candidates = [mock_candidate]
        
        result = parser.parse_response(mock_response)
        
        assert result is None
    
    def test_parse_raw_response_no_parts(self) -> None:
        """Test parsing raw response with no parts."""
        parser = ToolCallParser()
        
        mock_content = Mock()
        mock_content.parts = []
        
        mock_candidate = Mock()
        mock_candidate.content = mock_content
        
        mock_response = Mock()
        mock_response.candidates = [mock_candidate]
        
        result = parser.parse_response(mock_response)
        
        assert result is None
    
    def test_parse_raw_response_text_only(self) -> None:
        """Test parsing raw response with text only (no function call)."""
        parser = ToolCallParser()
        
        mock_part = Mock()
        mock_part.function_call = None
        mock_part.text = "This is a text response"
        
        mock_content = Mock()
        mock_content.parts = [mock_part]
        
        mock_candidate = Mock()
        mock_candidate.content = mock_content
        
        mock_response = Mock()
        mock_response.candidates = [mock_candidate]
        
        result = parser.parse_response(mock_response)
        
        assert result is None


class TestSafeParsing:
    """Tests for parse_response_safe method."""
    
    def test_successful_parse_returns_tool_call(self) -> None:
        """Test safe parse with valid response."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test",
                "args": {"value": 123}
            }
        }
        
        tool_call, error = parser.parse_response_safe(response)
        
        assert tool_call is not None
        assert tool_call.name == "test"
        assert error is None
    
    def test_no_function_call_returns_none(self) -> None:
        """Test safe parse with no function call."""
        parser = ToolCallParser()
        
        tool_call, error = parser.parse_response_safe({"text": "hello"})
        
        assert tool_call is None
        assert error is None
    
    def test_malformed_response_returns_error(self) -> None:
        """Test safe parse with malformed response."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "args": {}  # missing name
            }
        }
        
        tool_call, error = parser.parse_response_safe(response)
        
        assert tool_call is None
        assert error is not None
        assert "Malformed response" in error
    
    def test_invalid_args_returns_error(self) -> None:
        """Test safe parse with invalid args type."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test",
                "args": "not-a-dict"
            }
        }
        
        tool_call, error = parser.parse_response_safe(response)
        
        assert tool_call is None
        assert error is not None


class TestUnknownResponseTypes:
    """Tests for handling unknown response types."""
    
    def test_unknown_type_returns_none(self) -> None:
        """Test that unknown type returns None."""
        parser = ToolCallParser()
        
        # Pass something that's not dict, None, or has 'candidates'
        result = parser.parse_response("just a string")
        
        assert result is None
    
    def test_number_returns_none(self) -> None:
        """Test that number returns None."""
        parser = ToolCallParser()
        
        result = parser.parse_response(12345)
        
        assert result is None
    
    def test_list_returns_none(self) -> None:
        """Test that list returns None."""
        parser = ToolCallParser()
        
        result = parser.parse_response([{"function_call": {"name": "test"}}])
        
        assert result is None


class TestRawResponseStorage:
    """Tests for raw response storage in ToolCall."""
    
    def test_dict_response_stored(self) -> None:
        """Test that dict response is stored in raw_response."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "test",
                "args": {"key": "value"}
            },
            "other_data": "preserved"
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert result.raw_response == response
        assert result.raw_response["other_data"] == "preserved"
    
    def test_raw_response_useful_for_debugging(self) -> None:
        """Test that raw_response contains useful debug info."""
        parser = ToolCallParser()
        response = {
            "function_call": {
                "name": "search_files",
                "args": {"query": "test"}
            },
            "text": None,
            "metadata": {"model": "gemini-2.0-flash"},
        }
        
        result = parser.parse_response(response)
        
        assert result is not None
        assert "metadata" in result.raw_response
        assert result.raw_response["metadata"]["model"] == "gemini-2.0-flash"
