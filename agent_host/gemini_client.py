"""Gemini API client wrapper with retry logic.

This module provides a wrapper around the Google Gen AI SDK
for interacting with the Gemini API, including function calling support
and robust error handling with exponential backoff.

Uses the new `google.genai` Client API which allows per-request model selection.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, Union

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)


class GeminiClientError(Exception):
    """Base exception for Gemini client errors."""
    pass


class GeminiAPIError(GeminiClientError):
    """Raised when the Gemini API returns an error."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GeminiRateLimitError(GeminiAPIError):
    """Raised when rate limited (HTTP 429)."""
    pass


class GeminiServerError(GeminiAPIError):
    """Raised when server error occurs (HTTP 5xx)."""
    pass


class GeminiClient:
    """Client for interacting with the Gemini API.
    
    This class wraps the Google Gen AI SDK and provides:
    - Configuration of API credentials
    - Function/tool calling support
    - Per-request model selection (no restart needed to change models)
    - Automatic retry with exponential backoff
    - Error handling for rate limits and server errors
    
    Attributes:
        model_name: Default model name to use.
        max_retries: Maximum number of retry attempts.
        retry_delay: Initial delay between retries in seconds.
    
    Example:
        >>> client = GeminiClient(api_key="your-api-key")
        >>> tools = [{"name": "search_files", "description": "Search files", "parameters": {...}}]
        >>> response = client.send_prompt_with_tools("Find my Python files", tools)
        >>> # Use a different model for this request
        >>> response = client.send_prompt_with_tools("...", tools, model="gemini-3-pro-preview")
    """
    
    # HTTP status codes for retry logic
    RATE_LIMIT_STATUS = 429
    SERVER_ERROR_STATUSES = (500, 502, 503, 504)
    
    # Backoff configuration
    MAX_BACKOFF_DELAY = 60.0  # Maximum delay in seconds
    BACKOFF_MULTIPLIER = 2.0  # Exponential backoff multiplier
    _IMAGE_MODEL_ENV_VAR = "AI_AGENT_IMAGE_MODEL"
    _IMAGE_MODEL_CACHE_TTL_SECONDS = 600.0
    _IMAGE_SUPPORTED_ACTION_HINTS: tuple[str, ...] = (
        "image",
        "predict",
        "generate",
    )
    _IMAGE_QUALITY_PREFERENCES: dict[str, tuple[str, ...]] = {
        "fast": (
            "imagen-4.0-fast-generate-001",
            "imagen-3.0-fast-generate-001",
        ),
        "standard": (
            "imagen-4.0-generate-001",
            "imagen-3.0-generate-001",
        ),
        "ultra": (
            "imagen-4.0-ultra-generate-001",
        ),
    }
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-exp",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        *,
        require_no_training: bool = True,
        use_vertexai: bool = False,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
    ) -> None:
        """Initialize the Gemini client.
        
        Args:
            api_key: Google API key for authentication.
            model_name: Default model name to use (can be overridden per request).
            max_retries: Maximum number of retry attempts for failed requests.
            retry_delay: Initial delay in seconds between retry attempts.
            require_no_training: Fail closed unless backend mode can enforce no-training policy.
            use_vertexai: Route requests through Vertex AI.
            vertex_project: GCP project id when using Vertex AI.
            vertex_location: GCP location when using Vertex AI.
        
        Raises:
            GeminiClientError: If the API key is empty or invalid.
        """
        if not use_vertexai and not api_key:
            raise GeminiClientError("API key cannot be empty")

        if require_no_training and not use_vertexai:
            raise GeminiClientError(
                "No-training mode is enabled, but API-key Gemini Developer API is in use. "
                "Switch to Vertex AI by setting AI_AGENT_USE_VERTEXAI=true and "
                "AI_AGENT_VERTEX_PROJECT=<your-project-id>."
            )
        if use_vertexai and (not vertex_project or not vertex_project.strip()):
            raise GeminiClientError("vertex_project is required when use_vertexai is enabled")
        
        self.model_name = model_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.require_no_training = require_no_training
        self.use_vertexai = use_vertexai
        self.vertex_project = vertex_project.strip() if isinstance(vertex_project, str) else None
        self.vertex_location = vertex_location.strip() if vertex_location else "us-central1"

        if self.use_vertexai:
            self._client = genai.Client(
                vertexai=True,
                project=self.vertex_project,
                location=self.vertex_location,
            )
            logger.info(
                "Initialized GeminiClient (Vertex AI) with default model: %s, project=%s, location=%s",
                model_name,
                self.vertex_project,
                self.vertex_location,
            )
        else:
            self._client = genai.Client(api_key=api_key)
            logger.info("Initialized GeminiClient with default model: %s", model_name)
        self._cached_image_models: list[str] = []
        self._cached_image_models_expires_at = 0.0
    
    def send_prompt_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        deep_think: bool = False,
    ) -> Dict[str, Any]:
        """Send a prompt to Gemini with function calling configuration.
        
        Sends the user prompt along with tool definitions, allowing Gemini
        to respond with a function call if appropriate. Implements retry
        logic with exponential backoff for rate limits and server errors.
        
        The model can be changed per-request without restarting the client.
        
        Args:
            prompt: The user prompt to send.
            tools: List of tool definitions with 'name', 'description', and 'parameters'.
            system_instruction: Optional system instruction to guide model behavior.
            model: Optional model name for this request. If not provided,
                   uses the default model_name from the client instance.
            deep_think: Enable deeper reasoning controls when supported by the model.
        
        Returns:
            A dictionary containing the parsed response with fields:
            - 'text': Text response if any (may be None)
            - 'function_call': Function call data if any (may be None)
              - 'name': Name of the function to call
              - 'args': Arguments for the function
            - 'raw_response': The raw Gemini response object
        
        Raises:
            GeminiRateLimitError: If rate limited after all retries.
            GeminiServerError: If server error after all retries.
            GeminiAPIError: For other API errors.
            GeminiClientError: For client-side errors.
        
        Example:
            >>> tools = [{"name": "search_files", "parameters": {"type": "object", ...}}]
            >>> # Use default model
            >>> result = client.send_prompt_with_tools("Find Python files", tools)
            >>> # Use specific model for this request
            >>> result = client.send_prompt_with_tools("Find files", tools, model="gemini-3-flash-preview")
        """
        if not prompt:
            raise GeminiClientError("Prompt cannot be empty")
        
        if not tools:
            raise GeminiClientError("Tools list cannot be empty")
        
        # Use provided model or fall back to instance default
        model_name = model or self.model_name
        
        # Convert tools to new Gemini format
        gemini_tools = self._convert_tools_to_gemini_format(tools)
        
        # Build generation config
        config_kwargs: Dict[str, Any] = {
            "temperature": 0.1,  # Low temperature for more deterministic tool calls
            "tools": gemini_tools,
        }
        
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        
        thinking_config = self._build_thinking_config(
            model_name=model_name,
            deep_think=deep_think,
        )
        if thinking_config is not None:
            config_kwargs["thinking_config"] = thinking_config
            logger.info("Deep-think enabled for model '%s' with native thinking controls.", model_name)

        config = types.GenerateContentConfig(**config_kwargs)
        
        logger.info(f"Sending request with model: {model_name}")
        logger.debug(f"Full model name being used: '{model_name}'")
        
        # Execute with retry logic
        return self._execute_with_retry(
            model_name=model_name,
            contents=prompt,
            config=config,
        )

    def send_continuation(
        self,
        contents: List[Any],
        tools: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        deep_think: bool = False,
    ) -> Dict[str, Any]:
        """Continue a multi-turn conversation with tool results.

        Used by the tool chaining loop to feed function call results back
        to the model so it can decide on follow-up actions (e.g. calling
        ``apply_ops`` after ``plan_ops``).

        Args:
            contents: Conversation history as a list of ``types.Content``
                objects, including the original user prompt, model function
                calls, and function responses.
            tools: Tool definitions (same format as ``send_prompt_with_tools``).
            system_instruction: Optional system instruction.
            model: Optional model override.
            deep_think: Enable deeper reasoning controls when supported by the model.

        Returns:
            Parsed response dictionary (same shape as ``send_prompt_with_tools``).
        """
        if not contents:
            raise GeminiClientError("Contents list cannot be empty")
        if not tools:
            raise GeminiClientError("Tools list cannot be empty")

        model_name = model or self.model_name
        gemini_tools = self._convert_tools_to_gemini_format(tools)

        config_kwargs: Dict[str, Any] = {
            "temperature": 0.1,
            "tools": gemini_tools,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        thinking_config = self._build_thinking_config(
            model_name=model_name,
            deep_think=deep_think,
        )
        if thinking_config is not None:
            config_kwargs["thinking_config"] = thinking_config

        config = types.GenerateContentConfig(**config_kwargs)

        logger.info(f"Sending continuation with model: {model_name} ({len(contents)} turns)")

        return self._execute_with_retry(
            model_name=model_name,
            contents=contents,
            config=config,
        )

    def _build_thinking_config(
        self,
        *,
        model_name: str,
        deep_think: bool,
    ) -> Optional[types.ThinkingConfig]:
        """Return model-native thinking controls for deep-think mode when supported."""
        if not deep_think:
            return None

        normalized = model_name.strip().lower()
        if "gemini-3" in normalized:
            level_name = os.environ.get("AI_AGENT_DEEP_THINK_LEVEL_GEMINI3", "high")
            level = self._resolve_thinking_level(level_name)
            return types.ThinkingConfig(
                include_thoughts=False,
                thinking_level=level,
            )

        if "gemini-2.5" in normalized:
            budget = self._parse_int_env(
                "AI_AGENT_DEEP_THINK_BUDGET_GEMINI25",
                default=12288,
                minimum=128,
                maximum=32768,
            )
            return types.ThinkingConfig(
                include_thoughts=False,
                thinking_budget=budget,
            )

        raise GeminiClientError(
            "Deep-think mode requires a reasoning-enabled model with native thinking controls "
            f"(got '{model_name}'). Use Gemini 3 or Gemini 2.5."
        )

    @staticmethod
    def _resolve_thinking_level(raw_value: str) -> types.ThinkingLevel:
        """Map string values to SDK ThinkingLevel enum with a safe default."""
        normalized = raw_value.strip().lower()
        mapping = {
            "minimal": types.ThinkingLevel.MINIMAL,
            "low": types.ThinkingLevel.LOW,
            "medium": types.ThinkingLevel.MEDIUM,
            "high": types.ThinkingLevel.HIGH,
        }
        return mapping.get(normalized, types.ThinkingLevel.HIGH)

    @staticmethod
    def _parse_int_env(
        name: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        raw = os.environ.get(name, "")
        try:
            parsed = int(str(raw).strip())
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, parsed))

    def _convert_tools_to_gemini_format(
        self,
        tools: List[Dict[str, Any]],
    ) -> List[types.Tool]:
        """Convert tool schemas to Gemini function declaration format.
        
        Args:
            tools: List of tool definitions with JSON Schema parameters.
        
        Returns:
            List of Gemini Tool objects.
        """
        function_declarations = []
        
        for tool in tools:
            # Build function declaration using the new types API
            func_decl = types.FunctionDeclaration(
                name=tool.get("name", tool.get("title", "")),
                description=tool.get("description", ""),
                parameters_json_schema=tool.get("parameters", {}),
            )
            function_declarations.append(func_decl)
        
        return [types.Tool(function_declarations=function_declarations)]

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        normalized = model_name.strip()
        if normalized.startswith("models/"):
            normalized = normalized[len("models/") :]
        return normalized

    @staticmethod
    def _resolve_person_generation(value: str) -> types.PersonGeneration:
        normalized = value.strip().lower()
        mapping = {
            "dont_allow": types.PersonGeneration.DONT_ALLOW,
            "allow_adult": types.PersonGeneration.ALLOW_ADULT,
            "allow_all": types.PersonGeneration.ALLOW_ALL,
        }
        resolved = mapping.get(normalized)
        if resolved is None:
            raise GeminiClientError(
                "person_generation must be one of: dont_allow, allow_adult, allow_all"
            )
        return resolved

    def _list_available_image_models(self, *, force_refresh: bool = False) -> list[str]:
        now = time.time()
        if (
            not force_refresh
            and self._cached_image_models
            and now < self._cached_image_models_expires_at
        ):
            return list(self._cached_image_models)

        try:
            try:
                pager = self._client.models.list(
                    config=types.ListModelsConfig(page_size=200),
                )
            except TypeError:
                pager = self._client.models.list()
        except Exception as exc:
            raise GeminiClientError(f"Failed to list image models: {exc}") from exc

        discovered: set[str] = set()
        for model in pager:
            raw_name = str(getattr(model, "name", "") or "").strip()
            if not raw_name:
                continue
            normalized = self._normalize_model_name(raw_name)
            lowered = normalized.lower()
            if "imagen" not in lowered:
                continue

            supported_actions = getattr(model, "supported_actions", None)
            if isinstance(supported_actions, (list, tuple, set)) and supported_actions:
                lowered_actions = {str(action).lower() for action in supported_actions}
                if not any(
                    any(hint in action for hint in self._IMAGE_SUPPORTED_ACTION_HINTS)
                    for action in lowered_actions
                ):
                    continue
            discovered.add(normalized)

        models = sorted(discovered)
        self._cached_image_models = models
        self._cached_image_models_expires_at = now + self._IMAGE_MODEL_CACHE_TTL_SECONDS
        return list(models)

    def resolve_image_model(
        self,
        *,
        quality_tier: str = "standard",
        model_override: str | None = None,
    ) -> str:
        available = self._list_available_image_models()
        if not available:
            raise GeminiClientError(
                "No image generation models are available for this account/project."
            )

        configured_override = (model_override or os.environ.get(self._IMAGE_MODEL_ENV_VAR, "")).strip()
        if configured_override:
            normalized_override = self._normalize_model_name(configured_override)
            if normalized_override not in available:
                raise GeminiClientError(
                    f"Configured image model '{configured_override}' is unavailable. "
                    f"Available image models: {', '.join(available)}"
                )
            return normalized_override

        normalized_tier = quality_tier.strip().lower()
        preferences = self._IMAGE_QUALITY_PREFERENCES.get(normalized_tier)
        if preferences is None:
            raise GeminiClientError(
                "quality_tier must be one of: fast, standard, ultra"
            )

        for preferred in preferences:
            if preferred in available:
                return preferred

        if normalized_tier == "fast":
            tier_candidates = [
                name for name in available if "fast" in name.lower()
            ]
        elif normalized_tier == "ultra":
            tier_candidates = [
                name for name in available if "ultra" in name.lower()
            ]
        else:
            tier_candidates = [
                name
                for name in available
                if "fast" not in name.lower() and "ultra" not in name.lower()
            ]

        if not tier_candidates:
            raise GeminiClientError(
                f"No available image model satisfies quality_tier='{normalized_tier}'. "
                f"Available image models: {', '.join(available)}"
            )

        return sorted(tier_candidates, reverse=True)[0]

    def generate_images(
        self,
        *,
        prompt: str,
        quality_tier: str = "standard",
        number_of_images: int = 1,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        enhance_prompt: bool = True,
        person_generation: str = "allow_adult",
        negative_prompt: str | None = None,
        seed: int | None = None,
        model_override: str | None = None,
        output_mime_type: str = "image/png",
    ) -> Dict[str, Any]:
        if not prompt or not prompt.strip():
            raise GeminiClientError("Image prompt cannot be empty")
        if number_of_images < 1 or number_of_images > 4:
            raise GeminiClientError("number_of_images must be between 1 and 4")
        if output_mime_type not in {"image/png", "image/jpeg"}:
            raise GeminiClientError("output_mime_type must be image/png or image/jpeg")

        model_name = self.resolve_image_model(
            quality_tier=quality_tier,
            model_override=model_override,
        )
        person_generation_enum = self._resolve_person_generation(person_generation)
        config_kwargs: dict[str, Any] = {
            "number_of_images": number_of_images,
            "output_mime_type": output_mime_type,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "enhance_prompt": enhance_prompt,
            "person_generation": person_generation_enum,
            "safety_filter_level": types.SafetyFilterLevel.BLOCK_MEDIUM_AND_ABOVE,
            "include_safety_attributes": True,
            "include_rai_reason": True,
        }
        if negative_prompt and negative_prompt.strip():
            config_kwargs["negative_prompt"] = negative_prompt.strip()
        if seed is not None:
            config_kwargs["seed"] = seed
        config = types.GenerateImagesConfig(**config_kwargs)

        last_exception: Optional[Exception] = None
        delay = self.retry_delay
        for attempt in range(self.max_retries + 1):
            try:
                logger.info("[MODEL_VERIFICATION] Calling image API with model='%s'", model_name)
                response = self._client.models.generate_images(
                    model=model_name,
                    prompt=prompt,
                    config=config,
                )

                images: list[dict[str, Any]] = []
                generated_images = getattr(response, "generated_images", None) or []
                for generated in generated_images:
                    image_obj = getattr(generated, "image", None)
                    raw_bytes = getattr(image_obj, "image_bytes", None) if image_obj else None
                    image_bytes = (
                        bytes(raw_bytes)
                        if isinstance(raw_bytes, (bytes, bytearray, memoryview))
                        else b""
                    )
                    width = int(getattr(image_obj, "width", 0) or 0) if image_obj else 0
                    height = int(getattr(image_obj, "height", 0) or 0) if image_obj else 0
                    images.append(
                        {
                            "bytes": image_bytes,
                            "width": width,
                            "height": height,
                            "rai_filtered_reason": str(
                                getattr(generated, "rai_filtered_reason", "") or ""
                            ),
                            "safety_attributes": getattr(generated, "safety_attributes", None),
                        }
                    )
                return {
                    "model": model_name,
                    "images": images,
                    "raw_response": response,
                }
            except genai_errors.APIError as e:
                error_code = getattr(e, "code", None)
                error_message = getattr(e, "message", None)
                if not isinstance(error_message, str) or not error_message.strip():
                    details = getattr(e, "details", None)
                    error_message = str(details) if details else str(e)
                error_message = str(error_message).strip() or "Gemini image request failed."

                if error_code == 429:
                    last_exception = GeminiRateLimitError(
                        f"Image generation rate limit exceeded: {error_message}",
                        status_code=429,
                    )
                elif error_code in (500, 502, 503, 504):
                    last_exception = GeminiServerError(
                        f"Image generation server error ({error_code}): {error_message}",
                        status_code=error_code,
                    )
                else:
                    raise GeminiAPIError(
                        f"Image generation API error ({error_code}): {error_message}",
                        status_code=error_code,
                    ) from e
            except Exception as e:
                detail = str(e).strip()
                if detail:
                    raise GeminiClientError(f"Image generation failed: {detail}") from e
                raise GeminiClientError(
                    f"Image generation failed with no details ({e.__class__.__name__})"
                ) from e

            if attempt < self.max_retries:
                logger.info("Retrying image request in %.1f seconds...", delay)
                time.sleep(delay)
                delay = min(delay * self.BACKOFF_MULTIPLIER, self.MAX_BACKOFF_DELAY)

        if last_exception:
            raise last_exception
        raise GeminiClientError("All image generation retry attempts failed")
    
    def _execute_with_retry(
        self,
        model_name: str,
        contents: Union[str, List[Any]],
        config: types.GenerateContentConfig,
    ) -> Dict[str, Any]:
        """Execute API call with retry logic.

        Args:
            model_name: The model to use for this request.
            contents: Either a plain prompt string or a list of Content
                objects for multi-turn conversations.
            config: Generation configuration including tools and system instruction.

        Returns:
            Parsed response dictionary.

        Raises:
            GeminiRateLimitError: If rate limited after all retries.
            GeminiServerError: If server error after all retries.
            GeminiAPIError: For other API errors.
        """
        last_exception: Optional[Exception] = None
        delay = self.retry_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"API call attempt {attempt + 1}/{self.max_retries + 1}")
                logger.info(f"[MODEL_VERIFICATION] Calling API with model='{model_name}'")
                
                # Use the new client.models.generate_content API
                # Model is specified per-request - no need to recreate client
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                
                return self._parse_response(response)
                
            except genai_errors.APIError as e:
                # Handle API errors based on error code
                error_code = getattr(e, 'code', None)
                error_message = getattr(e, "message", None)
                if not isinstance(error_message, str) or not error_message.strip():
                    details = getattr(e, "details", None)
                    if details:
                        error_message = str(details)
                    else:
                        error_message = str(e)
                if not isinstance(error_message, str):
                    error_message = str(error_message)
                error_message = error_message.strip() or "Gemini API request failed without details."
                
                if error_code == 429:
                    # Rate limit error
                    last_exception = GeminiRateLimitError(
                        f"Rate limit exceeded: {error_message}",
                        status_code=429,
                    )
                    logger.warning(f"Rate limited, attempt {attempt + 1}: {error_message}")
                elif error_code in (500, 502, 503, 504):
                    # Server error
                    last_exception = GeminiServerError(
                        f"Server error ({error_code}): {error_message}",
                        status_code=error_code,
                    )
                    logger.warning(f"Server error, attempt {attempt + 1}: {error_message}")
                else:
                    # Other API errors - don't retry
                    raise GeminiAPIError(
                        f"API error ({error_code}): {error_message}",
                        status_code=error_code,
                    )
            
            except Exception as e:
                # Unexpected errors - don't retry
                detail = str(e).strip()
                if detail:
                    raise GeminiClientError(f"Unexpected error: {detail}")
                raise GeminiClientError(
                    f"Unexpected error with no details ({e.__class__.__name__})"
                )
            
            # Wait before retrying (only if not the last attempt)
            if attempt < self.max_retries:
                logger.info(f"Retrying in {delay:.1f} seconds...")
                time.sleep(delay)
                delay = min(delay * self.BACKOFF_MULTIPLIER, self.MAX_BACKOFF_DELAY)
        
        # All retries exhausted
        if last_exception:
            raise last_exception
        
        raise GeminiClientError("All retry attempts failed")
    
    def _parse_response(
        self,
        response: Any,
    ) -> Dict[str, Any]:
        """Parse Gemini response into a structured dictionary.
        
        Args:
            response: Raw response from Gemini API.
        
        Returns:
            Dictionary with 'text', 'function_call', and 'raw_response' keys.
        """
        result: Dict[str, Any] = {
            "text": None,
            "function_call": None,
            "raw_response": response,
        }
        
        # Check for function calls (new API uses response.function_calls)
        if hasattr(response, 'function_calls') and response.function_calls:
            fc = response.function_calls[0]  # Take first function call
            try:
                args = dict(fc.args) if fc.args else {}
            except (TypeError, ValueError):
                args = {}
                logger.warning("Could not convert function call args to dict for %s", fc.name)
            result["function_call"] = {
                "name": fc.name,
                "args": args,
            }
            logger.debug(f"Parsed function call: {fc.name}")
        
        # Check for text response.
        # Guard: the Gemini SDK .text property raises ValueError when the
        # response contains non-text parts (e.g. function_call only).
        try:
            if hasattr(response, 'text') and response.text:
                result["text"] = response.text
                logger.debug(f"Parsed text response: {len(response.text)} chars")
        except (ValueError, AttributeError):
            pass
        
        if result["text"] is None and result["function_call"] is None:
            logger.warning("Empty response from Gemini API")
        
        return result
