/**
 * 聊天页逻辑：负责 会话管理 + 收发消息 + 渲染界面。
 *
 * 整体思路（和页面上三个区域一一对应）：
 * 1. 会话抽屉：从后端拉会话列表，点哪个就切换到哪个会话
 * 2. 聊天区：把消息渲染成气泡（用户靠右蓝色，AI 靠左白色）
 * 3. 输入栏：回车/点发送 → 调后端接口 → 把 AI 回复追加到聊天区
 *
 * 用到的后端接口（都在 main.py 里定义）：
 *   POST /api/sessions                     新建会话
 *   GET  /api/sessions                     会话列表
 *   GET  /api/sessions/{id}/messages       某会话的全部消息
 *   POST /api/sessions/{id}/messages       发消息（返回 AI 回复和线索卡片）
 *   POST /api/sessions/{id}/end            手动结束对话（强制生成线索）
 */

// ===== 当前状态 =====
let currentSessionId = null; // 当前正在聊的会话 id

// ===== 页面元素（一次性取好，后面反复用） =====
const chatArea = document.getElementById("chatArea");
const sessionList = document.getElementById("sessionList");
const drawer = document.getElementById("drawer");
const drawerMask = document.getElementById("drawerMask");
const msgInput = document.getElementById("msgInput");
const sendBtn = document.getElementById("sendBtn");
const toast = document.getElementById("toast");

// ===== 小工具函数 =====

/** 在顶部弹一条提示，2.5 秒后自动消失。type 是 "error" 或 "success" */
function showToast(text, type = "error") {
  toast.textContent = text;
  toast.className = type; // CSS 里 .error 红底 / .success 绿底
  setTimeout(() => { toast.className = ""; }, 2500);
}

/**
 * 统一的接口请求封装：
 * 1. 自动把错误转换成友好提示（不再每个地方重复写错误处理）
 * 2. 后端返回 4xx/5xx 时，body 里的 detail 字段就是错误原因
 */
async function api(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({})); // 返回的不是 JSON 时给空对象兜底
  if (!resp.ok) {
    // 后端统一返回 {detail: "错误原因"}，直接抛给调用方
    throw new Error(data.detail || `请求失败（${resp.status}）`);
  }
  return data;
}

// ===== 渲染函数 =====

/** 把一条消息渲染成气泡，追加到聊天区底部 */
function appendMessage(role, content) {
  const msg = document.createElement("div");
  msg.className = "msg " + role;

  // 头像：用户显示"我"，AI 显示"销"
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "我" : "销";

  // 气泡：消息正文
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content; // textContent 不会把文字当 HTML 解析，安全

  msg.appendChild(avatar);
  msg.appendChild(bubble);
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight; // 滚到最新消息
}

/** 显示"AI 正在输入…"的小点动画，返回这个元素（回复到了就删掉它） */
function appendTyping() {
  const msg = document.createElement("div");
  msg.className = "msg assistant";
  msg.innerHTML =
    '<div class="avatar">销</div>' +
    '<div class="bubble typing-dots"><span></span><span></span><span></span></div>';
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
  return msg;
}

/** 渲染会话抽屉里的历史会话列表 */
function renderSessions(sessions, activeId) {
  if (sessions.length === 0) {
    sessionList.innerHTML = '<div class="empty">还没有历史会话，点"新对话"开始吧</div>';
    return;
  }
  sessionList.innerHTML = "";
  for (const s of sessions) {
    const item = document.createElement("button");
    item.className = "session-item" + (s.id === activeId ? " active" : "");

    // 标题 + 时间 + "已生成线索"标记（有线索卡片的会话带小徽标）
    const badge = s.has_lead ? '<span class="badge">已生成线索</span>' : "";
    item.innerHTML =
      `<div class="title">${escapeHtml(s.title)}${badge}</div>` +
      `<div class="time">${escapeHtml(s.created_at)}</div>`;

    // 点某个会话 → 切换到它（拉取并渲染它的全部消息）
    item.onclick = () => loadSession(s.id);
    sessionList.appendChild(item);
  }
}

