// background.js - Cookie + CDP Bridge
chrome.runtime.onInstalled.addListener(() => console.log('CDP Bridge installed'));

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'cookies') {
    handleCookies(msg, sender).then(sendResponse);
    return true;
  }
  if (msg.action === 'cdp') {
    handleCDP(msg, sender).then(sendResponse);
    return true;
  }
  if (msg.action === 'tabs') {
    (async () => {
      try {
        if (msg.method === 'switch') {
          const tab = await chrome.tabs.update(msg.tabId, { active: true });
          await chrome.windows.update(tab.windowId, { focused: true });
          sendResponse({ ok: true });
        } else {
          const tabs = await chrome.tabs.query({});
          const data = tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: t.active, windowId: t.windowId }));
          sendResponse({ ok: true, data });
        }
      } catch (e) { sendResponse({ ok: false, error: e.message }); }
    })();
    return true;
  }
});

async function handleCookies(msg, sender) {
  try {
    const url = msg.url || sender.tab?.url;
    const origin = url.match(/^https?:\/\/[^\/]+/)[0];
    const all = await chrome.cookies.getAll({ url });
    const part = await chrome.cookies.getAll({ url, partitionKey: { topLevelSite: origin } }).catch(() => []);
    const merged = [...all];
    for (const c of part) {
      if (!merged.some(x => x.name === c.name && x.domain === c.domain)) merged.push(c);
    }
    return { ok: true, data: merged };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function handleCDP(msg, sender) {
  const tabId = msg.tabId || sender.tab?.id;
  if (!tabId) return { ok: false, error: 'no tabId' };
  try {
    await chrome.debugger.attach({ tabId }, '1.3');
    const result = await chrome.debugger.sendCommand({ tabId }, msg.method, msg.params || {});
    await chrome.debugger.detach({ tabId });
    return { ok: true, data: result };
  } catch (e) {
    try { await chrome.debugger.detach({ tabId }); } catch (_) {}
    return { ok: false, error: e.message };
  }
}