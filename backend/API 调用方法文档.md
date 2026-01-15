# API调用方法文档

## 1. 文档概述

本文档详细描述了OtakuNeko后端服务的所有API端点，包括请求方法、参数格式、响应结构、认证要求等。开发者可以通过本文档了解如何调用各个API端点，实现与OtakuNeko后端的交互。

## 2. 认证机制

### 2.1 JWT认证

OtakuNeko采用JWT（JSON Web Token）进行身份认证，所有需要认证的API端点都要求在请求头中携带有效的JWT令牌。

#### 2.1.1 认证流程

1. **获取令牌**：通过`POST /auth/login`接口获取JWT令牌
2. **使用令牌**：在后续请求的`Authorization`头中添加`Bearer <token>`，例如：
   ```
   Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

#### 2.1.2 令牌有效期

- JWT令牌有效期为7天
- 令牌过期后需要重新获取

## 3. API端点列表

| 分类 | 路径 | 方法 | 功能描述 | 认证要求 |
|------|------|------|----------|----------|
| 认证 | `/api/v1/auth/login` | POST | 用户登录/注册/信息更新 | 无需认证 |
| 收藏 | `/api/v1/collections` | GET | 获取用户收藏列表 | 需要JWT |
| 收藏 | `/api/v1/collections/{sid}` | PUT | 更新或添加收藏 | 需要JWT |
| 收藏 | `/api/v1/collections/sync` | POST | 同步收藏（支持BGM和豆瓣） | 需要JWT |
| 仪表板 | `/api/v1/dashboard/stats` | GET | 获取用户统计数据 | 需要JWT |
| 条目 | `/api/v1/subjects` | GET | 搜索条目 | 需要JWT |
| 条目 | `/api/v1/subjects/{subject_id}` | GET | 获取单个条目详情 | 需要JWT |
| 条目 | `/api/v1/subjects/{subject_id}` | PUT | 修改条目信息 | 需要JWT |
| 用户 | `/api/v1/users/me` | GET | 获取当前用户信息 | 需要JWT |

## 4. API详细说明

### 4.1 认证相关API

#### 4.1.1 用户登录/注册/信息更新

**路径**：`/api/v1/auth/login`

**方法**：`POST`

**功能**：集用户注册、登录及信息更新功能于一体的综合入口。
- 如果用户名不存在：自动创建新用户，使用请求中的可选字段（如果提供），否则使用默认值
- 如果用户名已存在：选择性更新非空且变更的字段
- 所有场景下统一返回有效的JWT令牌和用户信息

**请求体**：

```json
{
  "username": "string", // 用户名，1-50个字符，必填
  "nickname": "string", // 用户昵称，可选，最大100字符
  "bangumi_id": 12345, // 第三方平台ID，可选，整数类型
  "avatar_url": "string", // 头像图片URL，可选，最大255字符
  "sign": "string" // 用户签名/个性签名，可选，最大200字符
}
```

**响应**：

```json
{
  "access_token": "string", // JWT访问令牌
  "token_type": "bearer", // 令牌类型，固定为"bearer"
  "user": {
    "id": 1, // 用户ID
    "username": "string", // 用户名
    "nickname": "string", // 用户昵称
    "email": null, // 邮箱
    "avatar_url": "string", // 头像URL
    "bangumi_id": 12345, // 第三方平台ID
    "sign": "string", // 用户签名
    "created_at": "2023-12-30T10:00:00" // 创建时间
  }
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 操作成功 |
| 400 | 请求参数错误 |
| 500 | 服务器内部错误 |

**示例请求1：新用户注册**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "nickname": "Test User", "bangumi_id": 12345, "avatar_url": "http://example.com/avatar.jpg", "sign": "Hello World!"}'
```

**示例响应1**：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbWUiOiJ0ZXN0dXNlciIsImV4cCI6MTcwMjM0Nzg5NH0.SAMPLE_TOKEN",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "testuser",
    "nickname": "Test User",
    "email": null,
    "avatar_url": "http://example.com/avatar.jpg",
    "bangumi_id": 12345,
    "sign": "Hello World!",
    "created_at": "2023-12-30T10:00:00"
  }
}
```

