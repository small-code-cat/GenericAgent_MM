import json, re, time, os, base64
from llm_stats import LLMStatsLogger
from llmcore import downscale_image_bytes
from dataclasses import dataclass
from typing import Any, Optional, List

# ── 从 <tool_result> 块中提取图片路径并就地插入 base64 图片 ──
_IMG_PATH_RE = re.compile(r'(?:/[\w.\-]+)+\.(?:jpg|jpeg|png|webp|gif|bmp)', re.IGNORECASE)
_TOOL_RESULT_RE = re.compile(r'<tool_result>\s*(.*?)\s*</tool_result>', re.DOTALL)
_IMG_EXT_MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                 '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp'}

def _build_content_with_inline_images(text: str, is_claude: bool = False):
    """仅从 <tool_result> 块内解析图片路径，在路径后方就地插入 base64 image part。
    若未找到任何可加载图片，返回原始字符串；否则返回 content list。
    is_claude=True 时使用 Claude 原生 image 格式，否则使用 image_url 格式。"""
    if not text:
        return text
    # 仅在 <tool_result> 块内搜索图片路径，收集 (绝对位置, 路径)
    img_insertions = []
    for tr in _TOOL_RESULT_RE.finditer(text):
        tr_start = tr.start(1)
        for m in _IMG_PATH_RE.finditer(tr.group(1)):
            img_insertions.append((tr_start + m.end(), m.group()))
    if not img_insertions:
        return text
    loaded_paths = set()
    parts = []
    last_end = 0
    img_count = 0
    for abs_end, path in img_insertions:
        if path in loaded_paths or not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        mime = _IMG_EXT_MIME.get(ext)
        if not mime or img_count >= 8:
            continue
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            raw, new_mime = downscale_image_bytes(raw)
            if new_mime: mime = new_mime
            b64 = base64.b64encode(raw).decode()
        except Exception:
            continue
        text_chunk = text[last_end:abs_end]
        if text_chunk:
            parts.append({"type": "text", "text": text_chunk})
        if is_claude:
            parts.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
        else:
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        last_end = abs_end
        img_count += 1
        loaded_paths.add(path)
    if img_count == 0:
        return text
    remaining = text[last_end:]
    if remaining:
        parts.append({"type": "text", "text": remaining})
    return parts

def _insert_images_around_user_input(text, user_input, image_parts):
    """在文本中找到 user_input，在其后插入 image_parts，返回 content list。"""
    if not text:
        return []
    if not image_parts or not user_input:
        return [{"type": "text", "text": text}]
    idx = text.find(user_input)
    if idx == -1:
        parts = [{"type": "text", "text": text}]
        parts.extend(image_parts)
        return parts
    split_pos = idx + len(user_input)
    parts = []
    if split_pos > 0:
        parts.append({"type": "text", "text": text[:split_pos]})
    parts.extend(image_parts)
    if split_pos < len(text):
        parts.append({"type": "text", "text": text[split_pos:]})
    return parts

@dataclass
class StepOutcome:
    data: Any
    next_prompt: Optional[str] = None
    should_exit: bool = False

def try_call_generator(func, *args, **kwargs):
    ret = func(*args, **kwargs)
    if hasattr(ret, '__iter__') and not isinstance(ret, (str, bytes, dict, list)):
        ret = yield from ret
    return ret

class BaseHandler:
    def tool_before_callback(self, tool_name, args, response): pass
    def tool_after_callback(self, tool_name, args, response, ret): pass
    def next_prompt_patcher(self, next_prompt, outcome, turn): return next_prompt
    def dispatch(self, tool_name, args, response, index=0):
        method_name = f"do_{tool_name}"
        if hasattr(self, method_name):
            args['_index'] = index
            prer = yield from try_call_generator(self.tool_before_callback, tool_name, args, response)
            ret = yield from try_call_generator(getattr(self, method_name), args, response)
            _ = yield from try_call_generator(self.tool_after_callback, tool_name, args, response, ret)
            return ret
        elif tool_name == 'bad_json':
            return StepOutcome(None, next_prompt=args.get('msg', 'bad_json'), should_exit=False)
        else:
            yield f"未知工具: {tool_name}\n"
            return StepOutcome(None, next_prompt=f"未知工具 {tool_name}", should_exit=False)

def json_default(o):
    if isinstance(o, set): return list(o)
    return str(o) 

def exhaust(g):
    try: 
        while True: next(g)
    except StopIteration as e: return e.value

