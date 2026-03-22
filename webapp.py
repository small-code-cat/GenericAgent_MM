import os, sys, json, time, threading, queue, base64, uuid
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
try: sys.stdout.reconfigure(errors='replace')
except: pass
try: sys.stderr.reconfigure(errors='replace')
except: pass
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory', 'multimodal_memory'))

from flask import Flask, request, Response, jsonify, send_from_directory, send_file
from agentmain import GeneraticAgent
from mm_memory import list_memories, forget_group, recall as mm_recall, get_group

script_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(script_dir, 'webui'), static_url_path='/static')
# 大图 base64 塞进 JSON 会很大；默认提高上限，避免 413 / 连接被掐断
_max_mb = int(os.environ.get("MAX_UPLOAD_MB", "48"))
app.config["MAX_CONTENT_LENGTH"] = max(8, _max_mb) * 1024 * 1024


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

@app.route('/api/reinject_prompt', methods=['POST'])
def reinject_prompt():
    ag = get_agent()
    ag.llmclient.last_tools = ''
    return jsonify({'ok': True})

# ── 记忆管理 API ──────────────────────────────────────────

@app.route('/api/memory/list')
def memory_list():
    """列出所有记忆，按 group_id 分组返回"""
    limit = request.args.get('limit', 200, type=int)
    items = list_memories(limit=limit)
    # 按 group_id 分组
    groups = {}
    for item in items:
        d = item.to_dict()
        d.pop('embedding', None)  # 不传 embedding 到前端
        gid = d['group_id']
        if gid not in groups:
            groups[gid] = {'group_id': gid, 'created_at': d['created_at'],
                           'knowledge': [], 'sources': []}
        if d['embed_type'] == 'knowledge':
            groups[gid]['knowledge'].append(d)
        else:
            groups[gid]['sources'].append(d)
        # 更新组时间为最早的
        groups[gid]['created_at'] = min(groups[gid]['created_at'], d['created_at'])
    # 按时间倒序
    result = sorted(groups.values(), key=lambda g: g['created_at'], reverse=True)
    return jsonify(result)


@app.route('/api/memory/image')
def memory_image():
    """提供本地图片文件访问"""
    path = request.args.get('path', '')
    if not path or not os.path.isfile(path):
        return 'Not found', 404
    # 安全：只允许图片扩展名
    ext = os.path.splitext(path)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'):
        return 'Forbidden', 403
    return send_file(path)


@app.route('/api/memory/delete/<group_id>', methods=['DELETE'])
def memory_delete(group_id):
    """删除一组记忆"""
    count = forget_group(group_id)
    return jsonify({'deleted': count})


@app.route('/api/memory/recall')
def memory_recall():
    """语义检索记忆，返回与查询相关的记忆（按 group 去重聚合）"""
    query = request.args.get('query', '')
    top_k = request.args.get('top_k', 5, type=int)
    threshold = request.args.get('threshold', 0.35, type=float)
    if not query:
        return jsonify([])
    results = mm_recall(query, top_k=top_k, threshold=threshold)
    # 按 group_id 聚合，保留最高 score
    groups = {}
    for r in results:
        d = r.to_dict()
        d['item'].pop('embedding', None)
        gid = d['item']['group_id']
        if gid not in groups:
            # 获取完整 group 信息
            group_items = get_group(gid)
            group_data = {
                'group_id': gid,
                'score': d['score'],
                'match_reason': d['match_reason'],
                'knowledge': [],
                'sources': [],
                'created_at': d['item']['created_at'],
            }
            for gi in group_items:
                gi_d = gi.to_dict()
                gi_d.pop('embedding', None)
                if gi.embed_type == 'knowledge':
                    group_data['knowledge'].append(gi_d)
                else:
                    group_data['sources'].append(gi_d)
            groups[gid] = group_data
        else:
            groups[gid]['score'] = max(groups[gid]['score'], d['score'])
    # 按 score 降序
    result = sorted(groups.values(), key=lambda g: g['score'], reverse=True)
    return jsonify(result)


if __name__ == '__main__':
    get_agent()  # 预初始化
    app.run(host='0.0.0.0', port=5800, debug=False, threaded=True)