**示例请求2：现有用户登录**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser"}'
```

**示例响应2**：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbWUiOiJ0ZXN0dXNlciIsImV4cCI6MTcwMjM0Nzg5NH0.SAMPLE_TOKEN",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "testuser",
    "nickname": "Test User",
    "email": null,
    "avatar_url": "http://example.com/avatar.jpg",
    "bangumi_id": 12345,
    "sign": "Hello World!",
    "created_at": "2023-12-30T10:00:00"
  }
}
```

**示例请求3：现有用户信息更新**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "nickname": "Updated Nickname", "sign": "Updated Sign"}'
```

**示例响应3**：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbWUiOiJ0ZXN0dXNlciIsImV4cCI6MTcwMjM0Nzg5NH0.SAMPLE_TOKEN",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "testuser",
    "nickname": "Updated Nickname",
    "email": null,
    "avatar_url": "http://example.com/avatar.jpg",
    "bangumi_id": 12345,
    "sign": "Updated Sign",
    "created_at": "2023-12-30T10:00:00"
  }
}
```

### 4.2 收藏相关API

#### 4.2.1 获取用户收藏列表

**路径**：`/api/v1/collections`

**方法**：`GET`

**功能**：获取用户的收藏列表，支持多种筛选和排序方式。

**查询参数**：

| 参数名 | 类型 | 可选值 | 默认值 | 描述 |
|--------|------|--------|--------|------|
| subject_type | int | 1, 2, 3, 4, 6 | 无 | 条目类型（1=书籍/2=动画/3=音乐/4=游戏/6=三次元） |
| status | int | 1, 2, 3, 4, 5 | 无 | 收藏状态（1=想看/2=看过/3=在看/4=搁置/5=抛弃） |
| keyword | string | - | 无 | 搜索关键词 |
| limit | int | 1-100 | 20 | 分页大小 |
| offset | int | ≥0 | 0 | 分页偏移 |
| sort_by | string | updated_at, rate, score, rank, date | updated_at | 排序字段 |

**响应**：

```json
{
  "total": 100, // 总记录数
  "items": [
    {
      "subject_id": 12345,
      "updated_at": "2023-12-30T10:00:00",
      "status": 2,
      "rate": 9,
      "comment": "很好看的动画",
      "private": false,
      "tags": ["动画", "热血"],
      "subject": {
        "id": 12345,
        "name": "测试动画",
        "name_cn": "测试动画中文名",
        "type": 2,
        "score": 9.5,
        "rank": 10,
        "date": "2023-01-01",
        "cover_url": "https://example.com/cover.jpg",
        "eps": 12,
        "volumes": null,
        "collection_total": 10000,
        "tags": ["动画", "热血"],
        "meta_tags": [],
        "infobox": [],
        "rating_details": {},
        "images": {}
      }
    }
  ]
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 获取成功 |
| 401 | 未认证或认证失败 |
| 500 | 服务器内部错误 |

**示例请求**：

```bash
curl -X GET "http://localhost:8000/api/v1/collections?subject_type=2&limit=10&offset=0" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

#### 4.2.2 更新或添加收藏

**路径**：`/api/v1/collections/{sid}`

**方法**：`PUT`

**功能**：更新现有收藏或添加新收藏。

**路径参数**：

| 参数名 | 类型 | 描述 |
|--------|------|------|
| sid | int | 条目ID |

**请求体**：

```json
{
  "collection": {
    "status": 2, // 收藏状态（1=想看/2=看过/3=在看/4=搁置/5=抛弃）
    "rate": 9, // 评分（0-10，0表示未评分）
    "comment": "很好看的动画", // 评论
    "private": false, // 是否私有
    "tags": ["动画", "热血"] // 标签列表
  },
  "subject": {
    "name": "测试动画",
    "name_cn": "测试动画中文名",
    "type": 2, // 条目类型（1=书籍/2=动画/3=音乐/4=游戏/6=三次元）
    "cover_url": "https://example.com/cover.jpg",
    "release_date": "2023-01-01",
    "publish_date": "2023-01-01",
    "status": 2, // 收藏状态（仅用于创建新收藏）
    "rate": 9, // 评分（仅用于创建新收藏）
    "comment": "很好看的动画", // 评论（仅用于创建新收藏）
    "tags": ["动画", "热血"] // 标签列表
  }
}
```

**响应**：

