# Overleaf 编辑器操作 SOP

## 核心约束（已验证）
- CM6虚拟渲染，DOM仅~25行可见，不能通过DOM读取完整文档
- 合成键盘事件无效（CM6不监听DOM事件）
- **web_execute_js可直接访问cmView**（无需CDP），通过`.cm-content`元素
- CDP桥也可用，但非必需

## 编辑方法：web_execute_js直接操作CM6（推荐）

### 读取全文
```js
const view = document.querySelector('.cm-content').cmView.view;
return view.state.doc.toString();
```
- ⚠️ cmView在`.cm-content`上，不是`.cm-editor`

### 精准替换文本
```js
view.dispatch({changes: {from: startPos, to: endPos, insert: newText}});
```

### 保存：DOM KeyboardEvent（已验证）
```js
// 需同时设metaKey+ctrlKey，派发到document
const opts = {key:'s', code:'KeyS', keyCode:83, which:83, metaKey:true, ctrlKey:true, bubbles:true, cancelable:true};
document.dispatchEvent(new KeyboardEvent('keydown', opts));
document.dispatchEvent(new KeyboardEvent('keyup', opts));
```
- 会触发编译，若频率过高返回"compiled very recently"（不影响保存）

### 内容修改策略（省token优先）
- **精细替换（优先）**：用indexOf定位old_content，只替换差异部分，省80%+ token
```js
const doc = view.state.doc.toString();
const from = doc.indexOf(oldContent);
view.dispatch({changes: {from, to: from + oldContent.length, insert: newContent}});
```
- **全量替换（兜底）**：仅当多处修改或结构大改时使用
```js
view.dispatch({changes:{from:0, to:view.state.doc.length, insert:fullContent}});
```
- 大内容用Python json.dumps转义→写入JS文件→`web_execute_js`传文件路径
- 10K+字符已验证可靠

### 🔴闭环：注入后必须保存
- CM6 dispatch只改buffer，**不会自动同步服务器**
- 注入内容后必须立即执行上方保存动作（Cmd+S）
- 完整流程：注入→保存→（可选）验证编译

### 🔴关键避坑：多层转义
- CDP表达式经过 JS模板→JSON→CDP 三层转义，反斜杠`\`极易出错
- **解法**：用`String.fromCharCode(92)`代替反斜杠字面量
- 复杂表达式：Python写入文件→读取→json.dumps编码→注入JS脚本