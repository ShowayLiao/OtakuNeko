# 测试vector_store修复效果
from src.vector_store import LocalVectorStore
from src.database import DatabaseManager

# 测试1: 检查数据库连接
print("测试1: 检查数据库连接")
db_manager = DatabaseManager()
records = db_manager.load_records('unknown')
print(f"数据库中有 {len(records)} 条记录")
if records:
    print(f"第一条记录的键名: {list(records[0].keys())}")

# 测试2: 检查LocalVectorStore._fetch_data_from_db方法
print("\n测试2: 检查LocalVectorStore._fetch_data_from_db方法")
vs = LocalVectorStore(username='unknown')
candidates = vs._fetch_data_from_db()
print(f"从数据库获取了 {len(candidates)} 条记录")
if candidates:
    print(f"第一条候选记录的键名: {list(candidates[0].keys())}")
    print(f"bangumi_id: {candidates[0]['bangumi_id']}")
    print(f"title: {candidates[0]['title']}")

# 测试3: 测试build_index方法
print("\n测试3: 测试build_index方法")
result = vs.build_index()
print(f"构建索引结果: {result}")
