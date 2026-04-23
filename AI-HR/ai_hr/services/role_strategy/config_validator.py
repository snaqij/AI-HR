"""
岗位配置验证器

提供配置文件的JSON Schema验证和业务规则验证功能。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

try:
    import jsonschema
    from jsonschema import Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from .exceptions import ConfigValidationError

logger = logging.getLogger(__name__)


class RoleConfigValidator:
    """岗位配置验证器"""
    
    def __init__(self, schema_path: str = None):
        """
        初始化验证器
        
        Args:
            schema_path: JSON Schema文件路径，默认使用内置schema
        """
        self.schema = self._load_schema(schema_path)
        self.validator = None
        
        if JSONSCHEMA_AVAILABLE and self.schema:
            self.validator = Draft7Validator(self.schema)
    
    def _load_schema(self, schema_path: str = None) -> Dict:
        """加载JSON Schema"""
        if schema_path is None:
            # 使用默认schema路径
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
        验证配置
        
        Args:
            config: 配置字典
            role_id: 岗位ID（用于错误消息）
        
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        # JSON Schema验证
        schema_errors = self._validate_schema(config)
        errors.extend(schema_errors)
        
        # 业务规则验证
        business_errors = self._validate_business_rules(config)
        errors.extend(business_errors)
        
        # 权重验证
        weight_errors = self._validate_weights(config)
        errors.extend(weight_errors)
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            logger.warning(
                "config.validation.failed",
                extra={
                    "role_id": role_id or config.get("role", {}).get("id", "unknown"),
                    "error_count": len(errors),
                    "errors": errors[:5]  # 只记录前5个错误
                }
            )
        
        return is_valid, errors
    
    def validate_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """
        验证配置文件
        
        Args:
            file_path: 配置文件路径
        
        Returns:
            (是否有效, 错误列表)
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
        """JSON Schema验证"""
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
        """业务规则验证"""
        errors = []
        
        # 验证role字段
        if "role" not in config:
            errors.append("Missing required field: role")
            return errors
        
        role = config["role"]
        
        # 验证role_id格式
        role_id = role.get("id", "")
        if not role_id:
            errors.append("role.id is required")
        elif not role_id.replace("_", "").isalnum():
            errors.append(f"role.id must contain only letters, numbers and underscores: {role_id}")
        
        # 验证display_name
        display_name = role.get("display_name", {})
        if not isinstance(display_name, dict):
            errors.append("role.display_name must be an object")
        elif "zh" not in display_name or "en" not in display_name:
            errors.append("role.display_name must contain both 'zh' and 'en' fields")
        
        # 验证match_rules（如果存在）
        if "match_rules" in role:
            match_rules = role["match_rules"]
            if "keywords" in match_rules:
                keywords = match_rules["keywords"]
                if not isinstance(keywords, list) or len(keywords) == 0:
                    errors.append("role.match_rules.keywords must be a non-empty array")
        
        return errors

    def _validate_weights(self, config: Dict) -> List[str]:
        """验证权重总和"""
        errors = []
        
        # 验证通用能力权重总和
        if "universal_competencies" in config:
            total = sum(
                comp.get("weight", 0)
                for comp in config["universal_competencies"].values()
            )
            if abs(total - 1.0) > 0.01:  # 允许0.01的浮点误差
                errors.append(
                    f"universal_competencies weights must sum to 1.0, got {total:.3f}"
                )
        
        # 验证岗位能力权重总和
        if "role_competencies" in config:
            total = sum(
                comp.get("weight", 0)
                for comp in config["role_competencies"].values()
            )
            if abs(total - 1.0) > 0.01:
                errors.append(
                    f"role_competencies weights must sum to 1.0, got {total:.3f}"
                )
        
        # 验证阶段权重总和
        if "stage_weights" in config:
            total = sum(config["stage_weights"].values())
            if abs(total - 1.0) > 0.01:
                errors.append(
                    f"stage_weights must sum to 1.0, got {total:.3f}"
                )
        
        # 验证题目分布权重总和
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
        验证配置，如果无效则抛出异常
        
        Args:
            config: 配置字典
            role_id: 岗位ID
            file_path: 文件路径（用于错误消息）
        
        Raises:
            ConfigValidationError: 配置验证失败
        """
        is_valid, errors = self.validate(config, role_id)
        if not is_valid:
            raise ConfigValidationError(
                role_id or config.get("role", {}).get("id", "unknown"),
                errors,
                file_path
            )
