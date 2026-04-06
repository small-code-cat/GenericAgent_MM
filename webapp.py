import os, sys, json, time, threading, queue, base64, uuid, logging, sqlite3
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
try: sys.stdout.reconfigure(errors='replace')
except: pass
try: sys.stderr.reconfigure(errors='replace')
except: pass
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, request, Response, jsonify, send_from_directory, send_file
from agentmain import GeneraticAgent

script_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(script_dir, 'webui'), static_url_path='/static')
# 大图 base64 塞进 JSON 会很大；默认提高上限，避免 413 / 连接被掐断
_max_mb = int(os.environ.get("MAX_UPLOAD_MB", "48"))
app.config["MAX_CONTENT_LENGTH"] = max(8, _max_mb) * 1024 * 1024

# 过滤 /api/status 轮询日志，避免刷屏
class _NoStatusLog(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return 'GET /api/status' not in msg
logging.getLogger('werkzeug').addFilter(_NoStatusLog())


@app.errorhandler(413)
def request_entity_too_large(_e):
    return jsonify({"error": "请求体过大，请缩小图片或压缩后再发"}), 413

agent = None
agent_lock = threading.Lock()
autonomous_enabled = False
last_reply_time = 0

def get_agent():
    global agent
    if agent is None:
        agent = GeneraticAgent()
        if agent.llmclient is None:
            raise RuntimeError("未配置任何可用的 LLM 接口")
        threading.Thread(target=agent.run, daemon=True).start()
    return agent

@app.route('/')
def index():
    return send_from_directory(os.path.join(script_dir, 'webui'), 'index.html')

@app.route('/token_stats.html')
def token_stats():
    return send_from_directory(os.path.join(script_dir, 'webui'), 'token_stats.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    global last_reply_time
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "无效的 JSON 或请求体过大"}), 400
    prompt = (data.get("message") or "").strip()
    has_images = bool(data.get('images'))
    if not prompt and not has_images:
        return jsonify({'error': 'Empty message'}), 400
    if not prompt and has_images:
        prompt = '请看这张图片'

    # Handle images: save base64 data URLs to temp files
    image_paths = []
    for img_data in (data.get('images') or []):
        try:
            # img_data is like "data:image/png;base64,iVBOR..."
            if ',' in img_data:
                header, b64 = img_data.split(',', 1)
                ext = 'png'
                if 'jpeg' in header or 'jpg' in header: ext = 'jpg'
                elif 'webp' in header: ext = 'webp'
                elif 'gif' in header: ext = 'gif'
            else:
                b64 = img_data
                ext = 'png'
            img_bytes = base64.b64decode(b64)
            temp_dir = os.path.join(script_dir, 'temp', 'uploads')
            os.makedirs(temp_dir, exist_ok=True)
            fpath = os.path.join(temp_dir, f'{uuid.uuid4().hex[:12]}.{ext}')
            with open(fpath, 'wb') as f:
                f.write(img_bytes)
            image_paths.append(fpath)
        except Exception as e:
            print(f'[WARN] Failed to save uploaded image: {e}')

    ag = get_agent()
    display_queue = ag.put_task(prompt, source="user", images=image_paths if image_paths else None)

    def generate():
        global last_reply_time
        try:
            while True:
                try:
                    item = display_queue.get(timeout=120)
                except queue.Empty:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Timeout'})}\n\n"
                    break
                if 'next' in item:
                    yield f"data: {json.dumps({'type': 'stream', 'content': item['next']})}\n\n"
                if 'done' in item:
                    yield f"data: {json.dumps({'type': 'done', 'content': item['done']})}\n\n"
                    last_reply_time = int(time.time())
                    break
        except GeneratorExit:
            ag.abort()

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/api/abort', methods=['POST'])
def abort():
    ag = get_agent()
    ag.abort()
    return jsonify({'ok': True})

@app.route('/api/switch_llm', methods=['POST'])
def switch_llm():
    data = request.json or {}
    n = data.get('index', -1)
    ag = get_agent()
    ag.next_llm(n)
    return jsonify({'ok': True, 'current': ag.get_llm_name(), 'index': ag.llm_no})

@app.route('/api/llms', methods=['GET'])
def list_llms():
    ag = get_agent()
    llms = ag.list_llms()
    return jsonify({'llms': [{'index': i, 'name': n, 'active': a} for i, n, a in llms]})

@app.route('/api/status', methods=['GET'])
def status():
    global last_reply_time, autonomous_enabled
    ag = get_agent()
    return jsonify({
        'llm_name': ag.get_llm_name(),
        'llm_no': ag.llm_no,
        'is_running': ag.is_running,
        'last_reply_time': last_reply_time,
        'idle_seconds': int(time.time()) - last_reply_time if last_reply_time > 0 else 0,
        'autonomous_enabled': autonomous_enabled
    })

@app.route('/api/autonomous', methods=['POST'])
def toggle_autonomous():
    global autonomous_enabled, last_reply_time
    data = request.json or {}
    action = data.get('action', 'toggle')
    if action == 'enable':
        autonomous_enabled = True
    elif action == 'disable':
        autonomous_enabled = False
    elif action == 'force_start':
        last_reply_time = int(time.time()) - 1800
    else:
        autonomous_enabled = not autonomous_enabled
    return jsonify({'autonomous_enabled': autonomous_enabled})

