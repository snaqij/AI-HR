"""领域与基础设施异常定义。"""

from __future__ import annotations


class AIHRException(Exception):
    """服务侧基础异常类型。"""


class ResourceNotFoundError(AIHRException):
    """资源不存在时抛出。"""


class InvalidStateError(AIHRException):
    """资源状态不满足执行条件时抛出。"""


class ConnectorNotFoundError(AIHRException):
    """连接器未注册时抛出。"""


class InvalidConnectorConfigError(AIHRException):
    """连接器配置不完整时抛出。"""


class ConnectorOperationError(AIHRException):
    """连接器执行动作失败时抛出。"""


class CredentialsExpiredError(ConnectorOperationError):
    """连接器凭据（如Cookie）已过期或无效时抛出。"""
