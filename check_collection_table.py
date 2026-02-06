import sys
import os

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

from sqlmodel import SQLModel
from app.models import Collection

print('Collection表结构:')
print(Collection.__table__)
print('\n主键列:')
for col in Collection.__table__.primary_key.columns:
    print(f'- {col.name}')
print('\n所有列:')
for col in Collection.__table__.columns:
    print(f'- {col.name}: {col.type}')
print('\n表参数:')
print(Collection.__table_args__)