@app.route('/api/list_jsonl', methods=['GET'])
def list_jsonl():
    temp_dir = os.path.join(script_dir, 'temp')
    files = []
    current_file = f'llm_stats_{os.getpid()}.jsonl'
    if os.path.isdir(temp_dir):
        for f in sorted(os.listdir(temp_dir), reverse=True):
            if f.endswith('.jsonl'):
                fpath = os.path.join(temp_dir, f)
                size_kb = round(os.path.getsize(fpath) / 1024, 1)
                files.append({'name': f, 'size_kb': size_kb, 'is_current': f == current_file})
    return jsonify({'files': files, 'current': current_file})

@app.route('/api/token_stats', methods=['GET'])
def api_token_stats():
    fname = request.args.get('file', '')
    if fname and not fname.endswith('.jsonl'):
        return jsonify([])  # safety
    if fname:
        # 防止路径穿越
        fname = os.path.basename(fname)
        jsonl_path = os.path.join(script_dir, 'temp', fname)
    else:
        jsonl_path = os.path.join(script_dir, 'temp', f'llm_stats_{os.getpid()}.jsonl')
    if not os.path.exists(jsonl_path):
        return jsonify([])
    qa_map = {}
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            qi = rec.get('qa_index', 0)
            if qi not in qa_map:
                qa_map[qi] = {'id': qi, 'question': (rec.get('input_text') or '')[:80], 'iterations': []}
            qa_map[qi]['iterations'].append({
                'round': rec.get('iteration', 1),
                'input_tokens': rec.get('total_input_tokens', rec.get('input_tokens', 0)),
                'output_tokens': rec.get('output_tokens', 0),
                'time_sec': round(rec.get('response_time_s', 0), 1),
                'input_text': (rec.get('input_text') or '')[:500],
                'output_text': (rec.get('output_text') or '')[:500]
            })
    result = sorted(qa_map.values(), key=lambda x: x['id'])
    return jsonify(result)

@app.route('/api/reinject_prompt', methods=['POST'])
def reinject_prompt():
    ag = get_agent()
    ag.llmclient.last_tools = ''
    return jsonify({'ok': True})

# ── 多模态记忆库管理 ──────────────────────────────────────
_mm_db_path = os.path.join(script_dir, 'memory', 'multimodal_memory', 'mm_data.db')

@app.route('/memory_manager.html')
def memory_manager():
    return send_from_directory(os.path.join(script_dir, 'webui'), 'memory_manager.html')

@app.route('/api/memories', methods=['GET'])
def api_memories():
    db = os.path.abspath(_mm_db_path)
    if not os.path.exists(db):
        return jsonify({'groups': []})
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT id, group_id, content, source_type, source_path, created_at, embed_type FROM memories ORDER BY created_at DESC, group_id, id').fetchall()
    conn.close()
    groups = {}
    for r in rows:
        gid = r['group_id']
        if gid not in groups:
            groups[gid] = {'group_id': gid, 'created_at': r['created_at'], 'source_type': r['source_type'], 'image_path': '', 'knowledge': '', 'source_text': '', 'image_desc': ''}
        item = groups[gid]
        et = r['embed_type']
        if et == 'knowledge':
            item['knowledge'] = r['content'] or ''
        elif et == 'source_text':
            item['source_text'] = r['content'] or ''
        elif et == 'source_image':
            item['image_desc'] = r['content'] or ''
            item['image_path'] = r['source_path'] or ''
    return jsonify({'groups': list(groups.values())})

@app.route('/api/memories/<group_id>', methods=['DELETE'])
def api_delete_memory(group_id):
    db = os.path.abspath(_mm_db_path)
    if not os.path.exists(db):
        return jsonify({'error': 'DB not found'}), 404
    conn = sqlite3.connect(db)
    # 先查出关联的图片文件路径，删除后也清理文件
    rows = conn.execute('SELECT source_path FROM memories WHERE group_id=?', (group_id,)).fetchall()
    conn.execute('DELETE FROM memories WHERE group_id=?', (group_id,))
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    # 尝试删除关联图片文件
    for row in rows:
        img = row[0]
        if img and os.path.isfile(img):
            try: os.remove(img)
            except: pass
    return jsonify({'ok': True, 'deleted': deleted})

@app.route('/api/memory_image')
def api_memory_image():
    """安全地提供记忆库中的图片文件"""
    fpath = request.args.get('path', '')
    if not fpath:
        return 'Missing path', 400
    abs_path = os.path.abspath(fpath)
    # 安全检查：只允许访问 memory 目录下的图片
    allowed_root = os.path.abspath(os.path.join(script_dir, 'memory'))
    if not abs_path.startswith(allowed_root):
        return 'Forbidden', 403
    if not os.path.isfile(abs_path):
        return 'Not found', 404
    return send_file(abs_path)


if __name__ == '__main__':
    get_agent()  # 预初始化
    app.run(host='0.0.0.0', port=5800, debug=False, threaded=True)