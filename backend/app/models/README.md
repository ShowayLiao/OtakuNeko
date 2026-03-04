# 数据库模型结构说明

本项目使用 SQLModel 作为 ORM 框架，基于 SQLAlchemy 构建，支持自动生成数据库表结构和类型提示。模型文件组织结构如下：

- `__init__.py` - 模型导出文件，定义了所有可导出的模型类
- `collection.py` - 用户收藏模型
- `subject.py` - 通用条目模型
- `user.py` - 用户模型
- `schedule.py` - 番剧排班模型
- `broadcast_metadata.py` - 番剧放送元数据模型
- `enums.py` - 枚举类型定义