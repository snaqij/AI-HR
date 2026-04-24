"""Role config validator.

JSON Schema validation and business-rule validation for role config files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from jsonschema import Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from .exceptions import ConfigValidationError

logger = logging.getLogger(__name__)


class RoleConfigValidator:
    """Role configuration validator."""
    
    def __init__(self, schema_path: str = None):
        """
        Initialize the validator.
        
        Args:
            schema_path: Path to the JSON Schema file, defaults to the built-in schema
        """
        self.schema = self._load_schema(schema_path)
        self.validator = None
        
        if JSONSCHEMA_AVAILABLE and self.schema:
            self.validator = Draft7Validator(self.schema)
    
    def _load_schema(self, schema_path: str = None) -> Dict:
        """Load the JSON Schema."""
        if schema_path is None:
            # Use the default schema path
            current_dir = Path(__file__).parent.parent.parent
            schema_path = current_dir / "role_configs" / "schema.json"
        
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load schema from {schema_path}: {e}")
            return {}
    
    def validate(self, config: Dict, role_id: str = None) -> Tuple[bool, List[str]]:
        """
        Validate a config.
        
        Args:
            config: Config dict
            role_id: Role ID (used in error messages)
        
        Returns:
            (is_valid, list of errors)
        """
        errors = []
        
        # JSON Schema validation
        schema_errors = self._validate_schema(config)
        errors.extend(schema_errors)
        
        # Business rule validation
        business_errors = self._validate_business_rules(config)
        errors.extend(business_errors)
        
        # Weight validation
        weight_errors = self._validate_weights(config)
        errors.extend(weight_errors)
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            logger.warning(
                "config.validation.failed",
                extra={
                    "role_id": role_id or config.get("role", {}).get("id", "unknown"),
                    "error_count": len(errors),
                    "errors": errors[:5]  # Log only the first 5 errors
                }
            )
        
        return is_valid, errors
    
    def validate_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """
        Validate a config file.
        
        Args:
            file_path: Path to the config file
        
        Returns:
            (is_valid, list of errors)
        """
        try:
            import yaml
            with open(file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            role_id = Path(file_path).stem
            return self.validate(config, role_id)
        
        except Exception as e:
            return False, [f"Failed to load file: {str(e)}"]
    
    def _validate_schema(self, config: Dict) -> List[str]:
        """JSON Schema validation."""
        if not JSONSCHEMA_AVAILABLE:
            logger.debug("jsonschema not available, skipping schema validation")
            return []
        
        if not self.validator:
            return []
        
        errors = []
        for error in self.validator.iter_errors(config):
            path = ".".join(str(p) for p in error.path) if error.path else "root"
            errors.append(f"{path}: {error.message}")
        
        return errors
    
    def _validate_business_rules(self, config: Dict) -> List[str]:
        """Business rule validation."""
        errors = []
        
        # Validate role field
        if "role" not in config:
            errors.append("Missing required field: role")
            return errors
        
        role = config["role"]
        
        # Validate role_id format
        role_id = role.get("id", "")
        if not role_id:
            errors.append("role.id is required")
        elif not role_id.replace("_", "").isalnum():
            errors.append(f"role.id must contain only letters, numbers and underscores: {role_id}")
        
        # Validate display_name
        display_name = role.get("display_name", {})
        if not isinstance(display_name, dict):
            errors.append("role.display_name must be an object")
        elif "zh" not in display_name or "en" not in display_name:
            errors.append("role.display_name must contain both 'zh' and 'en' fields")
        
        # Validate match_rules (if present)
        if "match_rules" in role:
            match_rules = role["match_rules"]
            if "keywords" in match_rules:
                keywords = match_rules["keywords"]
                if not isinstance(keywords, list) or len(keywords) == 0:
                    errors.append("role.match_rules.keywords must be a non-empty array")
        
        return errors

    def _validate_weights(self, config: Dict) -> List[str]:
        """Validate weight sums."""
        errors = []
        
        # Validate universal competency weights sum
        if "universal_competencies" in config:
            total = sum(
                comp.get("weight", 0)
                for comp in config["universal_competencies"].values()
            )
            if abs(total - 1.0) > 0.01:  # Allow 0.01 floating-point tolerance
                errors.append(
                    f"universal_competencies weights must sum to 1.0, got {total:.3f}"
                )
        
        # Validate role competency weights sum
        if "role_competencies" in config:
            total = sum(
                comp.get("weight", 0)
                for comp in config["role_competencies"].values()
            )
            if abs(total - 1.0) > 0.01:
                errors.append(
                    f"role_competencies weights must sum to 1.0, got {total:.3f}"
                )
        
        # Validate stage weights sum
        if "stage_weights" in config:
            total = sum(config["stage_weights"].values())
            if abs(total - 1.0) > 0.01:
                errors.append(
                    f"stage_weights must sum to 1.0, got {total:.3f}"
                )
        
        # Validate question distribution weights sum
        if "question_generation" in config:
            qg = config["question_generation"]
            if "distribution" in qg:
                dist = qg["distribution"]
                total = sum([
                    dist.get("from_resume", 0),
                    dist.get("from_jd", 0),
                    dist.get("from_template", 0)
                ])
                if abs(total - 1.0) > 0.01:
                    errors.append(
                        f"question_generation.distribution weights must sum to 1.0, got {total:.3f}"
                    )
        
        return errors
    
    def raise_if_invalid(self, config: Dict, role_id: str = None, file_path: str = None):
        """
        Validate a config and raise an exception if invalid.
        
        Args:
            config: Config dict
            role_id: Role ID
            file_path: File path (used in error messages)
        
        Raises:
            ConfigValidationError: Config validation failed
        """
        is_valid, errors = self.validate(config, role_id)
        if not is_valid:
            raise ConfigValidationError(
                role_id or config.get("role", {}).get("id", "unknown"),
                errors,
                file_path
            )
