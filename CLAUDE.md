# OtakuNeko - Claude Code Rules

## 📋 Project Overview

**OtakuNeko** is a private anime management assistant built with:
- **Backend**: FastAPI 0.109+ + Python 3.11+ + LangGraph ReAct Agent + SQLModel ORM
- **Frontend**: Next.js 16.1 (App Router) + React 19 + TypeScript + Tailwind CSS + Zustand
- **Database**: Dual-mode (SQLite for local dev / PostgreSQL for production)
- **Cache**: In-memory (local) / Redis (production)
- **AI Engine**: LangGraph ReAct workflow with 7 built-in tools for anime data analysis

**Purpose**: Personal anime collection management, smart scheduling, AI-powered recommendations, and character analysis via Bangumi API integration.

---

## 🏗️ Architecture Rules

### Layered Architecture (Backend)

```
API Layer (Routers) → Service Layer → Repository Layer → Database
```

1. **API Layer** (`backend/app/api/v1/`): 9 routers with ~30 endpoints
   - Each router is a separate file: `collections.py`, `subjects.py`, `bangumi.py`, `agent.py`, etc.
   - All endpoints use async/await
   - Authentication via `get_current_user` dependency
   - Response models use Pydantic schemas from `schemas/`

2. **Service Layer** (`backend/app/services/`): 11 services
   - One service per domain: `collection_service.py`, `bangumi_service.py`, `qb_service.py`, etc.
   - Business logic lives here, not in routers
   - Services are stateless and async

3. **Repository Layer** (`backend/app/repositories/`): 4 repositories
   - `subject_repo.py`, `collection_repo.py`, `user_repo.py`, `schedule_repo.py`
   - Handle database CRUD operations
   - Use SQLModel/SQLAlchemy async patterns

4. **Model Layer** (`backend/app/models/`): SQLModel ORM models
   - `subject.py`, `collection.py`, `user.py`, `schedule.py`
   - Define table schemas with `SQLModel(table=True)`
   - Use enums from `models/enums.py`

5. **Schema Layer** (`backend/app/schemas/`): Pydantic models
   - Separate schemas for request/response validation
   - Keep schemas independent of database models

### Frontend Architecture

```
Pages (App Router) → Components → Services → API Client → Backend
```

1. **Pages** (`frontend/src/app/`): Next.js 16 App Router
   - `page.tsx` - Chat interface
   - `collections/page.tsx` - Collection management
   - `Timetable/page.tsx` - Schedule management
   - `Personal/page.tsx` - AI persona settings
   - Each page is a client component with `"use client"` directive

2. **Components** (`frontend/src/components/`): Organized by feature
   - `chat/` - Chat input, message list, process visualization
   - `collection/` - Grid/list views, media cards
   - `timetable/` - Drag-drop schedule components
   - `Modal/` - Global modals (export, import, login, etc.)
   - `providers/` - Theme and context providers

3. **Services** (`frontend/src/services/`): API client layer
   - One service per domain: `auth.ts`, `collections.ts`, `bangumiService.ts`, etc.
   - Use fetch/axios for HTTP requests
   - Handle SSE streaming for chat

4. **State Management** (`frontend/src/stores/`, `frontend/src/store/`):
   - Zustand for global state: `useChatStore.ts`, `useRoleStore.ts`
   - Local state with React hooks in components

---

## 🔧 Tech Stack Rules

### Backend Dependencies (MUST use)

| Category | Library | Purpose |
|----------|---------|---------|
| Framework | FastAPI 0.109+ | REST API + SSE streaming |
| ORM | SQLModel + SQLAlchemy | Async database models |
| AI Agent | LangGraph 1.0+ | ReAct workflow orchestration |
| LLM | LangChain-OpenAI | Unified LLM interface |
| Database | SQLite (local) / PostgreSQL (cloud) | Dual-mode |
| Cache | fastapi-cache2 | API response caching |
| Auth | python-jose + passlib(bcrypt) | JWT + password hashing |
| HTTP | httpx | Async external API calls |
| Scraper | BeautifulSoup4 + lxml | Bangumi HTML scraping |
| Package Manager | uv | Python dependency management |

### Frontend Dependencies (MUST use)

