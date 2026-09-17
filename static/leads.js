/**
 * 线索管理页逻辑：拉取线索列表 → 渲染成卡片 → 支持删除。
 *
 * ⚠️ 本页需要登录：打开时先调 /api/auth/me 检查登录状态，
 * 未登录（401）自动跳转到登录页。线索的增删接口后端也会二次校验，
 * 前端跳转只是体验，真正的安全由后端保证。
 *
 * 用到的后端接口：
 *   GET    /api/auth/me         当前登录用户（未登录返回 401）
 *   POST   /api/auth/logout     登出
 *   GET    /api/leads           线索列表（需登录）
 *   DELETE /api/leads/{id}      删除一张线索卡片（需登录）
 */

const leadsWrap = document.getElementById("leadsWrap");
const leadGrid = document.getElementById("leadGrid");
const leadCount = document.getElementById("leadCount");
const toast = document.getElementById("toast");
const userName = document.getElementById("userName");
const logoutBtn = document.getElementById("logoutBtn");

/** 顶部提示条（和聊天页一样的小工具） */
function showToast(text, type = "error") {
  toast.textContent = text;
  toast.className = type;
  setTimeout(() => { toast.className = ""; }, 2500);
}

/** 统一请求封装：非 2xx 状态自动把后端的 detail 转成错误抛出（附上状态码） */
async function api(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const e = new Error(data.detail || `请求失败（${resp.status}）`);
    e.status = resp.status;
    throw e;
  }
  return data;
}

/** 防止线索内容里的特殊字符破坏页面（统一转义） */
function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/** 把一张线索卡片渲染成 HTML（一行信息 = 左边标签 + 右边内容） */
function cardHtml(lead) {
  const rows = [
    ["需求", lead.requirement],
    ["预算", lead.budget],
    ["时间", lead.timeline],
    ["联系方式", lead.contact],
    ["跟进摘要", lead.summary],
  ];
  const rowsHtml = rows
    .map(
      ([label, value]) =>
        `<div class="row"><span class="label">${label}</span>` +
        `<span class="value">${escapeHtml(value)}</span></div>`
    )
    .join("");

  return (
    `<div class="lead-card" data-id="${lead.id}">` +
    `<div class="head">` +
    `<span class="summary">${escapeHtml(lead.requirement)}</span>` +
    `<button class="delete-btn">删除</button>` +
    `</div>` +
    `<div class="time">生成时间：${escapeHtml(lead.created_at)}</div>` +
    rowsHtml +
    `</div>`
  );
}

/** 拉取并渲染全部线索 */
async function loadLeads() {
  try {
    const data = await api("/api/leads");
    if (data.leads.length === 0) {
      leadCount.textContent = "0";
      leadGrid.innerHTML =
        '<div class="empty-state empty-card"><div class="empty-icon">✦</div><strong>还没有线索</strong><span>返回对话页和客户聊一聊，完成接待后线索会出现在这里。</span><a class="btn primary" href="/">开始一轮接待</a></div>';
      return;
    }
    leadCount.textContent = data.leads.length;
    leadGrid.innerHTML = data.leads.map(cardHtml).join("");

    // 给每张卡片的删除按钮绑事件
    leadGrid.querySelectorAll(".lead-card").forEach((card) => {
      card.querySelector(".delete-btn").onclick = () => deleteLead(card);
    });
  } catch (err) {
    // 未登录/登录过期：跳去登录页
    if (err.status === 401) {
      location.href = "/login";
      return;
    }
    leadsWrap.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(err.message)}</div>`;
  }
}

/** 删除一张线索卡片（先弹确认框，防止手滑误删） */
async function deleteLead(card) {
  const id = card.dataset.id;
  if (!confirm(`确定删除这条线索吗？（会话 ${id} 的线索）`)) return;
  try {
    await api(`/api/leads/${id}`, { method: "DELETE" });
    card.remove(); // 从页面上拿掉这张卡片
    leadCount.textContent = String(Math.max(0, Number(leadCount.textContent) - 1));
    showToast("已删除", "success");
    // 删光了就重新渲染，显示空状态提示
    if (leadGrid.querySelectorAll(".lead-card").length === 0) loadLeads();
  } catch (err) {
    if (err.status === 401) {
      location.href = "/login";
      return;
    }
    showToast("删除失败：" + err.message);
  }
}

// 登出按钮：调登出接口（后端删除令牌）→ 回登录页
logoutBtn.onclick = async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (err) {
    /* 登出失败也照常跳登录页（本地 cookie 失效即可） */
  }
  location.href = "/login";
};

// 页面打开：先检查登录状态 → 已登录显示用户名并加载线索；未登录跳登录页
(async () => {
  try {
    const me = await api("/api/auth/me");
    userName.textContent = me.username;
    loadLeads();
  } catch (err) {
    location.href = "/login";
  }
})();