def get_pretty_json(data):
    if isinstance(data, dict) and "script" in data:
        data = data.copy()
        data["script"] = data["script"].replace("; ", ";\n  ")
    return json.dumps(data, indent=2, ensure_ascii=False).replace('\\n', '\n')

def agent_runner_loop(client, system_prompt, user_input, handler, tools_schema, max_turns=15, verbose=True, initial_user_content=None):
    # Extract image parts from multimodal content to persist across turns
    _image_parts = [p for p in (initial_user_content or []) if isinstance(p, dict) and p.get("type") in ("image_url", "image")] if isinstance(initial_user_content, list) else []
    # 构建用户上传图片路径→image_part映射，用于后续轮次就地插入
    _user_image_map = {}
    _unmapped_images = []
    if _image_parts and isinstance(initial_user_content, list):
        _paths = []
        for p in initial_user_content:
            if isinstance(p, dict) and p.get('type') == 'text':
                _paths.extend(_IMG_PATH_RE.findall(p.get('text', '')))
        for i, img_part in enumerate(_image_parts):
            if i < len(_paths):
                _user_image_map[_paths[i]] = img_part
            else:
                _unmapped_images.append(img_part)
    else:
        _unmapped_images = list(_image_parts)
    _is_claude = 'claude' in str(getattr(getattr(client, 'backend', None), 'default_model', '')).lower()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_content if initial_user_content is not None else user_input}
    ]
    _stats = LLMStatsLogger.get()
    _stats.new_qa()
    for turn in range(max_turns):
        yield f"**LLM Running (Turn {turn+1}) ...**\n\n"
        if (turn+1) % 10 == 0: client.last_tools = ''  # 每10轮重置一次工具描述，避免上下文过大导致的模型性能下降
        _stats.set_iteration(turn + 1)
        response_gen = client.chat(messages=messages, tools=tools_schema)
        if verbose:
            response = yield from response_gen
            yield '\n\n'
        else:
            response = exhaust(response_gen)
            yield response.content
        if not response.tool_calls: tool_calls = [{'tool_name': 'no_tool', 'args': {}}]
        else: tool_calls = [{'tool_name': tc.function.name, 'args': json.loads(tc.function.arguments)}
                          for tc in response.tool_calls]
       
        next_prompt = ""
        for ii, tc in enumerate(tool_calls):
            tool_name, args = tc['tool_name'], tc['args']
            if tool_name == 'no_tool': pass
            else: 
                showarg = get_pretty_json(args)
                if not verbose and len(showarg) > 200: showarg = showarg[:200] + ' ...'
                yield f"🛠️ **正在调用工具:** `{tool_name}`  📥**参数:**\n````text\n{showarg}\n````\n" 
            handler.current_turn = turn + 1
            gen = handler.dispatch(tool_name, args, response, index=ii)
            if verbose:
                yield '`````\n'
                outcome = yield from gen
                yield '`````\n'
            else: outcome = exhaust(gen)

            if outcome.next_prompt is None: return {'result': 'CURRENT_TASK_DONE', 'data': outcome.data}
            if outcome.should_exit: return {'result': 'EXITED', 'data': outcome.data}
            if outcome.next_prompt.startswith('未知工具'): client.last_tools = ''

            if outcome.data is not None: 
                datastr = json.dumps(outcome.data, ensure_ascii=False, default=json_default) if type(outcome.data) in [dict, list] else str(outcome.data) 
                next_prompt += f"<tool_result>\n{datastr}\n</tool_result>\n\n"
            next_prompt += outcome.next_prompt
        next_prompt = handler.next_prompt_patcher(next_prompt, None, turn+1)
        # 以最后一个 </tool_result> 分割，前半部分处理 tool_result 内图片，后半部分插入用户上传图片
        _split_tag = '</tool_result>'
        _split_idx = next_prompt.rfind(_split_tag)
        if _split_idx != -1:
            _front = next_prompt[:_split_idx + len(_split_tag)]
            _back = next_prompt[_split_idx + len(_split_tag):]
            front_parts = _build_content_with_inline_images(_front, is_claude=_is_claude)
            if isinstance(front_parts, str):
                front_parts = [{"type": "text", "text": front_parts}] if front_parts else []
            back_parts = _insert_images_around_user_input(_back, user_input, _image_parts)
            content = front_parts + back_parts
        else:
            content = _insert_images_around_user_input(next_prompt, user_input, _image_parts)
        messages = [{"role": "user", "content": content}]
    return {'result': 'MAX_TURNS_EXCEEDED'}
