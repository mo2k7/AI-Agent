"""Gemini API client wrapper with retry logic.

This module provides a wrapper around the Google Gen AI SDK
for interacting with the Gemini API, including function calling support
and robust error handling with exponential backoff.

Uses the new `google.genai` Client API which allows per-request model selection.
"""

import logging
import os
import re
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
        >>> response = client.send_prompt_with_tools("...", tools, model="gemini-2.5-pro")
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

    @staticmethod
    def _resolve_http_timeout_seconds() -> Optional[float]:
        """Resolve SDK HTTP timeout from environment."""
        timeout_source = "AI_AGENT_GEMINI_HTTP_TIMEOUT_SECONDS"
        raw_timeout = os.environ.get(timeout_source, "").strip()
        if not raw_timeout:
            timeout_source = "AI_AGENT_MODEL_TIMEOUT_SECONDS"
            raw_timeout = os.environ.get(timeout_source, "").strip()
        if not raw_timeout:
            return None
        try:
            timeout_seconds = float(raw_timeout)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid %s value %r for Gemini HTTP timeout",
                timeout_source,
                raw_timeout,
            )
            return None
        if timeout_seconds <= 0:
            logger.warning(
                "Ignoring non-positive %s value %r for Gemini HTTP timeout",
                timeout_source,
                raw_timeout,
            )
            return None
        return timeout_seconds
    
    def __init__(
        self,
        api_key: str,
        model_name: str | None = None,
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
                When omitted, the client resolves the best available text model
                dynamically from the live Gemini catalog.
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
        
        self.model_name = self._normalize_model_name(model_name) if model_name else ""
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.require_no_training = require_no_training
        self.use_vertexai = use_vertexai
        self.vertex_project = vertex_project.strip() if isinstance(vertex_project, str) else None
        self.vertex_location = vertex_location.strip() if vertex_location else "us-central1"
        self.http_timeout_seconds = self._resolve_http_timeout_seconds()
        http_options = (
            types.HttpOptions(timeout=self.http_timeout_seconds)
            if self.http_timeout_seconds is not None
            else None
        )

        if self.use_vertexai:
            client_kwargs: Dict[str, Any] = {
                "vertexai": True,
                "project": self.vertex_project,
                "location": self.vertex_location,
            }
            if http_options is not None:
                client_kwargs["http_options"] = http_options
            self._client = genai.Client(
                **client_kwargs,
            )
            logger.info(
                "Initialized GeminiClient (Vertex AI) with default model: %s, project=%s, location=%s, http_timeout=%s",
                self.model_name or "<auto>",
                self.vertex_project,
                self.vertex_location,
                self.http_timeout_seconds if self.http_timeout_seconds is not None else "default",
            )
        else:
            client_kwargs = {"api_key": api_key}
            if http_options is not None:
                client_kwargs["http_options"] = http_options
            self._client = genai.Client(**client_kwargs)
            logger.info(
                "Initialized GeminiClient with default model: %s, http_timeout=%s",
                self.model_name or "<auto>",
                self.http_timeout_seconds if self.http_timeout_seconds is not None else "default",
            )
        self._cached_image_models: list[str] = []
        self._cached_image_models_expires_at = 0.0
        self._cached_models: list[dict[str, Any]] = []
        self._cached_models_expires_at = 0.0
    
    _MODEL_CACHE_TTL_SECONDS = 600.0

    def list_models(
        self,
        *,
        filter_action: str | None = None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """List all available Gemini models.

        Args:
            filter_action: Optional action to filter by (e.g. ``"generateContent"``,
                ``"embedContent"``).  Only models whose ``supported_actions`` include
                the given action are returned.
            force_refresh: Bypass the cache and re-fetch from the API.

        Returns:
            List of model info dicts with keys: ``name``, ``display_name``,
            ``description``, ``supported_actions``, ``input_token_limit``,
            ``output_token_limit``.
        """
        now = time.time()
        if (
            not force_refresh
            and self._cached_models
            and now < self._cached_models_expires_at
        ):
            models = self._cached_models
        else:
            try:
                try:
                    pager = self._client.models.list(
                        config=types.ListModelsConfig(page_size=200),
                    )
                except TypeError:
                    pager = self._client.models.list()
            except Exception as exc:
                raise GeminiClientError(f"Failed to list models: {exc}") from exc

            models = []
            for model in pager:
                raw_name = str(getattr(model, "name", "") or "").strip()
                if not raw_name:
                    continue
                normalized_name = self._normalize_model_name(raw_name)
                supported_actions = getattr(model, "supported_actions", None) or []
                if not isinstance(supported_actions, (list, tuple)):
                    supported_actions = []
                record = {
                    "name": normalized_name,
                    "display_name": str(getattr(model, "display_name", "") or ""),
                    "description": str(getattr(model, "description", "") or ""),
                    "supported_actions": [str(a) for a in supported_actions],
                    "input_token_limit": int(getattr(model, "input_token_limit", 0) or 0),
                    "output_token_limit": int(getattr(model, "output_token_limit", 0) or 0),
                }
                record.update(self._derive_model_metadata(record))
                models.append(record)
            self._cached_models = self._sort_model_catalog(models)
            self._cached_models_expires_at = now + self._MODEL_CACHE_TTL_SECONDS

        if filter_action:
            lowered_filter = filter_action.strip().lower()
            return [
                m for m in models
                if any(lowered_filter in str(a).lower() for a in m["supported_actions"])
            ]
        return list(models)

    @classmethod
    def _extract_model_version(cls, model_name: str) -> tuple[int, int, int]:
        lowered = model_name.strip().lower()
        match = re.search(r"gemini-(\d+)(?:\.(\d+))?(?:[.-](\d+))?", lowered)
        if match is None:
            match = re.search(r"imagen-(\d+)(?:\.(\d+))?(?:[.-](\d+))?", lowered)
        if match is None:
            return (0, 0, 0)
        major = int(match.group(1) or 0)
        minor = int(match.group(2) or 0)
        patch = int(match.group(3) or 0)
        return (major, minor, patch)

    @classmethod
    def _looks_like_preview_model(cls, value: str) -> bool:
        lowered = value.strip().lower()
        return any(token in lowered for token in ("preview", "experimental", "exp"))

    @classmethod
    def _supports_native_deep_think(cls, model_name: str) -> bool:
        lowered = model_name.strip().lower()
        major, minor, _ = cls._extract_model_version(lowered)
        if not lowered.startswith("gemini-"):
            return False
        if major >= 3:
            return True
        return major == 2 and minor >= 5

    @classmethod
    def _derive_model_metadata(cls, model_info: dict[str, Any]) -> dict[str, Any]:
        normalized_name = str(model_info.get("name", "") or "").strip()
        display_name = str(model_info.get("display_name", "") or "").strip()
        description = str(model_info.get("description", "") or "").strip()
        supported_actions = model_info.get("supported_actions", []) or []
        lowered_actions = [str(action).lower() for action in supported_actions]
        lowered_name = normalized_name.lower()
        return {
            "is_preview": cls._looks_like_preview_model(normalized_name)
            or cls._looks_like_preview_model(display_name)
            or cls._looks_like_preview_model(description),
            "supports_deep_think": cls._supports_native_deep_think(normalized_name),
            "is_text_generation_model": cls._is_selectable_text_model_name(
                lowered_name,
                lowered_actions,
            ),
            "is_image_generation_model": cls._is_image_generation_model_name(
                lowered_name,
                lowered_actions,
            ),
        }

    @classmethod
    def _sort_model_catalog(cls, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            models,
            key=lambda model: (
                1 if model.get("is_text_generation_model") else 0,
                1 if not model.get("is_preview") else 0,
                cls._extract_model_version(str(model.get("name", ""))),
                int(model.get("output_token_limit", 0) or 0),
                int(model.get("input_token_limit", 0) or 0),
                str(model.get("display_name", "") or model.get("name", "")).lower(),
            ),
            reverse=True,
        )

    @classmethod
    def _is_selectable_text_model_name(
        cls,
        lowered_name: str,
        lowered_actions: list[str],
    ) -> bool:
        if not lowered_name.startswith("gemini-"):
            return False
        if any(token in lowered_name for token in ("image", "embedding", "embed", "tts", "aqa")):
            return False
        if not lowered_actions:
            return True
        return any("generatecontent" in action for action in lowered_actions)

    @classmethod
    def _is_image_generation_model_name(
        cls,
        lowered_name: str,
        lowered_actions: list[str],
    ) -> bool:
        if lowered_name.startswith("gemini-") and "image" in lowered_name:
            return True
        if lowered_name.startswith("imagen-"):
            return True
        if not lowered_actions:
            return False
        if lowered_name.startswith("gemini-") and any(
            any(hint in action for hint in cls._IMAGE_SUPPORTED_ACTION_HINTS)
            for action in lowered_actions
        ):
            return "image" in lowered_name
        return False

    def list_text_models(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        return [
            model
            for model in self.list_models(force_refresh=force_refresh)
            if model.get("is_text_generation_model")
        ]

    def resolve_text_model(self, model_override: str | None = None) -> str:
        available_models = self.list_text_models()
        if not available_models:
            raise GeminiClientError("No text-generation Gemini models are available for this account/project.")

        requested_model = (model_override or self.model_name or "").strip()
        if requested_model:
            normalized = self._normalize_model_name(requested_model)
            available_names = {str(model["name"]) for model in available_models}
            if normalized not in available_names:
                raise GeminiClientError(
                    f"Configured model '{requested_model}' is unavailable. "
                    f"Available text models: {', '.join(sorted(available_names))}"
                )
            return normalized

        ranked_models = sorted(
            available_models,
            key=self._text_model_sort_key,
            reverse=True,
        )
        resolved = str(ranked_models[0]["name"])
        self.model_name = resolved
        return resolved

    @classmethod
    def _text_model_sort_key(cls, model_info: dict[str, Any]) -> tuple[Any, ...]:
        normalized_name = str(model_info.get("name", "") or "").strip().lower()
        version = cls._extract_model_version(normalized_name)
        stable_rank = 1 if not model_info.get("is_preview") else 0
        latency_rank = 2 if "flash" in normalized_name else 1 if "pro" in normalized_name else 0
        return (
            stable_rank,
            version,
            latency_rank,
            int(model_info.get("output_token_limit", 0) or 0),
            int(model_info.get("input_token_limit", 0) or 0),
            normalized_name,
        )

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
            >>> result = client.send_prompt_with_tools("Find files", tools, model="gemini-2.5-flash")
        """
        if not prompt:
            raise GeminiClientError("Prompt cannot be empty")
        
        if not tools:
            raise GeminiClientError("Tools list cannot be empty")
        
        # Use provided model or fall back to instance default
        model_name = self.resolve_text_model(model)
        
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

        model_name = self.resolve_text_model(model)
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
        major, minor, _ = self._extract_model_version(normalized)
        if major >= 3:
            level_name = os.environ.get("AI_AGENT_DEEP_THINK_LEVEL_GEMINI3", "high")
            level = self._resolve_thinking_level(level_name)
            return types.ThinkingConfig(
                include_thoughts=False,
                thinking_level=level,
            )

        if major == 2 and minor >= 5:
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

        discovered = [
            model["name"]
            for model in self.list_models(force_refresh=force_refresh)
            if model.get("is_image_generation_model")
        ]
        models = sorted(set(discovered))
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
        if normalized_tier not in {"fast", "standard", "ultra"}:
            raise GeminiClientError(
                "quality_tier must be one of: fast, standard, ultra"
            )

        ranked = sorted(
            available,
            key=lambda model_name: self._image_model_sort_key(model_name, normalized_tier),
            reverse=True,
        )
        return ranked[0]

    @classmethod
    def _image_model_sort_key(
        cls,
        model_name: str,
        quality_tier: str,
    ) -> tuple[Any, ...]:
        lowered = model_name.strip().lower()
        version = cls._extract_model_version(lowered)
        stable_rank = 1 if not cls._looks_like_preview_model(lowered) else 0
        native_rank = 1 if lowered.startswith("gemini-") else 0
        if quality_tier == "fast":
            speed_rank = 2 if any(token in lowered for token in ("flash", "lite")) else 1
        elif quality_tier == "ultra":
            speed_rank = 2 if any(token in lowered for token in ("pro", "ultra", "max")) else 1
        else:
            speed_rank = 1
        return (stable_rank, native_rank, version, speed_rank, lowered)

    def generate_image(
        self,
        *,
        prompt: str,
        quality_tier: str = "standard",
        number_of_images: int = 1,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        person_generation: str = "ALLOW_ADULT",
        negative_prompt: str | None = None,
        model_override: str | None = None,
    ) -> Dict[str, Any]:
        """Generate images using Nano Banana (Gemini native image generation).

        Uses ``generate_content()`` with ``response_modalities=['TEXT', 'IMAGE']``
        instead of the legacy Imagen ``generate_images()`` API.

        Args:
            prompt: Detailed image description.
            quality_tier: One of ``fast``, ``standard``, ``ultra``.
            number_of_images: How many images to generate (1-4).
            aspect_ratio: Aspect ratio string (e.g. ``1:1``, ``16:9``).
            image_size: Output size profile (``1K``, ``2K``, ``4K``).
            person_generation: Policy string (``ALLOW_ADULT``, ``ALLOW_ALL``, ``ALLOW_NONE``).
            negative_prompt: Optional text describing what to avoid.
            model_override: Override the auto-resolved model name.

        Returns:
            Dictionary with ``model`` and ``images`` list.
        """
        if not prompt or not prompt.strip():
            raise GeminiClientError("Image prompt cannot be empty")
        if number_of_images < 1 or number_of_images > 4:
            raise GeminiClientError("number_of_images must be between 1 and 4")

        model_name = self.resolve_image_model(
            quality_tier=quality_tier,
            model_override=model_override,
        )

        # Build the text prompt — append negative prompt as avoidance instruction
        full_prompt = prompt.strip()
        if negative_prompt and negative_prompt.strip():
            full_prompt = f"{full_prompt}\n\nAvoid: {negative_prompt.strip()}"

        # Build Nano Banana config using generate_content with image output
        image_config_kwargs: dict[str, Any] = {
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        }
        if person_generation and person_generation.strip():
            image_config_kwargs["person_generation"] = person_generation.strip()

        config = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(**image_config_kwargs),
        )

        all_images: list[dict[str, Any]] = []
        text_responses: list[str] = []

        for image_idx in range(number_of_images):
            last_exception: Optional[Exception] = None
            delay = self.retry_delay

            for attempt in range(self.max_retries + 1):
                try:
                    logger.info(
                        "[MODEL_VERIFICATION] Calling Nano Banana image API with model='%s' (image %d/%d)",
                        model_name, image_idx + 1, number_of_images,
                    )
                    response = self._client.models.generate_content(
                        model=model_name,
                        contents=[full_prompt],
                        config=config,
                    )

                    # Extract images and text from response parts
                    parts = getattr(response, "parts", None) or []
                    found_image = False
                    for part in parts:
                        inline_data = getattr(part, "inline_data", None)
                        if inline_data is not None:
                            mime_type = str(getattr(inline_data, "mime_type", "") or "").strip()
                            if mime_type.startswith("image/"):
                                raw_bytes = getattr(inline_data, "data", None)
                                image_bytes = (
                                    bytes(raw_bytes)
                                    if isinstance(raw_bytes, (bytes, bytearray, memoryview))
                                    else b""
                                )
                                all_images.append({
                                    "bytes": image_bytes,
                                    "mime_type": mime_type,
                                    "width": 0,
                                    "height": 0,
                                })
                                found_image = True

                        text_content = getattr(part, "text", None)
                        if text_content and isinstance(text_content, str) and text_content.strip():
                            text_responses.append(text_content.strip())

                    if not found_image:
                        raise GeminiClientError(
                            "Image generation response contained no image data"
                        )

                    last_exception = None
                    break

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
                except GeminiClientError:
                    raise
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

        return {
            "model": model_name,
            "images": all_images,
            "text_responses": text_responses,
        }
    
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

        # Fallback: extract text from candidates when .text property is unavailable
        if result["text"] is None:
            try:
                candidates = getattr(response, 'candidates', None) or []
                if candidates:
                    content = getattr(candidates[0], 'content', None)
                    if content:
                        parts = getattr(content, 'parts', None) or []
                        text_parts = [
                            getattr(part, 'text', None)
                            for part in parts
                            if getattr(part, 'text', None)
                        ]
                        if text_parts:
                            result["text"] = "".join(text_parts)
                            logger.debug(f"Parsed text from candidates: {len(result['text'])} chars")
            except (ValueError, AttributeError, IndexError):
                pass
        
        if result["text"] is None and result["function_call"] is None:
            logger.warning("Empty response from Gemini API")
        
        return result
