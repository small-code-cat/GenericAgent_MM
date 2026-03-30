# 远程开发 SOP

## 调用模板
```python
import sys
sys.path.insert(0, '/Users/xuekejun/CursorProjects/GenericAgent_MM/memory/remote_develop')
from remote_dev import connect
r = connect('ssh1')  # ssh_config.py中的配置名
```

## API
| 方法 | 说明 | 示例 |
|------|------|------|
| `r.exec(cmd)` | 执行命令→(stdout,stderr,code) | `r.exec('python train.py')` |
| `r.read(path, keyword=)` | 读文件，可选关键字定位 | `r.read('config.yaml')` |
| `r.write(path, content, mode=)` | 写文件(overwrite/append) | `r.write('a.py', code)` |
| `r.patch(path, old, new)` | 精准替换文件片段 | `r.patch('a.py', 'v1', 'v2')` |
| `r.ls(path)` | 列目录 | `r.ls('demo/')` |
| `r.search(kw, path, file_pattern)` | grep搜索 | `r.search('import', '.', '*.py')` |
| `r.close()` | 关闭连接 | 用完必须close |

## 注意
- path支持相对路径（基于project_path）和绝对路径
- patch要求old_content在文件中唯一
- exec默认timeout=30s，长任务需加大：`r.exec(cmd, timeout=300)`
- 每次code_run结束后连接会断开，下次需重新connect