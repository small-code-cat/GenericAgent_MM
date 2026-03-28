"""LLM调用统计模块 - 独立于原有token估算，仅用于统计分析"""
import os, json, time, base64, struct, zlib, re
from datetime import datetime

try:
    import tiktoken
    _enc = tiktoken.encoding_for_model("gpt-4o")
except Exception:
    _enc = None

def count_text_tokens(text):
    """用tiktoken计算文本token数"""
    if not text or not _enc:
        return 0
    if not isinstance(text, str):
        text = str(text)
    return len(_enc.encode(text))

def _get_png_dimensions(data):
    """从PNG二进制数据提取宽高"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        w = struct.unpack('>I', data[16:20])[0]
        h = struct.unpack('>I', data[20:24])[0]
        return w, h
    return None, None

def _get_jpeg_dimensions(data):
    """从JPEG二进制数据提取宽高"""
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            break
        marker = data[i+1]
        if marker in (0xC0, 0xC1, 0xC2):
            h = struct.unpack('>H', data[i+5:i+7])[0]
            w = struct.unpack('>H', data[i+7:i+9])[0]
            return w, h
        length = struct.unpack('>H', data[i+2:i+4])[0]
        i += 2 + length
    return None, None

def _image_dimensions_from_base64(b64_str):
    """从base64编码的图片数据提取宽高"""
    try:
        data = base64.b64decode(b64_str[:1024])  # 只需要头部
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return _get_png_dimensions(data)
        elif data[:2] in (b'\xff\xd8',):
            data = base64.b64decode(b64_str)  # JPEG需要更多数据
            return _get_jpeg_dimensions(data)
    except Exception:
        pass
    return None, None

def count_image_tokens(width, height):
    """Claude图片token估算: 缩放后 (w*h)/750"""
    if not width or not height:
        return 0
    max_dim = max(width, height)
    if max_dim > 1568:
        scale = 1568 / max_dim
        width = int(width * scale)
        height = int(height * scale)
    return int((width * height) / 750)

def _extract_text_from_content(content):
    """从messages content中提取纯文本（图片替换为占位符）"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") in ("image_url", "image"):
                    parts.append("[IMAGE]")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content) if content else ""

def _count_image_tokens_from_content(content):
    """从messages content中计算所有图片的token总数"""
    total = 0
    if not isinstance(content, list):
        return 0
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "image_url":
            url = item.get("image_url", {}).get("url", "")
            if url.startswith("data:"):
                b64 = url.split(",", 1)[-1] if "," in url else ""
                w, h = _image_dimensions_from_base64(b64)
                total += count_image_tokens(w, h)
            else:
                total += 1000  # URL图片默认估算
        elif item.get("type") == "image":
            b64 = item.get("source", {}).get("data", "")
            if b64:
                w, h = _image_dimensions_from_base64(b64)
                total += count_image_tokens(w, h)
            else:
                total += 1000
    return total


class LLMStatsLogger:
    """LLM调用统计记录器，每个进程一个实例"""
    _instance = None
    
    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        pid = os.getpid()
        self.filepath = os.path.join(os.path.dirname(__file__), "temp", f"llm_stats_{pid}.jsonl")
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self.qa_index = 0
    
    def new_qa(self):
        """开始新的QA"""
        self.qa_index += 1
    
    def log_iteration(self, iteration, model, messages, response_text, response_time_s):
        """记录一次迭代的统计数据
        
        Args:
            iteration: 迭代轮次(1-based)
            model: 模型名称
            messages: 发送给模型的完整messages列表
            response_text: 模型响应文本
            response_time_s: 响应耗时(秒)
        """
        all_text_parts = []
        display_text_parts = []
        image_tokens = 0
        for msg in (messages if isinstance(messages, list) else []):
            content = msg.get("content", "") if isinstance(msg, dict) else msg
            role = msg.get("role", "") if isinstance(msg, dict) else ""
            text = _extract_text_from_content(content)
            all_text_parts.append(text)
            image_tokens += _count_image_tokens_from_content(content)
            # input_text只保留非system消息，并去掉tool_result块
            if role != "system":
                cleaned = re.sub(r'<tool_result>.*?</tool_result>', '', text, flags=re.DOTALL).strip()
                if cleaned:
                    display_text_parts.append(cleaned)
        input_text = "\n".join(display_text_parts)
        input_tokens = count_text_tokens("\n".join(all_text_parts))
        output_tokens = count_text_tokens(response_text or "")
        
        record = {
            "qa_index": self.qa_index,
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "model": model or "unknown",
            "input_tokens": input_tokens,
            "image_tokens": image_tokens,
            "total_input_tokens": input_tokens + image_tokens,
            "output_tokens": output_tokens,
            "response_time_s": round(response_time_s, 3),
            "input_text": input_text,
            "output_text": response_text or ""
        }
        
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[LLMStats] 写入失败: {e}")