| Category | Library | Purpose |
|----------|---------|---------|
| Framework | Next.js 16.1 (App Router) | React SSR + API proxy |
| UI | React 19 + @lobehub/ui + antd | Chat-focused UI components |
| State | Zustand 5.0 | Global state management |
| Styling | Tailwind CSS + antd-style | Atomic CSS + theme system |
| Drag-Drop | @dnd-kit 6.3 | Schedule drag interactions |
| HTTP | fetch + axios | API requests + SSE streaming |
| Build | Turbopack + React Compiler | Fast builds |
| Package Manager | pnpm 10.x | Dependency management |

---

## 📁 File Structure Rules

### Backend File Naming

```
backend/app/
├── api/v1/           # API routers (lowercase, plural)
│   ├── collections.py
│   ├── subjects.py
│   ├── bangumi.py
│   └── agent.py
├── services/         # Business logic (lowercase, singular)
│   ├── collection_service.py
│   └── bangumi_service.py
├── repositories/     # Data access (lowercase, plural)
│   ├── subject_repo.py
│   └── collection_repo.py
├── models/           # SQLModel ORM (lowercase, singular)
│   ├── subject.py
│   └── collection.py
├── schemas/          # Pydantic schemas (lowercase, plural)
│   ├── collection.py
│   └── subject.py
└── core/             # Infrastructure
    ├── config.py     # Settings (pydantic-settings)
    ├── security.py   # JWT + auth
    └── logging.py    # Logger setup
```

### Frontend File Naming

```
frontend/src/
├── app/                  # Next.js App Router pages
│   ├── page.tsx          # Chat page (root)
│   ├── layout.tsx        # Root layout (always present)
│   ├── collections/
│   ├── Timetable/
│   └── Personal/
├── components/           # UI components (lowercase, plural)
│   ├── chat/             # Feature-based grouping
│   ├── collection/
│   └── Modal/
├── services/             # API clients (lowercase, plural)
│   ├── auth.ts
│   └── collections.ts
├── stores/               # Zustand stores (lowercase, plural)
│   ├── useChatStore.ts
│   └── useRoleStore.ts
├── lib/                  # Utilities
│   ├── utils.ts          # cn() class name merger
│   └── fetcher.ts        # SSE streaming
└── hooks/                # Custom React hooks
    └── useChatStreaming.ts
```

---

## 🎨 Code Style Rules

### Python (Backend)

1. **Type Hints**: Always use type hints for function parameters and return values
   ```python
   async def get_collection(
       collection_id: int,
       current_user: User = Depends(get_current_user)
   ) -> CollectionRead:
   ```

2. **Docstrings**: Use Google-style docstrings for public functions
   ```python
   async def sync_user_collections(
       username: str,
       token: Optional[str] = None
   ) -> List[CollectionRead]:
       """Sync user collections from Bangumi API.
       
       Args:
           username: Bangumi username
           token: Optional API token for private data
           
       Returns:
           List of synced collections
       """
   ```

3. **Async/Await**: Use async/await for all I/O operations
   ```python
   async def fetch_subject(source_id: str) -> Subject:
       async with httpx.AsyncClient() as client:
           response = await client.get(f"https://api.bgm.tv/subject/{source_id}")
           return response.json()
   ```

4. **Error Handling**: Use HTTPException for API errors
   ```python
   if not collection:
       raise HTTPException(status_code=404, detail="Collection not found")
   ```

5. **Logging**: Use structured logging from `core/logging.py`
   ```python
   from app.core.logging import get_logger
   logger = get_logger(__name__)
   logger.info(f"Syncing collections for user {username}")
   ```

6. **Imports**: Group imports by standard library, third-party, local
   ```python
   from typing import Optional, List
   from datetime import datetime
   
   from fastapi import APIRouter, Depends, HTTPException
   from sqlmodel import select
   
   from app.db.database import get_session
   from app.models.user import User
   ```

### TypeScript/React (Frontend)

1. **TypeScript**: Use strict mode, define interfaces for all props
   ```typescript
   interface ChatInputProps {
     onSend: (text: string, contextItems: SearchResultItem[]) => void;
     loading: boolean;
     selectedModel: string;
   }
   
   export const ChatInput: React.FC<ChatInputProps> = ({
     onSend,
     loading,
     selectedModel
   }) => {
     // Component logic
   };
   ```

2. **Client Components**: Always add `"use client"` directive for interactive components
   ```typescript
   "use client";
   
   import { useState } from 'react';
   ```

