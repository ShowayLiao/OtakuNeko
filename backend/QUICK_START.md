# OtakuNeko 后端快速配置指南

## 1. 环境要求

### 1.1 基础环境

- Python 3.9+
- PostgreSQL 13+ (推荐)
- Redis 6+ (可选，但建议使用)

### 1.2 开发工具

- Git
- 代码编辑器 (VS Code, PyCharm 等)
- 终端/命令行工具

## 2. 安装步骤

### 2.1 克隆代码库

```bash
git clone https://github.com/your-repo/otakuneko.git
cd otakuneko/backend
```

### 2.2 创建虚拟环境

```bash
# 使用 venv 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
env\Scripts\activate
# macOS/Linux
. venv/bin/activate
```

### 2.3 安装依赖

```bash
pip install -r requirements.txt
```

## 3. 配置环境变量

### 3.1 创建 .env 文件

在 `backend` 目录下创建 `.env` 文件，根据你的环境配置以下内容：

```env
# 应用配置
DEBUG=True
PROJECT_NAME=OtakuNeko
API_V1_STR=/api/v1

# 数据库配置
# PostgreSQL 连接字符串 (推荐)
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/otakuneko
# 或 SQLite 连接字符串 (仅用于开发测试)
# DATABASE_URL=sqlite+aiosqlite:///./otakuneko.db

# Redis 配置 (可选)
REDIS_URL=redis://localhost:6379/0

# AI/Agent 配置 (可选)
OPENAI_API_KEY=your-openai-api-key
```

### 3.2 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| DEBUG | 调试模式 | True |
| PROJECT_NAME | 项目名称 | OtakuNeko |
| API_V1_STR | API 版本前缀 | /api/v1 |
| DATABASE_URL | 数据库连接字符串 | - |
| REDIS_URL | Redis 连接字符串 | redis://localhost:6379/0 |
| OPENAI_API_KEY | OpenAI API 密钥 | - |

## 4. 数据库初始化

### 4.1 初始化 PostgreSQL 数据库 (推荐)

1. 创建数据库：
   ```bash
   createdb otakuneko
   ```

2. 初始化数据库表结构：
   ```bash
   python -m app.db.database
   ```

### 4.2 初始化 SQLite 数据库 (仅用于开发测试)

直接运行数据库初始化脚本：

```bash
python -m app.db.database
```

## 5. 启动服务

### 5.1 开发模式

```bash
uvicorn app.main:app --reload
```

### 5.2 生产模式

```bash
# 使用 Gunicorn + Uvicorn
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### 5.3 服务访问

服务启动后，可以通过以下地址访问：

- 应用主页：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs` (Swagger UI)
- 健康检查：`http://localhost:8000/health`

## 6. 测试 API 访问

### 6.1 获取 JWT 令牌

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser"}'
```

### 6.2 使用令牌访问受保护的 API

```bash
# 替换 <token> 为上一步获取的 JWT 令牌
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

### 6.3 获取用户统计数据

```bash
curl -X GET http://localhost:8000/api/v1/dashboard/stats \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

## 7. 常见问题与解决方案

### 7.1 数据库连接错误

**问题**：`Database connection error: could not connect to server: Connection refused`

**解决方案**：
1. 确保 PostgreSQL 服务正在运行
2. 检查 `.env` 文件中的 `DATABASE_URL` 配置是否正确
3. 确保数据库用户名和密码正确
4. 确保数据库 `otakuneko` 已创建

### 7.2 Redis 连接错误

**问题**：`Failed to initialize Redis cache: Connection refused`

**解决方案**：
1. 确保 Redis 服务正在运行
2. 检查 `.env` 文件中的 `REDIS_URL` 配置是否正确
3. 或注释掉 `REDIS_URL` 配置，应用将自动使用内存缓存作为降级方案

### 7.3 依赖安装错误

**问题**：`ERROR: Could not find a version that satisfies the requirement XYZ`

**解决方案**：
1. 确保 Python 版本符合要求 (3.9+)
2. 尝试更新 pip：`pip install --upgrade pip`
3. 尝试使用 `--no-cache-dir` 选项重新安装：`pip install -r requirements.txt --no-cache-dir`

### 7.4 端口被占用

**问题**：`Error: [Errno 48] Address already in use`

**解决方案**：
1. 检查是否有其他进程占用了 8000 端口
2. 尝试使用其他端口启动服务：`uvicorn app.main:app --reload --port 8001`

## 8. 开发流程

### 8.1 代码风格

- 遵循 PEP 8 规范
- 使用类型注解
- 函数和类使用 docstring 文档

### 8.2 运行测试

```bash
# 运行单元测试
python -m pytest

# 运行测试并生成覆盖率报告
python -m pytest --cov=app
```

### 8.3 代码检查

```bash
# 使用 flake8 检查代码风格
flake8 app

# 使用 mypy 检查类型注解
mypy app
```

## 9. 部署建议

### 9.1 生产环境配置

- 设置 `DEBUG=False`
- 使用 PostgreSQL 数据库
- 配置 Redis 缓存
- 设置强密码的 JWT 密钥
- 配置 HTTPS

### 9.2 容器化部署

使用 Docker 和 Docker Compose 部署：

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    env_file:
      - .env

  db:
    image: postgres:14
    environment:
      POSTGRES_USER: username
      POSTGRES_PASSWORD: password
      POSTGRES_DB: otakuneko
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

## 10. 联系与支持

- 项目地址：https://github.com/your-repo/otakuneko
- 文档地址：https://your-docs-site.com
- 问题反馈：https://github.com/your-repo/otakuneko/issues

---

**文档版本**: v2.0.0  
**最后更新**: 2026-01-26  
**维护者**: OtakuNeko Team