// 真实浏览器中的草稿刷新与重新登录恢复；输入仅为隔离服务地址与合成密码。
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { once } from "node:events";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { candidates } from "./candidates.mjs";
import { checkLoginTheme, checkStudentTheme } from "./student_theme.mjs";

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
let scriptAlerts = 0;
const pending = new Map();
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (message.method === "Page.javascriptDialogOpening") {
    if (message.params.type === "alert") scriptAlerts++;
    send("Page.handleJavaScriptDialog", { accept: true });
  }
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
async function request(path, method = "GET", data, headers = {}) {
  const requestHeaders = {"Content-Type": "application/json", "X-CampusClaw-Request": "same-origin", ...headers};
  const expression = `fetch(${JSON.stringify(path)}, {method:${JSON.stringify(method)}, headers:${JSON.stringify(requestHeaders)}, ${data === undefined ? "" : `body:JSON.stringify(${JSON.stringify(data)}),`} }).then(async r => ({status:r.status, body:await r.json()}))`;
  return js(expression);
}
async function api(path, method = "GET", data, headers = {}) {
  const result = await request(path, method, data, headers);
  assert.ok(result.status < 300, `${path}: ${JSON.stringify(result)}`);
  return result.body.data;
}

try {
  await send("Page.enable");
  await send("Page.bringToFront");
  await send("Emulation.setDeviceMetricsOverride", {
    mobile: true, width: 390, height: 844, deviceScaleFactor: 2,
  });
  await send("Network.enable", { maxPostDataSize: 0 });
  await navigate("/login");
  await checkLoginTheme({send, js, wait});
  await login("demo_a_teacher");
  assert.equal((await request("/live")).status, 200);
  assert.equal((await request("/health")).status, 200);
  const materialTitle = '实验记录 <script>alert(1)</script> <group-a> & "复测"';
  const material = await api("/api/v1/materials", "POST", {
    title: materialTitle, text: "合成讲义原文",
  }, {"Idempotency-Key": "browser-material-title"});
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
  const candidateTask = await candidates({api, request, navigate, js, wait, send, socket});
  await api("/api/v1/auth/sessions/current", "DELETE");
  await navigate("/login");
  await login("demo_a_student");
  const sessionPath = "/api/v1/auth/sessions/current";
  const studentSession = await request(sessionPath);
  assert.equal(studentSession.status, 200);
  assert.equal(studentSession.body.data.role, "student");
  assert.equal(await js("isSecureContext && innerWidth === 390"), true);
  await checkStudentTheme({origin, send, js, wait, navigate, socket});

  // SR-F08 防御性对照：资料标题由 JSON 传递，并在列表和详情中显示为纯文本。
  const materialPath = `/materials/${material.id}`;
  assert.equal((await api(`/api/v1/materials/${material.id}`)).title, materialTitle);
  for (const path of ["/materials", materialPath]) {
    const page = await js(`fetch(${JSON.stringify(path)}).then(async response => ({
      status: response.status,
      containsTitleMarker: (await response.text()).includes("group-a"),
    }))`);
    assert.deepEqual(page, {status: 200, containsTitleMarker: false});
  }
  await navigate("/materials");
  const materialLink = `document.querySelector(${JSON.stringify(`#materials a[href="${materialPath}"]`)})`;
  await wait(() => js(`!!${materialLink}`));
  assert.deepEqual(await js(`({text: ${materialLink}.textContent, elements: ${materialLink}.childElementCount})`), {
    text: materialTitle, elements: 0,
  });
  await js(`${materialLink}.click()`);
  await wait(() => js('document.getElementById("body")?.textContent === "合成讲义原文"'));
  assert.deepEqual(await js(`({
    text: document.getElementById("detail-title").textContent,
    elements: document.getElementById("detail-title").childElementCount,
  })`), {text: materialTitle, elements: 0});
  assert.equal(scriptAlerts, 0, "SR-F08 标题不得触发脚本弹窗");
  assert.equal(await js('document.querySelectorAll("#detail-title script").length'), 0);
  console.log("SR_F08_XSS_BROWSER_OK: script title=text, childElements=0, alert=0");
  console.log("MATERIAL_TITLE_BROWSER_OK: 页面模板和讲义标题纯文本渲染");

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
  let submissionStatus;
  const submissionUrl = origin + `/api/v1/quizzes/${quiz.id}/submissions`;
  function observeSubmission({ data }) {
    const message = JSON.parse(data);
    if (message.method === "Network.responseReceived" && message.params.response.url === submissionUrl) {
      submissionStatus = message.params.response.status;
      socket.removeEventListener("message", observeSubmission);
    }
  }
  socket.addEventListener("message", observeSubmission);
  await js('document.querySelectorAll("#quiz-items input[type=radio]")[1].click(); document.getElementById("submit-quiz").click()');
  await wait(() => js('document.getElementById("notice")?.textContent === "正式提交成功。"'));
  assert.equal(await wait(async () => submissionStatus), 201);
  assert.equal(await js('document.getElementById("submit-quiz").disabled'), true, "正式提交后按钮应保持禁用");
  assert.equal(await js('document.getElementById("save-draft").disabled'), true, "正式提交后草稿应只读");
  await navigate("/mistakes");
  await wait(() => js('document.getElementById("notice")?.textContent === "已加载。"'));
  assert.equal(await js('document.getElementById("summary-list").textContent.includes("答案尚未开放")'), true);
  await api("/api/v1/auth/sessions/current", "DELETE");
  await navigate("/login");
  await login("demo_a_teacher");
  await navigate("/console/dashboard");
  await wait(() => js('document.getElementById("notice")?.textContent === "已加载。"'));
  assert.equal(await js('document.getElementById("summary-list").textContent.includes("提交 1 / 1")'), true);
  await navigate(`/quizzes/${quiz.id}`);
  await wait(() => js('document.querySelector("#teacher-results input[type=number]") && document.getElementById("notice")?.textContent === "已加载。"'));
  await js('document.querySelector("#teacher-results input[type=number]").value="6"; document.querySelector("#teacher-results input[placeholder=\"填写改分理由\"]").value="浏览器复核"; document.querySelector("#teacher-results button").click()');
  await wait(() => js('document.getElementById("notice")?.textContent === "最终分已更新。"'));
  const overridden = (await api(`/api/v1/quizzes/${quiz.id}/submission-results`)).items[0];
  assert.deepEqual({rule: overridden.rule_score, final: overridden.score, source: overridden.score_source}, {rule: 0, final: 6, source: "teacher_override"});
  console.log("TEACHING_BROWSER_OK: 草稿恢复、正式提交、答案门控和看板统计");
  console.log("TEACHER_SCORE_OVERRIDE_BROWSER_OK: 390px 教师改分=6, 规则分=0");

  // L10-F07：在同一浏览器里比较合法来源、未登记来源及两个班的可见数据。
  const materialApi = `/api/v1/materials/${material.id}`;
  assert.equal((await api(materialApi)).id, material.id);
  const other = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end("<!doctype html><title>合成 H5 来源</title>");
  });
  other.listen(0, "127.0.0.1");
  try {
    await once(other, "listening");
    const otherOrigin = `http://127.0.0.1:${other.address().port}`;
    await send("Page.navigate", { url: otherOrigin });
    await wait(() => js(`location.origin === ${JSON.stringify(otherOrigin)}`));
    for (const [path, method] of [[materialApi, "GET"], [sessionPath, "DELETE"]]) {
      const result = await js(`fetch(${JSON.stringify(origin + path)}, {
        method: ${JSON.stringify(method)}, credentials: "include"
      }).then(() => "readable", error => error.name)`);
      assert.equal(result, "TypeError", `未登记来源应拒绝 ${method}`);
    }
  } finally {
    other.closeAllConnections();
    await new Promise(resolve => other.close(resolve));
  }
  await navigate("/materials");
  await wait(() => js(`location.origin === ${JSON.stringify(origin)} && location.pathname === "/materials"`));
  assert.equal((await api(sessionPath)).role, "teacher");
  await api(sessionPath, "DELETE");
  await navigate("/login");
  await login("demo_b_teacher");
  assert.notEqual((await api(sessionPath)).class_id, studentSession.body.data.class_id);
  const own = await api("/api/v1/materials", "POST", {
    title: "B 班合成讲义", text: "B 班合成内容",
  }, {"Idempotency-Key": "h5-class-b-material"});
  assert.equal((await api(`/api/v1/materials/${own.id}`)).id, own.id);
  const absent = await request(`/api/v1/materials/${randomUUID()}`);
  const denied = await request(materialApi);
  assert.equal(absent.status, 404);
  assert.equal(denied.status, 404);
  assert.equal(denied.body.code, 1300);
  delete absent.body.request_id;
  delete denied.body.request_id;
  assert.deepEqual(denied.body, absent.body);
  const foreignJob = await request(`/api/v1/teaching-jobs/${candidateTask}`);
  const missingJob = await request(`/api/v1/teaching-jobs/${randomUUID()}`);
  assert.equal(foreignJob.status, 404);
  assert.equal(missingJob.status, 404);
  assert.equal(foreignJob.body.code, 1300);
  delete foreignJob.body.request_id;
  delete missingJob.body.request_id;
  assert.deepEqual(foreignJob.body, missingJob.body);
  console.log("H5_BROWSER_CONTRACT_OK: 390px HTTPS, login=200, quiz=201, cross-origin=blocked, cross-class=404/1300");
} finally {
  socket.close();
}