/** 防止标题里出现 HTML 特殊字符破坏页面（转义成普通文字） */
function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/** 显示"线索已生成"的绿色提示条（自动生成或手动结束成功后调用） */
function showLeadNotice() {
  const notice = document.createElement("div");
  notice.className = "lead-notice";
  notice.innerHTML = '✅ 已生成线索卡片，<a href="/leads">点此查看</a>';
  chatArea.appendChild(notice);
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ===== 会话操作 =====

/** 加载某个会话：拉它的全部消息渲染出来，并把它设为当前会话 */
async function loadSession(id) {
  const data = await api(`/api/sessions/${id}/messages`);
  chatArea.innerHTML = "";
  // 空会话（还没说过话）也显示开场问候，和新建会话时的界面保持一致
  if (data.messages.length === 0) {
    appendMessage(
      "assistant",
      "您好！我是销售助理，很高兴为您服务。\n可以聊聊您想解决什么问题、大概的预算和时间安排吗？"
    );
  }
  for (const m of data.messages) appendMessage(m.role, m.content);
  // 如果这个会话已经有线索卡片，补一条提示（刷新页面后也能看到状态）
  const sessions = await api("/api/sessions").then((d) => d.sessions);
  if (sessions.find((s) => s.id === id)?.has_lead) showLeadNotice();
  currentSessionId = id;
  closeDrawer();
}

/** 新建会话：后端建一条记录，聊天区回到干净状态 */
async function newChat() {
  const data = await api("/api/sessions", { method: "POST" });
  currentSessionId = data.id;
  chatArea.innerHTML = "";
  appendMessage(
    "assistant",
    "您好！我是销售助理，很高兴为您服务。\n可以聊聊您想解决什么问题、大概的预算和时间安排吗？"
  );
  refreshSessionList();
  closeDrawer();
  msgInput.focus();
}

/** 刷新抽屉里的会话列表（带高亮当前会话） */
async function refreshSessionList() {
  const data = await api("/api/sessions");
  renderSessions(data.sessions, currentSessionId);
}

/** 关闭左侧抽屉 */
function closeDrawer() {
  drawer.classList.remove("open");
  drawerMask.classList.remove("open");
}

// ===== 发消息（核心流程） =====

async function sendMessage() {
  const content = msgInput.value.trim();
  if (!content) return;
  if (!currentSessionId) return;

  // 界面先显示用户消息 + "正在输入"，再等后端返回
  msgInput.value = "";
  sendBtn.disabled = true;
  appendMessage("user", content);
  const typing = appendTyping();

  try {
    // 一个请求完成"存消息 → AI 回复 → 可能自动生成线索卡片"三件事
    const data = await api(`/api/sessions/${currentSessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });

    typing.remove(); // 去掉"正在输入"动画
    appendMessage("assistant", data.reply);

    // 后端说这轮生成了线索卡片 → 提示用户 + 刷新会话列表的徽标
    if (data.lead) {
      showLeadNotice();
      refreshSessionList();
    }
  } catch (err) {
    typing.remove();
    showToast("发送失败：" + err.message);
  } finally {
    sendBtn.disabled = false; // 无论成功失败都要恢复按钮
    msgInput.focus();
  }
}

/** 手动结束对话：强制生成线索卡片（AI 没自动集齐信息时用这个兜底） */
async function endChat() {
  if (!currentSessionId) return;
  try {
    const data = await api(`/api/sessions/${currentSessionId}/end`, { method: "POST" });
    showLeadNotice();
    refreshSessionList();
    showToast("对话已结束，线索卡片已生成", "success");
  } catch (err) {
    showToast("结束对话失败：" + err.message);
  }
}

// ===== 事件绑定 =====
sendBtn.onclick = sendMessage;
msgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage(); // 回车发送
});
document.getElementById("newChatBtn").onclick = newChat;
document.getElementById("endBtn").onclick = endChat;
document.getElementById("menuBtn").onclick = () => {
  refreshSessionList(); // 每次打开抽屉前刷新列表，徽标才是最新的
  drawer.classList.add("open");
  drawerMask.classList.add("open");
};
drawerMask.onclick = closeDrawer;

// ===== 页面打开时：自动开始一个新对话 =====
newChat();