3. **Zustand Stores**: Use `use` prefix for store hooks
   ```typescript
   export const useChatStore = create<ChatState>((set) => ({
     messages: [],
     addMessage: (message) => set((state) => ({
       messages: [...state.messages, message]
     }))
   }));
   ```

4. **Styling**: Use Tailwind CSS classes + antd-style for theme tokens
   ```typescript
   const { token } = theme.useToken();
   return (
     <div className="bg-white dark:bg-gray-800 p-4 rounded-lg">
       {/* Content */}
     </div>
   );
   ```

5. **Services**: Keep API calls in services/, use fetch with proper error handling
   ```typescript
   export async function fetchCollections(params: CollectionParams) {
     const response = await fetch(`/api/collections?${new URLSearchParams(params)}`);
     if (!response.ok) throw new Error('Failed to fetch collections');
     return response.json();
   }
   ```

---

## 🗄️ Database Rules

### Dual-Mode Configuration

```python
# backend/app/core/config.py
DEPLOY_MODE: str = "local"  # or "cloud"

# Auto-generates DATABASE_URL based on mode
@computed_field
@property
def DATABASE_URL(self) -> str:
    if self.DEPLOY_MODE == "local":
        return f"sqlite+aiosqlite:///{self.SQLITE_FILE}"
    else:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
```

### Table Naming

- Use singular snake_case: `subject`, `collection`, `user`, `schedule`
- Add `source` and `source_id` fields for multi-source data (Bangumi, Douban)
- Use JSON columns for flexible nested data: `images`, `tags`, `infobox`

### Indexing Rules

- Index foreign keys and frequently queried fields: `user_id`, `source_id`, `type`, `status`
- Add composite indexes for common query patterns
- Use unique constraints for multi-source deduplication: `(source, source_id)`

---

## 🤖 AI Agent Rules

### LangGraph ReAct Workflow

```python
# backend/app/agents/graph.py
graph = StateGraph(AgentState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_executor)
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")
```

### Tool Registration

- Tools are defined in `agents/tools/` directory
- Each tool is a function with `@tool` decorator
- Tools must have clear docstrings for LLM understanding
- Return structured data (dict/list), not raw strings

### Available Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `get_anime_info` | Bangumi API | Query anime details |
| `fetch_audience_reviews` | Bangumi Scraper | Get reviews |
| `get_anime_staff` | Bangumi API | Query production staff |
| `get_anime_cast` | Bangumi API | Query voice actors |
| `search_anime_advanced` | Bangumi API | Advanced search |
| `get_current_time` | Local system | Current datetime |
| `generate_user_profile_tool` | Database + LLM | User profile analysis |

---

## 🔐 Authentication Rules

### JWT Token Flow

1. User registers/logs in via `/api/v1/auth/` endpoints
2. Server validates credentials with bcrypt
3. Returns JWT token with `user_id` and `exp` claims
4. Client stores token in localStorage
5. Subsequent requests include `Authorization: Bearer <token>` header
6. Backend validates via `get_current_user` dependency

### Password Hashing

```python
# backend/app/core/security.py
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
```

---

## 🌐 API Design Rules

### RESTful Conventions

- **GET** `/api/v1/collections/` - List collections (with filters)
- **GET** `/api/v1/collections/{id}` - Get single collection
- **POST** `/api/v1/collections/` - Create collection
- **PUT** `/api/v1/collections/{id}` - Update collection
- **DELETE** `/api/v1/collections/{id}` - Delete collection

### Query Parameters

- Use snake_case: `sort_by`, `limit`, `offset`, `subject_type`
- Provide sensible defaults: `limit=20`, `offset=0`
- Document parameters with `description` in `Query()`

### Response Models

- Use Pydantic schemas from `schemas/` directory
- Return `UnifiedList` for paginated responses
- Include proper HTTP status codes: 200, 201, 404, 422, 500

---

## 🎯 SSE Streaming Rules (Chat)

### Backend Streaming

```python
# backend/app/api/v1/agent.py
from fastapi.responses import StreamingResponse

async def chat_stream(message: str):
    async for event in agent.astream_events({"messages": [("user", message)]}):
        if event["event"] == "on_chat_model_stream":
            yield f"data: {json.dumps({'type': 'token', 'content': event['data']['chunk'].content})}\n\n"
        elif event["event"] == "on_tool_start":
            yield f"data: {json.dumps({'type': 'tool_start', 'tool': event['name']})}\n\n"
    yield "data: [DONE]\n\n"

return StreamingResponse(chat_stream(message), media_type="text/event-stream")
```

