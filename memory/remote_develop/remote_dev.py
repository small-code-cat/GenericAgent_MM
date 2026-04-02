import paramiko
import sys, os

class RemoteDev:
    """远程开发工具 - 通过SSH操作远程服务器文件和命令"""
    
    def __init__(self, config: dict):
        self.host = config['hostname']
        self.port = int(config.get('port', 22))
        self.user = config.get('user', 'root')
        self.password = config.get('password')
        self.project = config.get('project_path', '')
        self.envs = config.get('envs', '')  # conda环境名，设置后exec自动激活
        self._ssh = None
        self._sftp = None
    
    def _connect(self):
        if self._ssh and self._ssh.get_transport() and self._ssh.get_transport().is_active():
            return
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._ssh.connect(self.host, self.port, self.user, self.password, timeout=10)
        self._sftp = self._ssh.open_sftp()
    
    def _abs(self, path):
        """相对路径转绝对路径（基于project_path）"""
        if path.startswith('/'):
            return path
        return os.path.join(self.project, path)
    
    def exec(self, cmd, timeout=30, cwd=None):
        """远程执行命令，返回 (stdout, stderr, exit_code)。cwd:工作目录; envs自动激活conda"""
        self._connect()
        if cwd:
            cmd = f'cd {cwd} && {cmd}'
        if self.envs:
            env_bin = f'/root/miniconda3/envs/{self.envs}/bin'
            cmd = f'export PATH={env_bin}:$PATH && {cmd}'
        _, stdout, stderr = self._ssh.exec_command(cmd, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        return out, err, code
    
    def read(self, path, keyword=None, start=None, count=200, context=None, match_index=1):
        """读取远程文件内容。
        keyword:关键字搜索; start:起始行号(从1开始), count:读取行数
        context:keyword模式下上下文行数(默认前5后15,可传int统一设或(before,after)元组)
        match_index:keyword模式下第几个匹配(从1开始,0=返回所有匹配位置摘要)"""
        self._connect()
        with self._sftp.open(self._abs(path), 'r') as f:
            content = f.read().decode('utf-8', errors='replace')
        lines = content.split('\n')
        if keyword:
            # 解析context参数
            if context is None:
                before, after = 5, 15
            elif isinstance(context, tuple):
                before, after = context
            else:
                before = after = int(context)
            # 找所有匹配
            matches = [i for i, line in enumerate(lines) if keyword.lower() in line.lower()]
            if not matches:
                return f"[keyword '{keyword}' not found]"
            if match_index == 0:
                # 返回所有匹配位置摘要
                summary = f"[{len(matches)} matches for '{keyword}']:\n"
                summary += '\n'.join(f"  match {k+1}: line {m+1} | {lines[m].strip()[:80]}" for k, m in enumerate(matches))
                return summary
            # 返回第match_index个匹配的上下文
            idx = min(match_index, len(matches)) - 1
            i = matches[idx]
            s = max(0, i - before)
            e = min(len(lines), i + after + 1)
            header = f"[match {idx+1}/{len(matches)}] " if len(matches) > 1 else ""
            return header + '\n'.join(f"{j+1}| {lines[j]}" for j in range(s, e))
        if start is not None:
            s = max(0, start - 1)
            e = min(len(lines), s + count)
            return '\n'.join(f"{j+1}| {lines[j]}" for j in range(s, e))
        return content
    
    def write(self, path, content, mode='overwrite'):
        """写入远程文件。mode: overwrite/append"""
        self._connect()
        abs_path = self._abs(path)
        if mode == 'append':
            try:
                old = self._sftp.open(abs_path, 'r').read().decode('utf-8', errors='replace')
            except FileNotFoundError:
                old = ''
            content = old + content
        with self._sftp.open(abs_path, 'w') as f:
            f.write(content.encode('utf-8'))
        return f"[written {len(content)} chars to {abs_path}]"
    
    def patch(self, path, old_content, new_content):
        """精准替换远程文件中的内容片段"""
        content = self.read(self._abs(path))
        count = content.count(old_content)
        if count == 0:
            return "[ERROR] old_content not found in file"
        if count > 1:
            return f"[ERROR] old_content found {count} times, must be unique"
        new = content.replace(old_content, new_content, 1)
        return self.write(path, new)
    
    def replace_lines(self, path, start, end, new_content):
        """替换远程文件第start到end行(含)为new_content。先read确认行号再调用"""
        content = self.read(self._abs(path))
        lines = content.split('\n')
        if start < 1 or end > len(lines):
            return f"[ERROR] line range {start}-{end} out of bounds (total {len(lines)} lines)"
        lines[start-1:end] = new_content.split('\n')
        return self.write(path, '\n'.join(lines))
    
    def upload(self, local_path, remote_path):
        """上传本地文件到远程服务器"""
        self._connect()
        self._sftp.put(local_path, self._abs(remote_path))
        return f"[uploaded {local_path} -> {self._abs(remote_path)}]"
    
    def download(self, remote_path, local_path):
        """下载远程文件到本地"""
        self._connect()
        self._sftp.get(self._abs(remote_path), local_path)
        return f"[downloaded {self._abs(remote_path)} -> {local_path}]"
    
    def ls(self, path='.'):
        """列出远程目录"""
        out, err, code = self.exec(f'ls -la {self._abs(path)}')
        return out if code == 0 else f"[ERROR] {err}"
    
    def search(self, keyword, path='.', file_pattern='*'):
        """在远程目录中搜索文件内容"""
        cmd = f'grep -rn --include="{file_pattern}" "{keyword}" {self._abs(path)} 2>/dev/null | head -50'
        out, _, _ = self.exec(cmd)
        return out if out else f"[no matches for '{keyword}']"
    
    def close(self):
        if self._sftp: self._sftp.close()
        if self._ssh: self._ssh.close()
        self._ssh = self._sftp = None
    
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


# 快捷初始化函数
def connect(config_name='ssh1'):
    """从ssh_config.py加载配置并返回RemoteDev实例"""
    sys.path.insert(0, '/Users/xuekejun/CursorProjects/GenericAgent_MM')
    from ssh_config import __dict__ as configs
    import ssh_config
    cfg = getattr(ssh_config, config_name)
    return RemoteDev(cfg)