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

### 3.1 模式选择

系统支持两种部署模式，通过 `.env` 文件中的 `DEPLOY_MODE` 变量切换：

- **local**：本地模式，使用 SQLite 数据库和内存缓存，无需额外服务
- **cloud**：云模式，使用 PostgreSQL 数据库和 Redis 缓存，适合生产环境

### 3.2 创建 .env 文件

在 `backend` 目录下创建 `.env` 文件，根据你的部署模式选择以下配置：

#### 本地模式配置 (推荐用于开发测试)

```env
# ==============================
# 模式开关
# local = 本地模式 (用 SQLite, 无 Redis)
# cloud = 生产/容器模式 (用 Postgres + Redis)
# ==============================
DEPLOY_MODE=local

# ==============================
# 基础配置
# ==============================
PROJECT_NAME=OtakuNeko
API_V1_STR=/api/v1
DEBUG=true
# 这里的 Key 保持您原本测试用的即可
OPENAI_API_KEY=test-secret-key-for-jwt-debugging

# ==============================
# 模式 A: Local 配置
# ==============================
SQLITE_FILE=./test.db
```

#### 云模式配置 (推荐用于生产环境)

```env
# ==============================
# 模式开关
# local = 本地模式 (用 SQLite, 无 Redis)
# cloud = 生产/容器模式 (用 Postgres + Redis)
# ==============================
DEPLOY_MODE=cloud

# ==============================
# 基础配置
# ==============================
PROJECT_NAME=OtakuNeko
API_V1_STR=/api/v1
DEBUG=false
# 生产环境请使用真实的 API Key
OPENAI_API_KEY=your-real-openai-api-key

# ==============================
# 模式 B: Cloud 配置
# ==============================
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=otaku
POSTGRES_PASSWORD=password
POSTGRES_DB=otakuneko

# 云端模式下的 Redis
REDIS_URL=redis://localhost:6379/0
```

### 3.3 配置说明

| 环境变量 | 说明 | 默认值 | 适用模式 |
|---------|------|--------|----------|
| DEPLOY_MODE | 部署模式 (local/cloud) | local | 通用 |
| DEBUG | 调试模式 | True | 通用 |
| PROJECT_NAME | 项目名称 | OtakuNeko | 通用 |
| API_V1_STR | API 版本前缀 | /api/v1 | 通用 |
| SQLITE_FILE | SQLite 数据库文件路径 | ./test.db | 仅本地模式 |
| POSTGRES_SERVER | PostgreSQL 服务器地址 | localhost | 仅云模式 |
| POSTGRES_PORT | PostgreSQL 端口 | 5432 | 仅云模式 |
| POSTGRES_USER | PostgreSQL 用户名 | otaku | 仅云模式 |
| POSTGRES_PASSWORD | PostgreSQL 密码 | password | 仅云模式 |
| POSTGRES_DB | PostgreSQL 数据库名 | otakuneko | 仅云模式 |
| REDIS_URL | Redis 连接字符串 | redis://localhost:6379/0 | 仅云模式 |
| OPENAI_API_KEY | OpenAI API 密钥 | - | 通用 |

## 4. 数据库初始化

### 4.1 本地模式 (SQLite)

**无需手动创建数据库**，系统会自动创建 SQLite 文件并初始化表结构。

直接启动服务即可：

```bash
uvicorn app.main:app --reload
```

### 4.2 云模式 (PostgreSQL)

1. **创建 PostgreSQL 数据库**：
   ```bash
   createdb otakuneko
   ```

2. **启动服务**（系统会自动初始化表结构）：
   ```bash
   uvicorn app.main:app --reload
   ```

### 4.3 快速配置指南

#### 本地模式快速启动

1. 确保 `.env` 文件中设置了 `DEPLOY_MODE=local`
2. 安装依赖：`pip install -r requirements.txt`
3. 启动服务：`uvicorn app.main:app --reload`
4. 访问：`http://localhost:8000`

**特点**：无需额外服务，一键启动，适合开发测试

#### 云模式快速启动

1. 确保 `.env` 文件中设置了 `DEPLOY_MODE=cloud`
2. 安装依赖：`pip install -r requirements.txt`
3. 启动 PostgreSQL 和 Redis 服务（使用 Docker Compose）：
   ```bash
   # 在项目根目录执行
   docker compose up -d
   ```
4. 启动应用：`uvicorn app.main:app --reload`
5. 访问：`http://localhost:8000`

**特点**：适合生产环境，性能更好，支持更多功能

## 5. 启动服务

### 5.1 本地模式

```bash
# 开发模式
uvicorn app.main:app --reload

# 生产模式 (本地)
gunicorn app.main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### 5.2 云模式

```bash
# 开发模式
uvicorn app.main:app --reload

# 生产模式 (云)
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

### 7.1 本地模式问题

**问题**：`Database connection error: unable to open database file`

**解决方案**：
1. 确保应用有写入权限到当前目录
2. 检查 `.env` 文件中的 `SQLITE_FILE` 路径是否正确
3. 确保磁盘有足够空间

### 7.2 云模式问题

**问题**：`Database connection error: could not connect to server: Connection refused`

**解决方案**：
1. 确保 PostgreSQL 服务正在运行
2. 检查 `.env` 文件中的 PostgreSQL 配置是否正确
3. 确保数据库用户名和密码正确
4. 确保数据库 `otakuneko` 已创建

**问题**：`Failed to initialize Redis cache: Connection refused`

**解决方案**：
1. 确保 Redis 服务正在运行
2. 检查 `.env` 文件中的 `REDIS_URL` 配置是否正确
3. 注意：即使 Redis 连接失败，系统也会自动降级到内存缓存，服务仍会正常运行

### 7.3 模式切换问题

**问题**：切换模式后服务无法启动

**解决方案**：
1. 确保 `.env` 文件中的 `DEPLOY_MODE` 值正确（`local` 或 `cloud`）
2. 本地模式：确保没有设置 PostgreSQL 相关配置
3. 云模式：确保 PostgreSQL 相关配置完整
4. 重启服务

### 7.4 依赖安装错误

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

### 9.1 本地模式部署

**适合场景**：个人开发、测试、小型应用

**配置建议**：
- 可以保持 `DEBUG=True` 方便开发
- 无需额外服务配置
- 适合直接在本地机器上运行
- 可通过 `systemd` 或 `pm2` 管理进程

### 9.2 云模式部署

**适合场景**：生产环境、团队协作、大型应用

**配置建议**：
- 设置 `DEBUG=False`
- 配置强密码的 JWT 密钥
- 配置 HTTPS
- 建议使用容器化部署

### 9.3 容器化部署 (云模式)

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
      POSTGRES_USER: otaku
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

### 9.4 快速切换指南

**从本地模式切换到云模式**：
1. 修改 `.env` 文件：`DEPLOY_MODE=cloud`
2. 配置 PostgreSQL 和 Redis 相关参数
3. 启动 PostgreSQL 和 Redis 服务
4. 重启应用

**从云模式切换到本地模式**：
1. 修改 `.env` 文件：`DEPLOY_MODE=local`
2. 无需启动额外服务
3. 重启应用

## 10. 联系与支持

- 项目地址：https://github.com/your-repo/otakuneko
- 文档地址：https://your-docs-site.com
- 问题反馈：https://github.com/your-repo/otakuneko/issues

---

**文档版本**: v2.0.0  
**最后更新**: 2026-01-26  
**维护者**: OtakuNeko Team