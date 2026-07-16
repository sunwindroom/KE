from fastapi import HTTPException


class BusinessException(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class AuthenticationException(BusinessException):
    def __init__(self, message: str = "未认证或Token已失效"):
        super().__init__(code=40100, message=message)


class PermissionDeniedException(BusinessException):
    def __init__(self, message: str = "无权限访问"):
        super().__init__(code=40300, message=message)


class ResourceNotFoundException(BusinessException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=40400, message=message)


class ConflictException(BusinessException):
    def __init__(self, message: str = "资源冲突"):
        super().__init__(code=40900, message=message)


class RateLimitException(BusinessException):
    def __init__(self, message: str = "请求频率超限"):
        super().__init__(code=42900, message=message)


class ServiceUnavailableException(BusinessException):
    def __init__(self, message: str = "依赖服务不可用"):
        super().__init__(code=50300, message=message)


class EmptyResultException(BusinessException):
    def __init__(self, message: str = "检索结果为空，无法生成可靠回答"):
        super().__init__(code=50301, message=message)


def raise_not_found(resource: str = "资源"):
    raise HTTPException(status_code=404, detail=f"{resource}不存在")


def raise_forbidden(action: str = "此操作"):
    raise HTTPException(status_code=403, detail=f"无权限执行{action}")