### Frontend Consumption

```typescript
// frontend/src/lib/fetcher.ts
const response = await fetch('/api/agent/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const chunk = decoder.decode(value);
  const lines = chunk.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      // Handle token, tool_start, tool_end events
    }
  }
}
```

---

## 🧪 Testing Rules

### Backend (pytest)

- Test files: `tests/` directory
- Use `pytest-asyncio` for async tests
- Mock external APIs (Bangumi, qBittorrent) with `pytest-mock`
- Test fixtures in `conftest.py`

```python
# backend/tests/test_collections.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_collections(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/collections/", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()
```

### Frontend (vitest)

- Test files: `frontend/src/__tests__/` directory
- Use React Testing Library for component tests
- Mock API calls with MSW or jest.mock

```typescript
// frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx
import { render, screen } from '@testing-library/react';
import { AgentMessageRenderer } from '@/components/chat/AgentMessageRenderer';

test('renders message content', () => {
  render(<AgentMessageRenderer content="Hello World" />);
  expect(screen.getByText('Hello World')).toBeInTheDocument();
});
```

---

## 🚀 Deployment Rules

### Docker Compose (5 Services)

```yaml
services:
  db:           # PostgreSQL 15
  redis:        # Redis 7
  backend:      # FastAPI (port 8000)
  frontend:     # Next.js (port 3000)
  qbittorrent:  # BT downloader (port 8080)
```

### Environment Variables

```bash
# Required
DEPLOY_MODE=local|cloud
OPENAI_API_KEY=your-key
JWT_SECRET_KEY=strong-secret

# Local mode
SQLITE_FILE=./local.db

# Cloud mode
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=otakuneko
POSTGRES_PASSWORD=password
POSTGRES_DB=otakuneko
REDIS_URL=redis://localhost:6379/0

# Optional integrations
BANGUMI_TOKEN=your-token
QB_URL=http://localhost:8080
QB_USERNAME=admin
QB_PASSWORD=adminadmin
```

### Startup Commands

```bash
# Local development
start_all.bat  # Windows
./start_all.sh  # macOS/Linux

# Docker deployment
start_docker.bat  # Windows
./start_docker.sh  # macOS/Linux

# Manual start
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && pnpm dev
```

---

## ⚠️ Critical Rules

1. **NEVER commit secrets**: `.env` files, API keys, passwords must be in `.gitignore`
2. **Always use async/await**: Both FastAPI and Next.js support async; don't block the event loop
3. **Use dual-mode config**: Test with SQLite locally, deploy with PostgreSQL in production
4. **Validate with Pydantic**: All API inputs/outputs must use Pydantic schemas
5. **Error handling**: Use try/except for external API calls, HTTPException for API errors
6. **Logging**: Use structured logging from `core/logging.py`, not print statements
7. **Type safety**: Use TypeScript strict mode, Python type hints everywhere
8. **Component organization**: Group components by feature, not by type
9. **Service layer**: Business logic stays in services/, not in routers or components
10. **Database migrations**: Use Alembic for schema changes, never modify tables directly

---

## 📚 Key Documentation

- `docs/backend-architecture-whitepaper.md` - Backend architecture deep-dive
- `docs/frontend-src-research-report.md` - Frontend codebase analysis
- `backend/QUICK_START.md` - Backend setup guide
- `frontend/FRONTEND_DOCUMENTATION.md` - Frontend development guide

---

## 📦 Package Management Rules

### Backend (uv)

```bash
# Install dependencies
uv sync

# Add new dependency
uv add <package>

# Add dev dependency
uv add --dev <package>

# Run commands in venv
uv run python script.py
uv run pytest
uv run uvicorn app.main:app --reload

# Lock file
# IMPORTANT: uv.lock MUST be committed to git
```

### Frontend (pnpm)

```bash
# Install dependencies
pnpm install

# Add dependency
pnpm add <package>

# Add dev dependency
pnpm add -D <package>

# Run scripts
pnpm dev
pnpm build
pnpm test
pnpm lint

# Lock file
# IMPORTANT: pnpm-lock.yaml MUST be committed to git
# NEVER use npm or yarn - only pnpm is allowed
```

---

## 🧠 AI Memory System Rules