```json
{
  "subject_id": 12345,
  "updated_at": "2023-12-30T10:00:00",
  "status": 2,
  "rate": 9,
  "comment": "很好看的动画",
  "private": false,
  "tags": ["动画", "热血"],
  "subject": null
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 更新/添加成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或认证失败 |
| 404 | 收藏记录不存在 |
| 500 | 服务器内部错误 |

**示例请求**：

```bash
curl -X PUT http://localhost:8000/api/v1/collections/12345 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"collection": {"status": 2, "rate": 9, "comment": "很好看的动画"}}'
```

#### 4.2.3 同步收藏

**路径**：`/api/v1/collections/sync`

**方法**：`POST`

**功能**：从BGM或豆瓣同步用户收藏到本地数据库。

**请求体**：

```json
{
  "source": "bgm", // 数据源（bgm或douban）
  "subject_type": 2, // 可选，条目类型（1=书籍/2=动画/3=音乐/4=游戏/6=三次元）
  "data": [] // 豆瓣数据列表（仅当source=douban时需要）
}
```

**响应**：

```json
{
  "message": "Successfully synced 100 collections for user testuser",
  "username": "testuser",
  "sync_count": 100,
  "subject_type": 2,
  "source": "bgm"
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 同步成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或认证失败 |
| 404 | 用户不存在 |
| 500 | 服务器内部错误 |

**示例请求**：

```bash
curl -X POST http://localhost:8000/api/v1/collections/sync \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "bgm", "subject_type": 2}'
```

### 4.3 仪表板相关API

#### 4.3.1 获取用户统计数据

**路径**：`/api/v1/dashboard/stats`

**方法**：`GET`

**功能**：获取用户在不同分类下的收藏统计数据。

**响应**：

```json
{
  "anime": 50, // 动画收藏数量
  "book": 20, // 书籍收藏数量
  "game": 10, // 游戏收藏数量
  "music": 15, // 音乐收藏数量
  "real": 5 // 三次元收藏数量
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 获取成功 |
| 401 | 未认证或认证失败 |
| 500 | 服务器内部错误 |

**示例请求**：

```bash
curl -X GET http://localhost:8000/api/v1/dashboard/stats \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

### 4.4 条目相关API

#### 4.4.1 搜索条目

**路径**：`/api/v1/subjects`

**方法**：`GET`

**功能**：搜索条目，支持本地、远程和混合三种搜索模式。

**查询参数**：

| 参数名 | 类型 | 可选值 | 默认值 | 描述 |
|--------|------|--------|--------|------|
| q | string | - | 无 | 搜索关键词 |
| source | string | local, remote, mixed | mixed | 搜索来源（local=仅本地, remote=仅远程, mixed=混合） |
| type | int | 1, 2, 3, 4, 6 | 无 | 条目类型（1=书籍/2=动画/3=音乐/4=游戏/6=三次元） |
| limit | int | 1-100 | 20 | 返回结果数量 |
| offset | int | ≥0 | 0 | 结果偏移量 |
| sort | string | rank, score, date | rank | 排序方式（仅remote模式有效） |

**响应**：

```json
[
  {
    "name": "四月は君の嘘",
    "name_cn": "四月是你的谎言",
    "cover_url": "https://lain.bgm.tv/pic/cover/l/ec/c7/100444_96r3J.jpg",
    "type": 2,
    "eps": 22,
    "volumes": 0,
    "platform": "",
    "summary": "　　有马公生的母亲一心想把有马培育成举世闻名的钢琴家，而有马也不负母亲的期望，在念小学时就赢得许多钢琴比赛的大奖。11岁的秋天，有马的母亲过世，从此他再也听不见自己弹奏的钢琴声，沮丧的他也只好放弃演奏，但在14岁那年，经由儿时玩伴的介绍，有",
    "tags": [
      "恋爱",
      "音乐",
      "A-1Pictures",
      "治愈",
      "青春",
      "催泪",
      "四月は君の嘘",
      "2014年10月",
      "漫画改",
      "TV"
    ],
    "date": "2014-10-09",
    "id": 302,
    "source_id": "100444",
    "score": 8,
    "rank": 241,
    "is_collected": false,
    "is_favorited": false,
    "collection_info": null
  }
]
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 搜索成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或认证失败 |
| 500 | 服务器内部错误 |
| 504 | 远程API超时 |

**示例请求**：

```bash
curl -X GET "http://localhost:8000/api/v1/subjects?q=测试&source=mixed&type=2&limit=10" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

#### 4.4.2 获取单个条目详情

**路径**：`/api/v1/subjects/{subject_id}`

**方法**：`GET`

**功能**：获取单个条目的详细信息，支持从远程刷新数据。

**路径参数**：

| 参数名 | 类型 | 描述 |
|--------|------|------|
| subject_id | int | 条目ID |

**查询参数**：

| 参数名 | 类型 | 默认值 | 描述 |
|--------|------|--------|------|
| refresh | bool | false | 是否从远程刷新数据 |

**响应**：

```json
{
  "id": 12345,
  "name": "测试动画",
  "name_cn": "测试动画中文名",
  "type": 2,
  "score": 9.5,
  "rank": 10,
  "date": "2023-01-01",
  "cover_url": "https://example.com/cover.jpg",
  "eps": 12,
  "volumes": null,
  "collection_total": 10000,
  "tags": ["动画", "热血"],
  "meta_tags": [],
  "infobox": [],
  "rating_details": {},
  "images": {}
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 获取成功 |
| 401 | 未认证或认证失败 |
| 404 | 条目不存在 |
| 500 | 服务器内部错误 |
| 504 | 远程API超时 |

**示例请求**：

```bash
curl -X GET "http://localhost:8000/api/v1/subjects/12345?refresh=true" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

#### 4.4.3 修改条目信息

**路径**：`/api/v1/subjects/{subject_id}`

**方法**：`PUT`

**功能**：修改条目信息（用于错误修正）。

**路径参数**：

| 参数名 | 类型 | 描述 |
|--------|------|------|
| subject_id | int | 条目ID |

**请求体**：

```json
{
  "name": "修改后的动画名",
  "name_cn": "修改后的动画中文名",
  "score": 9.0,
  "rank": 5,
  "date": "2023-02-01",
  "cover_url": "https://example.com/new_cover.jpg"
}
```

**响应**：

```json
{
  "id": 12345,
  "name": "修改后的动画名",
  "name_cn": "修改后的动画中文名",
  "type": 2,
  "score": 9.0,
  "rank": 5,
  "date": "2023-02-01",
  "cover_url": "https://example.com/new_cover.jpg",
  "eps": 12,
  "volumes": null,
  "collection_total": 10000,
  "tags": ["动画", "热血"],
  "meta_tags": [],
  "infobox": [],
  "rating_details": {},
  "images": {}
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 修改成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或认证失败 |
| 404 | 条目不存在 |
| 500 | 服务器内部错误 |

**示例请求**：

```bash
curl -X PUT http://localhost:8000/api/v1/subjects/12345 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "修改后的动画名", "score": 9.0}'
```

### 4.5 用户相关API

#### 4.5.1 获取当前用户信息

**路径**：`/api/v1/users/me`

**方法**：`GET`

**功能**：获取当前登录用户的详细信息。

**响应**：

```json
{
  "id": 1,
  "username": "testuser",
  "nickname": "testuser",
  "email": null,
  "avatar_url": null,
  "bangumi_id": null,
  "sign": "本地用户",
  "created_at": "2023-12-30T10:00:00"
}
```

**状态码**：

| 状态码 | 描述 |
|--------|------|
| 200 | 获取成功 |
| 401 | 未认证或认证失败 |
| 500 | 服务器内部错误 |

**示例请求**：

```bash
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

## 5. 全局状态码说明

| 状态码 | 描述 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或认证失败 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 504 | 远程API超时 |

## 6. 错误处理

当API请求失败时，服务器会返回包含错误信息的JSON响应，例如：

```json
{
  "detail": "Failed to sync collections: Network error"
}
```

### 6.1 常见错误类型

| 错误类型 | 描述 |
|----------|------|
| Network error | 网络连接错误 |
| Bangumi API error | Bangumi API调用失败 |
| Data validation failed | 数据验证失败 |
| Failed to clear cache | 清除缓存失败 |
| Failed to upsert collection | 更新或添加收藏失败 |

## 7. 缓存机制

- **收藏列表**：缓存60秒
- **用户统计数据**：缓存10分钟（600秒）
- **搜索结果**：缓存60秒
- **条目详情**：不缓存

当数据发生变化时，相关缓存会自动清除，确保数据一致性。