import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas.adapters import convert_douban_to_bangumi


json_file_path = "tofu[208745052].json"
target_index = 150

try:
    with open(json_file_path, 'r', encoding='utf-8') as f:
        input_json = json.load(f)
except FileNotFoundError:
    print(f"错误: 找不到文件 {json_file_path}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"错误: JSON 格式不正确 - {e}")
    sys.exit(1)

# 执行转换
result = convert_douban_to_bangumi(input_json, target_index)

# Print 结果 (ensure_ascii=False 用于正确显示中文)
print(json.dumps(result, indent=4, ensure_ascii=False))