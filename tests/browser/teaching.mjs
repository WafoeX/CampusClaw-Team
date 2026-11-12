// 真实浏览器中的草稿刷新与重新登录恢复；输入仅为隔离服务地址与合成密码。
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const origin = process.argv[2];
const password = process.env.CAMPUS_BROWSER_PASSWORD;
if (!origin || !password) throw Error("缺少隔离浏览器输入");
const wait = async (action) => {
  for (let attempt = 0; attempt < 120; attempt++) {
    const value = await action().catch(() => null);
    if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error("浏览器等待超时");
};
const port = (await wait(() => readFile("/tmp/teaching-browser/DevToolsActivePort", "utf8"))).split("\n")[0];
const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const socket = new WebSocket(pages.find(page => page.type === "page").webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let sequence = 0;
const pending = new Map();
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (message.method === "Page.javascriptDialogOpening") send("Page.handleJavaScriptDialog", { accept: true });
  const callback = pending.get(message.id);
  if (callback) { pending.delete(message.id); callback(message); }
});
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    pending.set(++sequence, message => message.error ? reject(Error(message.error.message)) : resolve(message.result));
    socket.send(JSON.stringify({ id: sequence, method, params }));
  });
}
async function js(expression) {
  const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw Error(result.exceptionDetails.text);
  return result.result.value;
}
const navigate = path => send("Page.navigate", { url: origin + path });
async function login(name) {
  await wait(() => js('!!document.getElementById("login-name")'));
  await js(`document.getElementById("login-name").value=${JSON.stringify(name)}; document.getElementById("password").value=${JSON.stringify(password)}; document.querySelector("button[type=submit]").click()`);
  await wait(() => js('location.pathname !== "/login"'));
}
async function api(path, method = "GET", data) {
  const expression = `fetch(${JSON.stringify(path)}, {method:${JSON.stringify(method)}, headers:{'Content-Type':'application/json','X-CampusClaw-Request':'same-origin'}, ${data === undefined ? "" : `body:JSON.stringify(${JSON.stringify(data)}),`} }).then(async r => ({status:r.status, body:await r.json()}))`;
  const result = await js(expression);
  assert.ok(result.status < 300, `${path}: ${JSON.stringify(result)}`);
  return result.body.data;
}

try {
  await send("Page.enable");
  await send("Page.bringToFront");
  await navigate("/login");
  await login("demo_a_teacher");
  const question = await api("/api/v1/questions", "POST", {
    kind: "single_choice", stem: "浏览器草稿恢复题", options: ["甲", "乙"],
    answer: "A", explanation: "合成解析", source_material_id: null,
  });
  await api(`/api/v1/questions/${question.id}/reviews`, "POST", { expected_version: 1 });
  const deadline = new Date(Date.now() + 7200000).toISOString();
  const answersOpen = new Date(Date.now() + 10800000).toISOString();
  const quiz = await api("/api/v1/quizzes", "POST", {
    title: "浏览器草稿恢复", chapter_id: null, deadline_at: deadline,
    answers_open_at: answersOpen, items: [{ question_id: question.id, points: 10 }],
  });
  await api(`/api/v1/quizzes/${quiz.id}/publications`, "POST", {});
  await api("/api/v1/auth/sessions/current", "DELETE");
  await navigate("/login");
  await login("demo_a_student");
  await navigate(`/quizzes/${quiz.id}`);
  await wait(() => js('document.querySelector("#quiz-items input[type=radio]") && document.getElementById("notice").textContent === "已加载。"'));
  await js('document.querySelector("#quiz-items input[type=radio]").click(); document.getElementById("save-draft").click()');
  await wait(() => js('document.getElementById("notice").textContent === "草稿已保存。"'));
  await send("Page.reload", { ignoreCache: true });
  await wait(() => js('document.getElementById("notice")?.textContent === "已加载。" && !!document.querySelector("#quiz-items input[type=radio]:checked")'));
  await api("/api/v1/auth/sessions/current", "DELETE");
  assert.equal(await js('fetch("/api/v1/auth/sessions/current").then(r => r.status)'), 401);
  await navigate(`/login?next=${encodeURIComponent(`/quizzes/${quiz.id}`)}`);
  await wait(() => js('location.pathname === "/login" && !!document.getElementById("login-name")'));
  await login("demo_a_student");
  await wait(() => js('location.pathname.startsWith("/quizzes/") && document.getElementById("notice")?.textContent === "已加载。" && !!document.querySelector("#quiz-items input[type=radio]:checked")'));
  const draft = await api(`/api/v1/quizzes/${quiz.id}/draft`);
  assert.deepEqual(Object.values(draft.answers), ["A"]);
  await navigate("/mistakes");
  await wait(() => js('document.getElementById("notice")?.textContent === "已加载。"'));
  assert.equal(await js('document.getElementById("summary-list").textContent.includes("答案尚未开放")'), true);
  await api("/api/v1/auth/sessions/current", "DELETE");
  await navigate("/login");
  await login("demo_a_teacher");
  await navigate("/console/dashboard");
  await wait(() => js('document.getElementById("notice")?.textContent === "已加载。"'));
  assert.equal(await js('document.getElementById("summary-list").textContent.includes("提交 0 / 1")'), true);
  console.log("TEACHING_BROWSER_OK: 刷新和重新登录后草稿恢复");
} finally {
  socket.close();
}
