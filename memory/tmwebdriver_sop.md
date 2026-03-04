# TMWebDriver SOP

- 禁止import，直接用web_scan/web_execute_js工具。本文件只记录特性和坑。
- 底层：`../TMWebDriver.py`通过Tampermonkey脚本接管用户浏览器（保留登录态/Cookie）
- 非Selenium/Playwright，不需调试浏览器或新数据目录
- 支撑 `web_scan`(只读DOM) / `web_execute_js`(执行JS) 等高层工具

## 限制(isTrusted)
- JS dispatch的事件`isTrusted=false`，敏感操作(文件上传/部分按钮)会被浏览器拦截
- ⭐**首选绕过：CDP桥**——CDP派发的Input事件是浏览器原生级别(isTrusted=true)，且无需前台，见下方CDP章节
- 文件上传：JS无法填充`<input type=file>`，仍需ljqCtrl物理点击+Win32轮询文件对话框
  - 流程：SetForegroundWindow→ljqCtrl点上传按钮→FindWindow轮询对话框→输入路径→轮询关闭
- 备选：元素→屏幕物理坐标(ljqCtrl/PostMessage点击前必算)：JS一次取rect+窗口信息，公式：
  - `physX = (screenX + rect中心x) * dpr`，`physY = (screenY + chromeH + rect中心y) * dpr`
  - chromeH = outerHeight - innerHeight，dpr = devicePixelRatio
  - 注意：screenX/Y也是CSS像素，所有值先加后统一乘dpr
- 结论：读信息+普通操作用TMWebDriver；需isTrusted事件首选CDP桥；文件上传需配合ljqCtrl

## 导航
- `web_scan` 仅读当前页不导航，切换网站用 `web_execute_js` + `location.href='url'`

## Google图搜
- class名混淆禁硬编码，点击结果用 `[role=button]` div
- web_scan过滤边栏，弹出后用JS：文本`document.body.innerText`，大图遍历img按`naturalWidth`最大取src
- "访问"链接：遍历a找`textContent.includes('访问')`的href
- 缩略图：`img[src^="data:image"]`直接提取；大图src可能截断用`return img.src`

## Chrome下载PDF
场景：PDF链接在浏览器内预览而非下载
```js
fetch('PDF_URL').then(r=>r.blob()).then(b=>{
  const a=document.createElement('a');
  a.href=URL.createObjectURL(b);
  a.download='filename.pdf';
  a.click();
});
```
注意：需同源或CORS允许，跨域先导航到目标域再执行

## Chrome后台标签节流
- 后台标签中`setTimeout`被Chrome intensive throttling延迟到≥1min/次
- TM脚本中detect_newtab的轮询(`setTimeout 150ms × 10`)会超时
- 已修复：移除TM脚本内轮询，改由Python侧`get_session_dict()`前后对比检测新标签
- 同理：TM脚本中任何后台逻辑都应避免依赖setTimeout轮询

## CDP桥(tmwd_cdp_bridge扩展) ⭐首选
扩展路径：`assets/tmwd_cdp_bridge/`(需安装，含debugger权限)
调用：MutationObserver监听addedNodes(id=`__ljq_ctrl`)，⚠每次必须remove旧→createElement新→设textContent JSON→appendChild
```js
const old = document.getElementById('__ljq_ctrl');
if (old) old.remove();
const el = document.createElement('div');
el.id = '__ljq_ctrl'; el.style.display = 'none';
el.textContent = JSON.stringify({cmd:'...', ...});
document.body.appendChild(el);  // 响应写回el.textContent
```
命令：`{cmd:'tabs'}` | `{cmd:'cookies'}` | `{cmd:'cdp', tabId:N, method:'...', params:{...}}`
- CDP可用任意方法(Input/Network/DOM/Page/Runtime/Emulation等)，每次attach→send→detach
- ⭐跨tab无需前台：指定tabId即可操作后台标签页
- ⭐绕过isTrusted：CDP派发的Input事件是浏览器原生级别

## autofill获取
检测：web_scan输出input带`data-autofilled="true"`，value显示为受保护提示(非真实值，Chrome安全保护需点击释放)
- ⭐首选CDP：tabs获取tabId→CDP mousePressed点击输入框→autofill值释放→JS读`.value`(无需前台)
- 备选PostMessage物理点击(仅Windows/需前台)：枚举Chrome窗口标题匹配→rect*dpr→WM_LBUTTONDOWN/UP到Chrome_RenderWidgetHostHWND子窗口
  - 坑：多RenderWidgetHostHWND共存，必须按父窗口标题匹配再取子窗口

## 验证码/页面视觉截图
- 优先：JS `canvas.toDataURL()` 直接拿base64（验证码是canvas/img时最干净，无需截屏）
- 备选：`window.open(location.href,'_blank')` 前台开新标签→win32截图→完后close
  - GM_openInTab在web_execute_js不可用（非油猴上下文）
  - 浏览器无JS API切标签页，只能开新的来保证前台

## 跨域iframe操控(postMessage中继)
- 跨域iframe的contentDocument不可访问，web_execute_js只在顶层执行
- TM脚本已改造：iframe内不return，改为监听postMessage并eval执行+回传结果
- 顶层发送：`iframe.contentWindow.postMessage({type:'ljq_exec', id, code}, '*')`
- iframe回传：`{type:'ljq_result', id, result}` 通过window.addEventListener('message')接收
- ⚠只能eval表达式，不支持return/函数体包装，构造代码时注意
- 流程：发postMessage→等→读window._ljqResults[id]获取结果
- 已验证：读取iframe内DOM(document.title)、填写input均成功