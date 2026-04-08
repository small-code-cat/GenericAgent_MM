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
| `r.exec(cmd, timeout=30, cwd=None)` | 执行命令→(stdout,stderr,code)，可指定工作目录 | `r.exec('python train.py', cwd='/opt/proj')` |
| `r.read(path, keyword=, start=, count=200, context=, match_index=1)` | 读文件，可选关键字定位或按行范围读取(start从1开始)。context:keyword上下文行数(int或(before,after)元组,默认前5后15); match_index:第几个匹配(0=返回所有匹配摘要) | `r.read('a.py', keyword='def main', context=30, match_index=2)` |
| `r.write(path, content, mode=)` | 写文件(overwrite/append) | `r.write('a.py', code)` |
| `r.patch(path, old, new)` | 精准替换文件片段(old须唯一) | `r.patch('a.py', 'v1', 'v2')` |
| `r.replace_lines(path, start, end, new)` | 按行号范围替换(含start和end行) | `r.replace_lines('a.py', 37, 100, new_code)` |
| `r.upload(local, remote)` | 上传本地文件到远程 | `r.upload('./prompt.txt', '/tmp/prompt.txt')` |
| `r.download(remote, local)` | 下载远程文件到本地 | `r.download('model.pt', './model.pt')` |
| `r.ls(path)` | 列目录 | `r.ls('demo/')` |
| `r.search(kw, path, file_pattern)` | grep搜索 | `r.search('import', '.', '*.py')` |
| `r.close()` | 关闭连接 | 用完必须close |

## 注意
- 🔴ssh_config.py在项目根目录(GenericAgent_MM/)，不在remote_develop/下。connect()源码已写明路径，别去子目录找
- path支持相对路径（基于project_path）和绝对路径
- patch要求old_content在文件中唯一，适合小片段替换
- 大段代码替换（如整个函数/多行字符串）优先用 `r.replace_lines()`：先 `r.read()` 确认行号范围，再一步替换，避免转义问题
- 本地写好文件后用 `r.upload()` 传到远程，比 `r.write()` 传大内容更可靠
- exec默认timeout=30s，长任务需加大：`r.exec(cmd, timeout=300)`
- exec支持cwd参数指定工作目录：`r.exec('ls', cwd='/opt')`
- 每次code_run结束后连接会断开，下次需重新connect
- 🔴本地ClashX代理(7890)会拦截直接ssh/scp命令，必须用connect()+upload()/download()传文件，禁止直接shell执行ssh/scp
- ssh_config中可配置`envs`字段（conda环境名），设置后exec自动将该环境bin加入PATH，python3/pip等命令直接使用该环境

## 复杂修改推荐工作流
当修改涉及多行字符串、特殊字符（引号/换行/转义）或多处patch时：
1. `r.download(remote, './temp_file')` 下载到本地
2. 本地用 `file_patch` / `file_read` 精确修改（本地工具更可靠）
3. `r.upload('./temp_file', remote)` 上传回远程
4. `r.read(path, keyword='关键内容')` 验证修改生效

简单单行替换直接用 `r.patch()` 即可，无需走此流程。

## 🔴首次探索远程项目（读代码前必做）
1. **禁止假设路径**: 项目名≠目录名，`r.ls('~')` 或 `r.ls('/')` 先看顶层结构
2. **逐层drill-down**: `r.ls()` 逐级进入，确认代码实际位置
3. **找不到就搜**: `r.exec('find / -name "target.py" -type f 2>/dev/null')` 全盘定位
4. **记住**: 每次 `code_run` 连接断开，下轮必须重新 `connect()` + 重新定义变量

## 远程多文件开发避坑（写代码前必做）
1. **环境探测先行**: 写代码前先 `r.exec('pip list')` + `r.exec('python --version')` 摸清已装包，避免写完才发现缺依赖
2. **读清再调用**: 调用现有模块前先 `r.read()` 完整读取其接口（类名/函数签名），禁止假设API
3. **Config一次写全**: 写config前先 `r.search('config.', '.', '*.py')` grep所有引用，一次定义完所有常量，禁止逐个补丁
4. **Import用lazy**: `__init__.py` 禁止 eager import 子模块；外部重依赖（transformers等）用函数内import
5. **全量验证**: 写完所有文件后，用一个脚本一次性 `import` 所有模块并报告错误，禁止逐个模块试错
6. **目录先建后用**: `r.exec('mkdir -p xxx')` 后再 `r.ls()`/`r.write()`，禁止对不存在的目录操作