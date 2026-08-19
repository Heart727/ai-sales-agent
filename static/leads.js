/**
 * 线索管理页逻辑：拉取线索列表 → 渲染成卡片 → 支持删除。
 *
 * 用到的后端接口：
 *   GET    /api/leads           线索列表（最新的在前）
 *   DELETE /api/leads/{id}      删除一张线索卡片
 */

const leadsWrap = document.getElementById("leadsWrap");
const toast = document.getElementById("toast");

/** 顶部提示条（和聊天页一样的小工具） */
function showToast(text, type = "error") {
  toast.textContent = text;
  toast.className = type;
  setTimeout(() => { toast.className = ""; }, 2500);
}

/** 统一请求封装：非 2xx 状态自动把后端的 detail 转成错误抛出 */
async function api(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `请求失败（${resp.status}）`);
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
      leadsWrap.innerHTML =
        '<div class="empty-state">还没有线索。<br>去「返回对话」里和客户聊一聊，聊完线索会自动出现在这里。</div>';
      return;
    }
    leadsWrap.innerHTML = data.leads.map(cardHtml).join("");

    // 给每张卡片的删除按钮绑事件
    leadsWrap.querySelectorAll(".lead-card").forEach((card) => {
      card.querySelector(".delete-btn").onclick = () => deleteLead(card);
    });
  } catch (err) {
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
    showToast("已删除", "success");
    // 删光了就重新渲染，显示空状态提示
    if (leadsWrap.querySelectorAll(".lead-card").length === 0) loadLeads();
  } catch (err) {
    showToast("删除失败：" + err.message);
  }
}

// 页面打开就加载
loadLeads();
