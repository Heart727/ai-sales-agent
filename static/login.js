/**
 * 登录页逻辑：登录 / 注册两个标签切换，成功后跳转到线索管理页。
 *
 * 用到的后端接口：
 *   GET  /api/auth/me       判断当前是否已登录（已登录就直接进线索页）
 *   POST /api/auth/login    登录
 *   POST /api/auth/register 注册（成功后自动登录）
 *
 * 登录的原理：后端校验通过后，会在浏览器里存一个 cookie（登录令牌），
 * 之后打开 /leads 时浏览器自动带上，后端就认得你了。
 */

const tabLogin = document.getElementById("tabLogin");
const tabRegister = document.getElementById("tabRegister");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const authError = document.getElementById("authError");

/** 统一请求封装：非 2xx 时把后端的 detail 转成错误抛出 */
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

/** 在卡片下方显示错误文字 */
function showError(text) {
  authError.textContent = text;
  authError.className = "show";
}

/** 切换登录/注册标签 */
function switchTab(showLogin) {
  tabLogin.classList.toggle("active", showLogin);
  tabRegister.classList.toggle("active", !showLogin);
  loginForm.hidden = !showLogin;
  registerForm.hidden = showLogin;
  authError.className = "";
}

// 标签点击事件
tabLogin.onclick = () => switchTab(true);
tabRegister.onclick = () => switchTab(false);

// 登录表单提交
loginForm.onsubmit = async (e) => {
  e.preventDefault(); // 阻止浏览器默认刷新页面的行为
  authError.className = "";
  const fd = new FormData(loginForm);
  try {
    await api("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: fd.get("username"), password: fd.get("password") }),
    });
    location.href = "/leads"; // 登录成功 → 进线索页
  } catch (err) {
    showError(err.message);
  }
};

// 注册表单提交
registerForm.onsubmit = async (e) => {
  e.preventDefault();
  authError.className = "";
  const fd = new FormData(registerForm);
  try {
    await api("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: fd.get("username"),
        password: fd.get("password"),
        signup_code: fd.get("signup_code"),
      }),
    });
    location.href = "/leads"; // 注册成功即已登录 → 进线索页
  } catch (err) {
    showError(err.message);
  }
};

// 页面打开时：如果已经登录过了，直接进线索页，不用再输密码
(async () => {
  try {
    await api("/api/auth/me");
    location.href = "/leads";
  } catch (err) {
    /* 未登录，留在本页正常显示登录表单 */
  }
})();
