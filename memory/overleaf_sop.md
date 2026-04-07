# Overleaf 编辑器操作 SOP

## 核心约束（已验证）
- 普通JS上下文：CM6 view不可访问（隔离），合成键盘事件无效
- **CDP桥可绕过隔离**：Runtime.evaluate可访问CM6 view（见下方CDP方法）
- CM6虚拟渲染，DOM仅~25行可见，不能通过DOM读取完整文档

## 编辑方法：CDP桥（需tmwebdriver_sop的TID元素通信）

### 读取全文
```js
// CDP Runtime.evaluate expression (⚠需 returnByValue:true):
const view = document.querySelector('.cm-content').cmView.view;
view.state.doc.toString();
// params: {expression: "...", returnByValue: true}
```
- ⚠️ cmView在`.cm-content`上，不是`.cm-editor`

### 精准替换文本
```js
view.dispatch({changes: {from: startPos, to: endPos, insert: newText}});
```

### 保存：CDP Input.dispatchKeyEvent
- Cmd+S: `{type:"keyDown", modifiers:4, key:"s", code:"KeyS", windowsVirtualKeyCode:83}`
- 需发keyDown+keyUp两个事件

### 🔴关键避坑：多层转义
- CDP表达式经过 JS模板→JSON→CDP 三层转义，反斜杠`\`极易出错
- **解法**：用`String.fromCharCode(92)`代替反斜杠字面量
- 复杂表达式：Python写入文件→读取→json.dumps编码→注入JS脚本