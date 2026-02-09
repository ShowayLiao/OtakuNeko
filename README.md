# OtakuNeko 项目配置指南

## 项目简介

OtakuNeko 是一个动漫爱好者的收藏管理系统，包含后端 API 和前端界面，支持动漫收藏的管理、同步和统计分析。

## 技术栈

- **后端**: FastAPI (Python)
- **前端**: Next.js (React)
- **数据库**: SQLite (本地模式) / PostgreSQL (云模式)
- **缓存**: 内存缓存 (本地模式) / Redis (云模式)

## 一、后端配置

### 1. 环境要求
- Python 3.9+
- PostgreSQL 13+ (可选，云模式需要)
- Redis 6+ (可选，云模式需要)

### 2. 配置步骤

#### 步骤1：进入后端目录
```bash
cd backend
```

#### 步骤2：创建虚拟环境
```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (Windows)
venv\Scripts\activate

# 激活虚拟环境 (macOS/Linux)
# . venv/bin/activate
```

#### 步骤3：安装依赖
```bash
pip install -r requirements.txt
```

#### 步骤4：配置环境变量
在 `backend` 目录下创建 `.env` 文件，根据部署模式选择配置：

**本地模式配置（推荐开发测试）**：
```env
# 模式开关
DEPLOY_MODE=local

# 基础配置
PROJECT_NAME=OtakuNeko
API_V1_STR=/api/v1
DEBUG=true
OPENAI_API_KEY=test-secret-key-for-jwt-debugging

# 本地模式配置
SQLITE_FILE=./test.db
```

**云模式配置（推荐生产环境）**：
```env
# 模式开关
DEPLOY_MODE=cloud

# 基础配置
PROJECT_NAME=OtakuNeko
API_V1_STR=/api/v1
DEBUG=false
OPENAI_API_KEY=your-real-openai-api-key

# 云模式配置
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=otaku
POSTGRES_PASSWORD=password
POSTGRES_DB=otakuneko

# Redis配置
REDIS_URL=redis://localhost:6379/0
```

#### 步骤5：启动服务
```bash
# 开发模式
uvicorn app.main:app --reload

# 生产模式
# gunicorn app.main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

#### 步骤6：访问服务
- 应用主页：http://localhost:8000
- API文档：http://localhost:8000/docs (Swagger UI)
- 健康检查：http://localhost:8000/health

## 二、前端配置

### 1. 环境要求
- Node.js 18+
- npm, yarn, pnpm 或 bun

### 2. 配置步骤

#### 步骤1：进入前端目录
```bash
cd frontend
```

#### 步骤2：安装依赖
```bash
npm install
# 或
# yarn install
# 或
# pnpm install
# 或
# bun install
```

#### 步骤3：启动开发服务器
```bash
npm run dev
# 或
# yarn dev
# 或
# pnpm dev
# 或
# bun dev
```

#### 步骤4：访问前端
- 前端地址：http://localhost:3000

## 三、部署模式说明

### 本地模式 (local)
- 使用 SQLite 数据库（无需额外安装）
- 使用内存缓存（无需 Redis）
- 适合开发测试和个人使用
- 配置简单，一键启动

### 云模式 (cloud)
- 使用 PostgreSQL 数据库
- 使用 Redis 缓存
- 适合生产环境和团队协作
- 性能更好，支持更多功能

## 四、快速启动指南

### 本地模式快速启动
1. 在 `backend` 目录创建 `.env` 文件，设置 `DEPLOY_MODE=local`
2. 安装后端依赖：`pip install -r requirements.txt`
3. 启动后端服务：`uvicorn app.main:app --reload`
4. 安装前端依赖：`npm install`
5. 启动前端服务：`npm run dev`
6. 访问前端：http://localhost:3000

### 云模式快速启动
1. 在 `backend` 目录创建 `.env` 文件，设置 `DEPLOY_MODE=cloud`
2. 安装后端依赖：`pip install -r requirements.txt`
3. 启动 PostgreSQL 和 Redis 服务（可使用 Docker Compose）
4. 启动后端服务：`uvicorn app.main:app --reload`
5. 安装前端依赖：`npm install`
6. 启动前端服务：`npm run dev`
7. 访问前端：http://localhost:3000

## 五、常见问题解决方案

1. **本地模式数据库错误**：确保应用有写入权限，检查 `.env` 文件中的 `SQLITE_FILE` 路径
2. **云模式数据库连接错误**：确保 PostgreSQL 服务正在运行，检查配置是否正确
3. **Redis 连接错误**：确保 Redis 服务正在运行，检查 `REDIS_URL` 配置
4. **端口被占用**：尝试使用其他端口启动服务，例如 `uvicorn app.main:app --reload --port 8001`
5. **依赖安装错误**：确保 Python 版本符合要求，尝试更新 pip 后重新安装

## 六、项目结构说明

- **backend/**: 后端代码（FastAPI）
  - **app/**: 应用代码
  - **requirements.txt**: 依赖文件
  - **.env.example**: 环境变量示例
  - **QUICK_START.md**: 详细配置指南

- **frontend/**: 前端代码（Next.js）
  - **src/**: 源代码
  - **package.json**: 依赖配置
  - **README.md**: 前端说明文档

- **tests/**: 测试代码

## 七、API 测试

### 获取 JWT 令牌
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser"}'
```

### 使用令牌访问受保护的 API
```bash
# 替换 <token> 为上一步获取的 JWT 令牌
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

### 获取用户统计数据
```bash
curl -X GET http://localhost:8000/api/v1/dashboard/stats \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

---

**文档版本**: v1.0.0  
**最后更新**: 2026-02-09  
**维护者**: OtakuNeko Team