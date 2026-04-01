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
    
    def exec(self, cmd, timeout=30):
        """远程执行命令，返回 (stdout, stderr, exit_code)。若配置了envs则自动激活conda环境"""
        self._connect()
        if self.envs:
            env_bin = f'/root/miniconda3/envs/{self.envs}/bin'
            cmd = f'export PATH={env_bin}:$PATH && {cmd}'
        _, stdout, stderr = self._ssh.exec_command(cmd, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        return out, err, code
    
    def read(self, path, keyword=None):
        """读取远程文件内容，可选关键字搜索"""
        self._connect()
        with self._sftp.open(self._abs(path), 'r') as f:
            content = f.read().decode('utf-8', errors='replace')
        if keyword:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if keyword.lower() in line.lower():
                    start = max(0, i - 5)
                    end = min(len(lines), i + 15)
                    return '\n'.join(f"{j+1}| {lines[j]}" for j in range(start, end))
            return f"[keyword '{keyword}' not found]"
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