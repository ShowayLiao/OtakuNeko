import os

def print_tree(startpath, exclude_dirs=None):
    if exclude_dirs is None:
        exclude_dirs = []
        
    for root, dirs, files in os.walk(startpath):
        # --- 核心修改：原地过滤掉不需要的文件夹 ---
        # 必须使用切片 [:] 修改，才能影响 os.walk 的后续遍历
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = '│   ' * (level - 1) + '├── ' if level > 0 else ''
        
        print(f'{indent}{os.path.basename(root)}/')
        
        subindent = '│   ' * (level) + '├── '
        for f in files:
            print(f'{subindent}{f}')

if __name__ == '__main__':
    # 在这里定义你想排除的文件夹名字
    ignore_list = ['venv', '.git', '__pycache__', '.idea', '.vscode']
    
    # 打印当前文件夹
    print_tree('.', ignore_list)