### Memory Storage Structure

```
backend/data/memory/
├── short_term/
│   └── {thread_id}.json          # Recent 10 messages
└── long_term/
    └── {thread_id}_facts.json    # BM25 + vector hybrid retrieval
```

### Memory Implementation

- **Short-term memory**: Stores recent conversation context (last 10 messages)
- **Long-term memory**: Uses BM25 + vector embeddings for semantic search
- **Embedding model**: text-embedding-3-small via OpenAI API
- **Storage**: JSON files (not database)
- **Retrieval**: Hybrid approach combining keyword and semantic search

### Memory Manager

```python
# backend/app/memory/manager.py
class MemoryManager:
    async def add_message(self, thread_id: str, message: dict):
        # Add to short-term (append to JSON)
        # Optionally add to long-term (extract facts)
        
    async def retrieve_context(self, thread_id: str, query: str) -> list:
        # Search long-term memory with BM25 + vector
        # Return relevant context for LLM
```

---

## 🚫 Git Ignore Rules (CRITICAL)

### Files That MUST NOT Be Committed

```bash
# Environment & secrets
.env
.env.local
.env.*.local

# Databases
*.sqlite3
*.db
*.db-journal

# Python
__pycache__/
*.pyc
.venv/
venv/

# Node
node_modules/
.next/

# Docker data
data/postgres_data/
data/redis_data/

# Runtime downloads
.runtime/
.node_runtime/

# IDE
.vscode/
.idea/
.trae/

# Logs
logs/
*.log
```

### Files That MUST Be Committed

```bash
# Lock files (CRITICAL)
uv.lock
pnpm-lock.yaml

# Configuration
.env.example
backend/.env.example
docker-compose.yml

# Documentation
docs/**/*.md
README.md
CLAUDE.md
```

---

## ⚙️ Configuration File Locations

| File | Location | Purpose |
|------|----------|---------|
| `.env.example` | Root & backend/ | Environment variable template |
| `pyproject.toml` | backend/ | Python dependencies + tool config |
| `package.json` | frontend/ | Node.js dependencies |
| `docker-compose.yml` | Root | Docker service orchestration |
| `alembic.ini` | backend/ | Database migration config |
| `tsconfig.json` | frontend/ | TypeScript compiler config |
| `tailwind.config.ts` | frontend/ | Tailwind CSS config |
| `.gitignore` | Root | Git ignore rules |
| `CLAUDE.md` | Root | This file (AI assistant rules) |

---

## 🔧 Development Workflow

### Making Changes

1. **Backend changes**:
   - Edit files in `backend/app/`
   - Run `uv run pytest` to test
   - Run `uv run alembic upgrade head` if DB schema changed
   - Restart backend: `uv run uvicorn app.main:app --reload`

2. **Frontend changes**:
   - Edit files in `frontend/src/`
   - Run `pnpm typecheck` for TypeScript validation
   - Run `pnpm test` for unit tests
   - Frontend auto-reloads with Turbopack

3. **Database migrations**:
   - Edit models in `backend/app/models/`
   - Generate migration: `uv run alembic revision --autogenerate -m "description"`
   - Apply migration: `uv run alembic upgrade head`
   - NEVER modify tables directly

4. **Adding new API endpoints**:
   - Create/update router in `backend/app/api/v1/`
   - Add Pydantic schemas in `backend/app/schemas/`
   - Implement business logic in `backend/app/services/`
   - Register router in `backend/app/api/__init__.py`

5. **Adding new frontend features**:
   - Create components in `frontend/src/components/`
   - Create services in `frontend/src/services/`
   - Create Zustand store in `frontend/src/stores/` if needed
   - Create page in `frontend/src/app/` if new route

---

## 📊 Key Metrics & Limits

- **Max file size**: Keep files under 500 lines when possible
- **API response time**: Target < 200ms for non-AI endpoints
- **SSE streaming**: Token-by-token streaming for chat responses
- **Database queries**: Use pagination (limit/offset) for all list endpoints
- **Cache TTL**: 60 seconds default for cached endpoints
- **Max upload size**: 10MB for file uploads
- **Concurrent requests**: FastAPI handles async I/O efficiently

---

*Last updated: 2026-06-24*
*This CLAUDE.md provides rules for AI assistants working with the OtakuNeko codebase. Follow these conventions to maintain consistency and quality.*
