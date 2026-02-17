"""Parse Gemini API responses for tool/function calls.

This module provides functionality to extract and parse function calls
from Gemini API responses into structured ToolCall objects.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ToolParserError(Exception):
    """Base exception for tool parser errors."""
    pass


class MalformedResponseError(ToolParserError):
    """Raised when response structure is malformed."""
    pass


@dataclass
class ToolCall:
    """Represents a parsed tool/function call from Gemini.
    
    This dataclass encapsulates all information about a tool call
    extracted from a Gemini API response.
    
    Attributes:
        name: Name of the tool/function to call.
        arguments: Dictionary of arguments for the function.
        raw_response: The original response object for reference.
    
    Example:
        >>> tool_call = ToolCall(
        ...     name="search_files",
        ...     arguments={"query": "python", "limit": 10},
        ...     raw_response={"function_call": {...}}
        ... )
        >>> print(tool_call.name)
        search_files
    """
    
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate tool call data after initialization."""
        if not self.name:
            raise ValueError("Tool call name cannot be empty")
        
        if not isinstance(self.arguments, dict):
            raise ValueError("Arguments must be a dictionary")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the tool call to a dictionary.
        
        Returns:
            Dictionary representation of the tool call.
        """
        return {
            "name": self.name,
            "arguments": self.arguments,
        }
    
    def __str__(self) -> str:
        """Return a string representation of the tool call."""
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"{self.name}({args_str})"


class ToolCallParser:
    """Parses Gemini API responses to extract tool calls.
    
    This class handles the extraction of function calls from various
    Gemini response formats, providing a unified interface for accessing
    tool call information.
    
    Example:
        >>> parser = ToolCallParser()
        >>> response = {"function_call": {"name": "search", "args": {"q": "test"}}}
        >>> tool_call = parser.parse_response(response)
        >>> print(tool_call.name)
        search
    """
    
    def parse_response(self, response: Any) -> Optional[ToolCall]:
        """Parse a Gemini response to extract a tool call.
        
        Handles multiple response formats:
        - GeminiClient processed response (dict with 'function_call' key)
        - Raw Gemini SDK response objects
        - Direct function call dictionaries
        
        Args:
            response: The response to parse. Can be:
                - A dictionary with 'function_call' key
                - A raw Gemini GenerateContentResponse object
                - None (returns None)
        
        Returns:
            A ToolCall object if a function call is found, None otherwise.
        
        Raises:
            MalformedResponseError: If the response structure is invalid.
        
        Example:
            >>> parser = ToolCallParser()
            >>> result = parser.parse_response({"function_call": {"name": "test", "args": {}}})
            >>> result.name
            'test'
        """
        if response is None:
            logger.debug("Response is None, no tool call")
            return None
        
        # Handle dictionary response (from GeminiClient)
        if isinstance(response, dict):
            return self._parse_dict_response(response)
        
        # Handle raw Gemini SDK response object
        if hasattr(response, "candidates"):
            return self._parse_raw_response(response)
        
        logger.warning(f"Unknown response type: {type(response)}")
        return None
    
    def _parse_dict_response(self, response: Dict[str, Any]) -> Optional[ToolCall]:
        """Parse a dictionary response.
        
        Args:
            response: Dictionary response to parse.
        
        Returns:
            ToolCall if function_call found, None otherwise.
        
        Raises:
            MalformedResponseError: If function_call structure is invalid.
        """
        function_call = response.get("function_call")
        
        if function_call is None:
            logger.debug("No function_call in response")
            return None
        
        if not isinstance(function_call, dict):
            raise MalformedResponseError(
                f"function_call must be a dictionary, got {type(function_call)}"
            )
        
        return self._extract_tool_call(function_call, response)
    
    def _parse_raw_response(self, response: Any) -> Optional[ToolCall]:
        """Parse a raw Gemini SDK response.
        
        Args:
            response: Raw GenerateContentResponse object.
        
        Returns:
            ToolCall if function call found, None otherwise.
        """
        if not response.candidates:
            logger.debug("No candidates in raw response")
            return None
        
        candidate = response.candidates[0]
        
        if not hasattr(candidate, "content") or not candidate.content:
            logger.debug("No content in candidate")
            return None
        
        if not hasattr(candidate.content, "parts") or not candidate.content.parts:
            logger.debug("No parts in content")
            return None
        
        # Look for function call in parts
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                return ToolCall(
                    name=fc.name,
                    arguments=dict(fc.args) if fc.args else {},
                    raw_response=self._response_to_dict(response),
                )
        
        logger.debug("No function call found in response parts")
        return None
    
    def _extract_tool_call(
        self,
        function_call: Dict[str, Any],
        raw_response: Dict[str, Any],
    ) -> ToolCall:
        """Extract ToolCall from function_call dictionary.
        
        Args:
            function_call: The function_call dictionary.
            raw_response: The original response for reference.
        
        Returns:
            Constructed ToolCall object.
        
        Raises:
            MalformedResponseError: If required fields are missing.
        """
        name = function_call.get("name")
        
        if not name:
            raise MalformedResponseError("function_call missing required 'name' field")
        
        # Handle both 'args' and 'arguments' keys (different Gemini versions)
        if "args" in function_call:
            arguments = function_call.get("args")
        elif "arguments" in function_call:
            arguments = function_call.get("arguments")
        else:
            arguments = {}
        
        if not isinstance(arguments, dict):
            raise MalformedResponseError(
                f"function_call arguments must be a dictionary, got {type(arguments)}"
            )
        
        logger.debug(f"Extracted tool call: {name}")
        
        return ToolCall(
            name=name,
            arguments=arguments,
            raw_response=raw_response,
        )
    
    def _response_to_dict(self, response: Any) -> Dict[str, Any]:
        """Convert a raw response object to a dictionary for storage.
        
        Args:
            response: Raw response object.
        
        Returns:
            Dictionary representation of the response.
        """
        try:
            # Try to use to_dict if available
            if hasattr(response, "to_dict"):
                return response.to_dict()
            
            # Build a minimal representation
            result: Dict[str, Any] = {"_type": str(type(response))}
            
            if hasattr(response, "candidates") and response.candidates:
                result["candidates_count"] = len(response.candidates)
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to convert response to dict: {e}")
            return {"_conversion_error": str(e)}
    
    def parse_response_safe(
        self,
        response: Any,
    ) -> tuple[Optional[ToolCall], Optional[str]]:
        """Parse response without raising exceptions.
        
        Args:
            response: The response to parse.
        
        Returns:
            Tuple of (tool_call, error_message).
            If successful, returns (ToolCall, None).
            If failed, returns (None, error_message).
        """
        try:
            tool_call = self.parse_response(response)
            return tool_call, None
        except MalformedResponseError as e:
            return None, f"Malformed response: {e}"
        except Exception as e:
            return None, f"Parse error: {e}"
