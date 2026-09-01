"""Public configuration error types."""

from __future__ import annotations


class ConfigError(Exception):
    """Base class for all configuration module errors."""

    code: str = "CFG_ERROR"


class ConfigLoadError(ConfigError):
    """Configuration source missing, unreadable, or unparseable."""

    code = "CFG_LOAD"


class ConfigValidationError(ConfigError):
    """Base class for configuration validation failures."""

    code = "CFG_VALIDATION"


class ConfigMissingError(ConfigValidationError):
    """Required configuration key is absent."""

    code = "CFG_MISSING"

    def __init__(self, message: str, *, key_path: str) -> None:
        super().__init__(message)
        self.key_path = key_path


class ConfigFormatError(ConfigValidationError):
    """Configuration value has wrong type or unparsable format."""

    code = "CFG_FORMAT"

    def __init__(self, message: str, *, key_path: str) -> None:
        super().__init__(message)
        self.key_path = key_path


class ConfigValueError(ConfigValidationError):
    """Configuration value violates semantic constraints."""

    code = "CFG_VALUE"

    def __init__(self, message: str, *, key_path: str) -> None:
        super().__init__(message)
        self.key_path = key_path


class ConfigSecretDetectedError(ConfigValidationError):
    """Inline secret detected in configuration source."""

    code = "CFG_SECRET"

    def __init__(self, message: str, *, key_path: str) -> None:
        super().__init__(message)
        self.key_path = key_path


class ConfigCredentialMissingError(ConfigValidationError):
    """Required credential environment variable is unset or empty."""

    code = "CFG_CREDENTIAL"

    def __init__(self, message: str, *, env_var_name: str) -> None:
        super().__init__(message)
        self.env_var_name = env_var_name


class ConfigPromptNotFoundError(ConfigValidationError):
    """Referenced prompt file does not exist."""

    code = "CFG_PROMPT"

    def __init__(self, message: str, *, prompt_file: str) -> None:
        super().__init__(message)
        self.prompt_file = prompt_file
