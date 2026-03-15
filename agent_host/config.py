"""Configuration management for the AI Agent.

This module provides configuration loading and validation for the agent host.
Configuration values are loaded from environment variables with sensible defaults
for optional fields.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


def _get_project_root() -> Path:
    """Get the project root directory.
    
    Returns:
        Path to the project root (parent of agent_host directory).
    """
    return Path(__file__).parent.parent


def _default_schemas_dir() -> Path:
    """Get the default schemas directory path.
    
    Returns:
        Path to the schemas directory in the project root.
    """
    return _get_project_root() / "schemas"


def _default_audit_log_path() -> Path:
    """Get the default audit log path.
    
    Returns:
        Path to the audit log file in user's local data directory.
    """
    return Path.home() / ".local" / "share" / "ai-agent" / "audit.log"


def _default_memory_root() -> Path:
    """Get the default secure memory root directory."""
    return Path.home() / "Library" / "Application Support" / "AIAgent" / "memory"


def _default_image_output_root() -> Path:
    """Get the default root directory for generated images."""
    return _default_memory_root() / "generated_images"


def _default_allowed_roots() -> list[Path]:
    """Get default filesystem roots for tool execution.

    Uses the root filesystem (Macintosh HD) so search covers the entire
    computer.  Noisy/system paths are filtered by _path_has_noisy_components
    and _path_is_excluded rather than by restricting roots.
    """
    return [Path("/")]


def _default_automations_dir() -> Path:
    """Get default allowlisted automation script directory."""
    return _get_project_root() / "automations"


def _parse_bool_env(value: Optional[str], *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"Invalid boolean value: {value}")


@dataclass
class Config:
    """Configuration settings for the AI Agent.
    
    This dataclass holds all configuration values needed by the agent,
    including API credentials, model settings, file paths, and retry behavior.
    
    Attributes:
        gemini_api_key: Google API key for Gemini (required).
        model_name: Gemini model to use for inference. When empty, the backend
            resolves the best currently available text model dynamically.
        schemas_dir: Directory containing JSON tool schemas.
        audit_log_path: Path to the JSONL audit log file.
        max_retries: Maximum number of retry attempts for API calls.
        retry_delay: Initial delay in seconds between retries.
        memory_root: Root directory for encrypted session memory.
        image_output_root: Root directory for generated image files.
        allowed_roots: Filesystem roots where tools are allowed to operate.
        automations_dir: Directory containing allowlisted automation scripts.
        enable_open_item: Whether the open_item tool can launch macOS apps.
        audit_include_prompt: Whether raw prompts are persisted in audit logs.
        search_scan_limit: Maximum filesystem entries scanned by search_files.
        image_model_override: Optional explicit image model name override.
        image_timeout_seconds: Timeout budget for image generation calls.
        require_no_training: Fail closed unless backend mode can enforce no-training policy.
        use_vertexai: Use Vertex AI backend instead of API-key Gemini Developer API.
        vertex_project: GCP project id for Vertex AI requests.
        vertex_location: GCP location/region for Vertex AI requests.
    """
    
    gemini_api_key: str
    model_name: str = ""
    schemas_dir: Path = field(default_factory=_default_schemas_dir)
    audit_log_path: Path = field(default_factory=_default_audit_log_path)
    max_retries: int = 3
    retry_delay: float = 1.0
    memory_root: Path = field(default_factory=_default_memory_root)
    image_output_root: Path = field(default_factory=_default_image_output_root)
    allowed_roots: list[Path] = field(default_factory=_default_allowed_roots)
    automations_dir: Path = field(default_factory=_default_automations_dir)
    enable_open_item: bool = False
    audit_include_prompt: bool = False
    search_scan_limit: int = 20000
    image_model_override: Optional[str] = None
    image_timeout_seconds: float = 180.0
    require_no_training: bool = False
    use_vertexai: bool = False
    vertex_project: Optional[str] = None
    vertex_location: str = "us-central1"
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization.
        
        Raises:
            ConfigurationError: If required configuration values are invalid.
        """
        if not self.gemini_api_key:
            raise ConfigurationError("gemini_api_key cannot be empty")
        
        if self.max_retries < 0:
            raise ConfigurationError("max_retries must be non-negative")
        
        if self.retry_delay < 0:
            raise ConfigurationError("retry_delay must be non-negative")
        if self.search_scan_limit < 100:
            raise ConfigurationError("search_scan_limit must be >= 100")
        if self.image_timeout_seconds <= 0:
            raise ConfigurationError("image_timeout_seconds must be > 0")
        if self.use_vertexai and (not self.vertex_project or not self.vertex_project.strip()):
            raise ConfigurationError(
                "vertex_project is required when use_vertexai is enabled"
            )
        
        # Ensure paths are Path objects
        if isinstance(self.schemas_dir, str):
            self.schemas_dir = Path(self.schemas_dir)
        if isinstance(self.audit_log_path, str):
            self.audit_log_path = Path(self.audit_log_path)
        if isinstance(self.memory_root, str):
            self.memory_root = Path(self.memory_root)
        if isinstance(self.image_output_root, str):
            self.image_output_root = Path(self.image_output_root)
        if isinstance(self.automations_dir, str):
            self.automations_dir = Path(self.automations_dir)
        normalized_roots: list[Path] = []
        for root in self.allowed_roots:
            normalized_roots.append(Path(root) if isinstance(root, str) else root)
        self.allowed_roots = normalized_roots
    
    @classmethod
    def from_env(
        cls,
        env_prefix: str = "",
        api_key_var: str = "GOOGLE_API_KEY"
    ) -> "Config":
        """Create a Config instance from environment variables.
        
        Loads configuration from environment variables. API key mode and
        Vertex AI mode are both supported.
        
        Args:
            env_prefix: Optional prefix for all environment variable names.
            api_key_var: Name of the environment variable containing the API key.
        
        Returns:
            A Config instance with values loaded from the environment.
        
        Raises:
            ConfigurationError: If required credentials/settings are missing.
        
        Example:
            >>> config = Config.from_env()
            >>> config.model_name
            ''
        """
        use_vertexai = _parse_bool_env(
            os.environ.get(f"{env_prefix}AI_AGENT_USE_VERTEXAI"),
            default=False,
        )

        # Load API key for Developer API mode (optional in Vertex mode).
        api_key = os.environ.get(api_key_var)
        if not use_vertexai and not api_key:
            raise ConfigurationError(
                f"Required environment variable {api_key_var} is not set. "
                "Please set your Google API key or enable Vertex AI mode."
            )
        if use_vertexai and not api_key:
            # Keep field non-empty for dataclass validation while credentials
            # are expected from ADC / gcloud in Vertex mode.
            api_key = "vertexai-managed-auth"
        
        # Load optional configuration values
        model_name = os.environ.get(
            f"{env_prefix}AI_AGENT_MODEL_NAME",
            ""
        )
        
        schemas_dir_str = os.environ.get(f"{env_prefix}AI_AGENT_SCHEMAS_DIR")
        schemas_dir = Path(schemas_dir_str) if schemas_dir_str else _default_schemas_dir()
        
        audit_log_str = os.environ.get(f"{env_prefix}AI_AGENT_AUDIT_LOG_PATH")
        audit_log_path = Path(audit_log_str) if audit_log_str else _default_audit_log_path()

        memory_root_str = os.environ.get(f"{env_prefix}AI_AGENT_MEMORY_ROOT")
        memory_root = Path(memory_root_str) if memory_root_str else _default_memory_root()

        image_output_root_str = os.environ.get(f"{env_prefix}AI_AGENT_IMAGE_OUTPUT_ROOT")
        image_output_root = (
            Path(image_output_root_str).expanduser()
            if image_output_root_str
            else _default_image_output_root()
        )

        allowed_roots_str = os.environ.get(f"{env_prefix}AI_AGENT_ALLOWED_ROOTS")
        if allowed_roots_str:
            raw_parts = [part.strip() for part in allowed_roots_str.split(",") if part.strip()]
            allowed_roots = [Path(part).expanduser() for part in raw_parts]
        else:
            allowed_roots = _default_allowed_roots()

        automations_dir_str = os.environ.get(f"{env_prefix}AI_AGENT_AUTOMATIONS_DIR")
        automations_dir = (
            Path(automations_dir_str).expanduser()
            if automations_dir_str
            else _default_automations_dir()
        )

        enable_open_item = _parse_bool_env(
            os.environ.get(f"{env_prefix}AI_AGENT_ENABLE_OPEN_ITEM"),
            default=False,
        )

        audit_include_prompt = _parse_bool_env(
            os.environ.get(f"{env_prefix}AI_AGENT_AUDIT_INCLUDE_PROMPT"),
            default=False,
        )

        search_scan_limit_str = os.environ.get(f"{env_prefix}AI_AGENT_SEARCH_SCAN_LIMIT")
        if search_scan_limit_str:
            try:
                search_scan_limit = int(search_scan_limit_str)
            except ValueError as e:
                raise ConfigurationError(
                    f"{env_prefix}AI_AGENT_SEARCH_SCAN_LIMIT must be an integer"
                ) from e
        else:
            search_scan_limit = 20000

        image_model_override = os.environ.get(f"{env_prefix}AI_AGENT_IMAGE_MODEL")
        if image_model_override is not None:
            image_model_override = image_model_override.strip() or None

        image_timeout_seconds_str = os.environ.get(f"{env_prefix}AI_AGENT_IMAGE_TIMEOUT_SECONDS")
        if image_timeout_seconds_str:
            try:
                image_timeout_seconds = float(image_timeout_seconds_str)
            except ValueError as e:
                raise ConfigurationError(
                    f"{env_prefix}AI_AGENT_IMAGE_TIMEOUT_SECONDS must be a number"
                ) from e
        else:
            image_timeout_seconds = 180.0

        require_no_training = _parse_bool_env(
            os.environ.get(f"{env_prefix}AI_AGENT_REQUIRE_NO_TRAINING"),
            default=False,
        )

        vertex_project = (
            os.environ.get(f"{env_prefix}AI_AGENT_VERTEX_PROJECT")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
        if vertex_project is not None:
            vertex_project = vertex_project.strip() or None

        vertex_location = (
            os.environ.get(f"{env_prefix}AI_AGENT_VERTEX_LOCATION")
            or os.environ.get("GOOGLE_CLOUD_LOCATION")
            or "us-central1"
        ).strip() or "us-central1"
        
        max_retries_str = os.environ.get(f"{env_prefix}AI_AGENT_MAX_RETRIES")
        if max_retries_str:
            try:
                max_retries = int(max_retries_str)
            except ValueError as e:
                raise ConfigurationError(
                    f"{env_prefix}AI_AGENT_MAX_RETRIES must be an integer"
                ) from e
        else:
            max_retries = 3
        
        retry_delay_str = os.environ.get(f"{env_prefix}AI_AGENT_RETRY_DELAY")
        if retry_delay_str:
            try:
                retry_delay = float(retry_delay_str)
            except ValueError as e:
                raise ConfigurationError(
                    f"{env_prefix}AI_AGENT_RETRY_DELAY must be a number"
                ) from e
        else:
            retry_delay = 1.0
        
        return cls(
            gemini_api_key=api_key or "",
            model_name=model_name,
            schemas_dir=schemas_dir,
            audit_log_path=audit_log_path,
            max_retries=max_retries,
            retry_delay=retry_delay,
            memory_root=memory_root,
            image_output_root=image_output_root,
            allowed_roots=allowed_roots,
            automations_dir=automations_dir,
            enable_open_item=enable_open_item,
            audit_include_prompt=audit_include_prompt,
            search_scan_limit=search_scan_limit,
            image_model_override=image_model_override,
            image_timeout_seconds=image_timeout_seconds,
            require_no_training=require_no_training,
            use_vertexai=use_vertexai,
            vertex_project=vertex_project,
            vertex_location=vertex_location,
        )
    
    def validate_schemas_dir(self) -> bool:
        """Check if the schemas directory exists and contains JSON files.
        
        Returns:
            True if the schemas directory exists and contains .json files.
        """
        if not self.schemas_dir.exists():
            return False
        if not self.schemas_dir.is_dir():
            return False
        return any(self.schemas_dir.glob("*.json"))
