# API 文档

本文档详细说明 OtakuNeko 后端 API 的定义规则和规范，确保开发人员能够清晰理解并正确遵循 API 的定义规范。

## 目录结构

```
api/
├── __init__.py          # 主 API 路由配置
├── deps.py             # 依赖注入函数
└── v1/                 # v1 版本 API
    ├── __init__.py     # v1 路由配置
    ├── auth.py         # 认证相关接口
    ├── bangumi.py      # Bangumi 相关接口
    ├── collections.py  # 收藏相关接口
    ├── dashboard.py    # 仪表盘相关接口
    ├── users.py        # 用户相关接口
    ├── agent.py        # 代理相关接口
    ├── rss.py          # RSS 相关接口
    └── endpoints/      # 其他端点
        └── schedules.py # 日程相关接口
```

## API 命名规范

### 路由命名
- 使用小写字母和连字符（-）分隔单词
- 采用 RESTful 风格，使用资源名称作为路由路径
- 版本号使用 v1、v2 等前缀

### 模块命名
- 每个功能模块对应一个 Python 文件
- 文件名使用小写字母和下划线（_）分隔单词
- 模块名应清晰反映其功能

### 函数命名
- 使用小写字母和下划线（_）分隔单词
- 采用动词+名词的命名方式（如 `get_user`, `create_post`）
- 端点函数以 `endpoint` 结尾（如 `get_bangumi_user_endpoint`）

## 请求方法使用原则

| 方法 | 用途 | 示例 |
|------|------|------|
| GET | 获取资源 | `/api/v1/bangumi/calendar` |
| POST | 创建资源 | `/api/v1/auth/login` |
| PUT | 更新资源 | `/api/v1/users/{id}` |
| DELETE | 删除资源 | `/api/v1/collections/{id}` |

## 参数类型及格式要求

### 路径参数
- 使用大括号 `{}` 定义路径参数
- 路径参数应在函数参数中明确类型
- 示例：`@router.get("/user/{username}")`

### 查询参数
- 使用函数参数定义查询参数
- 可使用 Pydantic 模型进行复杂查询参数验证
- 示例：`@router.get("/items")` 接收 `skip` 和 `limit` 参数

### 请求体参数
- 使用 Pydantic 模型定义请求体结构
- 模型应继承自 `BaseModel`
- 示例：`class LoginRequest(BaseModel):`

### 依赖注入参数
- 使用 `Depends()` 标记依赖注入参数
- 常见依赖：数据库会话、当前用户认证
- 示例：`db: AsyncSession = Depends(get_session)`

## 响应数据结构标准

### 成功响应
- 使用 `response_model` 装饰器指定响应模型
- 响应模型应继承自 `BaseModel`
- 示例：`@router.get("/user/{username}", response_model=BangumiUserInfo)`

### 错误响应
- 使用 `HTTPException` 抛出错误
- 错误应包含适当的状态码和详细信息
- 示例：`raise HTTPException(status_code=500, detail="获取 Bangumi 用户信息失败")`

## 错误处理机制

### 异常类型
- `400 Bad Request`：请求参数错误
- `401 Unauthorized`：未授权访问
- `403 Forbidden`：禁止访问
- `404 Not Found`：资源不存在
- `500 Internal Server Error`：服务器内部错误

### 错误处理模式
```python
try:
    # 业务逻辑
    result = await some_service()
    return result
except Exception as e:
    import traceback
    print(f"[操作名称] 错误: {str(e)}")
    print(traceback.format_exc())
    raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")
```

## 认证授权方式

### JWT 认证
- 使用 `HTTPBearer` 进行 token 验证
- token 包含用户 ID 和用户名信息
- 认证失败返回 401 错误

### 依赖注入
```python
from app.api.deps import get_current_user

@router.get("/protected", response_model=UserRead)
async def protected_route(current_user: UserRead = Depends(get_current_user)):
    # 需要认证的接口
    return current_user
```

## 代码规范

### 文档字符串
- 每个端点函数必须包含详细的文档字符串
- 文档字符串应包含：
  - 接口功能描述
  - 参数说明（Args）
  - 返回值说明（Returns）
  - 异常说明（Raises）

### 代码风格
- 使用 4 个空格进行缩进
- 变量和函数命名使用 snake_case
- 类名使用 PascalCase
- 导入语句按标准库、第三方库、本地模块的顺序排列

## 示例代码

### 基本端点示例
```python
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.example import ExampleResponse

router = APIRouter(prefix="/example", tags=["Example"])

@router.get("/items/{item_id}", response_model=ExampleResponse)
async def get_item(item_id: int):
    """
    获取示例项目
    
    Args:
        item_id: 项目 ID
        
    Returns:
        示例项目信息
        
    Raises:
        HTTPException: 当项目不存在时返回 404 错误
    """
    try:
        # 业务逻辑
        item = await get_item_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="项目不存在")
        return item
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[获取示例项目] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取项目失败: {str(e)}")
```

### 带认证的端点示例
```python
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])

@router.put("/me", response_model=UserRead)
async def update_current_user(
    user_update: UserUpdate,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    更新当前用户信息
    
    Args:
        user_update: 用户更新信息
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        更新后的用户信息
        
    Raises:
        HTTPException: 当更新失败时返回 500 错误
    """
    try:
        # 业务逻辑
        updated_user = await update_user(db, current_user.id, user_update)
        return updated_user
    except Exception as e:
        import traceback
        print(f"[更新用户信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"更新用户信息失败: {str(e)}")
```

## 最佳实践

1. **保持接口简洁**：每个接口应只负责一个功能
2. **使用 Pydantic 模型**：统一请求和响应的数据结构
3. **完善错误处理**：捕获并处理所有可能的异常
4. **详细的文档**：为每个接口编写清晰的文档字符串
5. **遵循 RESTful 规范**：使用适当的 HTTP 方法和状态码
6. **合理的路由设计**：组织良好的路由结构便于维护
7. **使用依赖注入**：分离业务逻辑和请求处理
8. **统一的响应格式**：保持 API 响应格式的一致性

## 版本控制

API 版本控制通过 URL 路径中的版本前缀实现（如 `/api/v1/`）。当 API 发生不兼容变更时，应创建新的版本目录（如 `v2/`）。

## 测试建议

- 为每个 API 端点编写单元测试
- 测试应覆盖正常流程和错误场景
- 使用 FastAPI 的测试客户端进行测试
- 测试数据库操作时使用测试数据库

## 部署注意事项

- 生产环境应启用 HTTPS
- 配置适当的 CORS 策略
- 设置合理的请求大小限制
- 实现适当的速率限制防止滥用
- 监控 API 性能和错误率

---

**注意**：本文档应随 API 的变更及时更新，确保开发人员能够获取最新的 API 规范信息。