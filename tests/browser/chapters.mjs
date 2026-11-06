import { readFile, writeFile } from "node:fs/promises";
import assert from "node:assert/strict";

const [profile, origin, output] = process.argv.slice(2);
async function eventually(action) {
  for (let i = 0; i < 120; i++) {
    const value = await action().catch(() => null);
    if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error("浏览器等待超时");
}
const activePort = await eventually(() => readFile(profile + "/DevToolsActivePort", "utf8"));
const targets = await (await fetch("http://127.0.0.1:" + activePort.split("\n")[0] + "/json")).json();
const socket = new WebSocket(targets.find(entry => entry.type === "page").webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, {once:true});
  socket.addEventListener("error", reject, {once:true});
});
let sequence = 0, paused, pausedPayload;
const pending = new Map();
socket.addEventListener("message", ({data}) => {
  const result = JSON.parse(data);
  if (result.method === "Fetch.requestPaused") {paused = result.params.requestId; pausedPayload = result.params.request.postData;}
  if (result.method === "Page.javascriptDialogOpening") send("Page.handleJavaScriptDialog", {accept:true});
  const handler = pending.get(result.id);
  if (handler) { pending.delete(result.id); handler(result); }
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
  pending.set(++sequence, result => result.error ? reject(Error(result.error.message)) : resolve(result.result));
  socket.send(JSON.stringify({id:sequence, method, params}));
});
async function js(expression) {
  const value = await send("Runtime.evaluate", {expression, returnByValue:true, awaitPromise:true});
  if (value.exceptionDetails) throw Error(value.exceptionDetails.text);
  return value.result.value;
}
const navigate = path => send("Page.navigate", {url:origin + path});
const key = async value => {
  await send("Input.dispatchKeyEvent", {type:value === "Enter" ? "keyDown" : "rawKeyDown", key:value, code:value, text:value === "Enter" ? "\r" : "", unmodifiedText:value === "Enter" ? "\r" : "", windowsVirtualKeyCode:value === "Enter" ? 13 : 9});
  await send("Input.dispatchKeyEvent", {type:"keyUp", key:value, code:value});
};
async function login(name) {
  await eventually(() => js('!!document.getElementById("login-name")'));
  await js('document.getElementById("login-name").value = ' + JSON.stringify(name)
    + '; document.getElementById("password").value = ' + JSON.stringify(process.env.CAMPUS_BROWSER_PASSWORD)
    + '; document.querySelector("button[type=submit]").focus()');
  await js('document.querySelector("button[type=submit]").click()');
  try {
    await eventually(() => js('location.pathname === "/chapters" && !!document.getElementById("chapter-status")'));
  } catch (error) {
    console.error(await js('({path:location.pathname,feedback:document.getElementById("feedback")?.textContent})'));
    throw error;
  }
}
const ready = () => eventually(() => js('document.getElementById("chapter-status")?.textContent.includes("另有未分类") && document.getElementById("chapter-material-status")?.textContent.includes("暂无资料")'));
const screenshot = async filename => {
  const {data} = await send("Page.captureScreenshot", {format:"png"});
  await writeFile(output + "/" + filename, Buffer.from(data, "base64"));
};

try {
  await send("Page.enable");
  await send("Page.bringToFront");
  await send("Emulation.setDeviceMetricsOverride", {width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await navigate("/chapters");
  await eventually(() => js('location.pathname === "/login" && !!document.getElementById("login-name")'));
  assert.equal(await js('new URLSearchParams(location.search).get("next")'), "/chapters");
  await login("demo_a_teacher");
  await ready();
  assert.equal(await js('document.querySelector("#chapters button").textContent'), "未分类");

  // 真实页面先显示加载态，再注入可恢复依赖故障并用键盘重试。
  await send("Fetch.enable", {patterns:[{urlPattern:origin + "/api/v1/chapters",requestStage:"Request"}]});
  await send("Page.reload");
  await eventually(async () => paused);
  assert.equal(await js('document.getElementById("chapter-status").textContent'), "正在加载章节…");
  await send("Fetch.fulfillRequest", {requestId:paused,responseCode:503,responseHeaders:[{name:"Content-Type",value:"application/json"}],
    body:Buffer.from(JSON.stringify({code:1500,message:"依赖暂不可用，请重试",data:null,request_id:"browser-fault"})).toString("base64")});
  await send("Fetch.disable");
  await eventually(() => js('!document.getElementById("chapter-retry").hidden'));
  assert.ok(await js('document.getElementById("chapter-status").textContent.includes("browser-fault")'));
  await js('document.getElementById("chapter-retry").focus()');
  await key("Enter");
  await ready();

  await js('document.querySelector("#chapter-create input[name=name]").focus()');
  await send("Input.insertText", {text:"键盘章节"});
  await key("Tab");
  assert.equal(await js('document.activeElement.name'), "sort_order");
  await key("Tab");
  assert.equal(await js('document.activeElement.textContent'), "创建章节");
  await key("Enter");
  await eventually(() => js('document.getElementById("notice").textContent === "章节已创建。"'));
  await js('document.querySelector("#chapters button").focus()');
  await key("Enter");
  await eventually(() => js('document.getElementById("notice").textContent.includes("正在查看键盘章节")'));
  assert.equal(await js('document.querySelector("#chapters button[aria-pressed=true]").textContent'), "键盘章节");

  // 上传真实资料后从未分类归类，学生在章节内打开原文。
  await js(`(async () => {
    const result = await fetch('/api/v1/materials', {method:'POST',headers:{'Content-Type':'application/json','X-CampusClaw-Request':'same-origin','Idempotency-Key':'browser-material'},body:JSON.stringify({title:'章节原文',text:'章节功能验证正文'})});
    if (result.status !== 201) throw Error('资料创建失败');
  })()`);
  await navigate("/chapters");
  await eventually(() => js('!!document.querySelector("#chapter-materials select")'));
  await js('const select = document.querySelector("#chapter-materials select"); select.value = [...select.options].find(o => o.text === "键盘章节").value; select.dispatchEvent(new Event("change")); document.querySelector("#chapter-materials button").click()');
  await eventually(() => js('document.getElementById("notice").textContent === "资料已归类。"'));
  await js('document.querySelector("#chapters button").click()');
  await eventually(() => js('!!document.querySelector("#chapter-materials a")'));
  await screenshot("chapters-desktop.png");
  await send("Emulation.setDeviceMetricsOverride", {width:390,height:844,deviceScaleFactor:1,mobile:false});
  assert.equal(await js('document.documentElement.scrollWidth <= innerWidth'), true);
  await screenshot("chapters-mobile.png");
  await js('document.getElementById("logout").click()');
  await eventually(() => js('location.pathname === "/login"'));
  await navigate("/chapters");
  await login("demo_a_student");
  await eventually(() => js('!!document.querySelector("#chapters button")'));
  assert.equal(await js('document.getElementById("chapter-create")'), null);
  await js('document.querySelector("#chapters button").focus()');
  await key("Enter");
  await eventually(() => js('!!document.querySelector("#chapter-materials a")'));
  assert.equal(await js('document.querySelector("#chapter-materials select")'), null);
  await js('document.querySelector("#chapter-materials a").focus()');
  await key("Enter");
  await eventually(() => js('document.getElementById("body")?.textContent === "章节功能验证正文"'));
  await screenshot("student-source-mobile.png");
  await js('document.getElementById("logout").click()');
  await eventually(() => js('location.pathname === "/login"'));
  await navigate("/chapters");
  await login("demo_a_teacher");
  await ready();
  await js('const name = document.querySelector("#chapters input"); name.value="改名后的章节"; name.dispatchEvent(new Event("input")); document.querySelector("#chapters .row button").click()');
  await eventually(() => js('document.getElementById("notice").textContent === "章节已更新。"'));
  assert.equal(await js('document.querySelector("#chapters button").textContent'), "改名后的章节");
  await js('document.querySelectorAll("#chapters .row button")[1].click()');
  await eventually(() => js('document.getElementById("notice").textContent.includes("章节已删除")'));
  assert.equal(await js('document.querySelector("#chapters button").textContent'), "未分类");
  assert.equal(await js('document.querySelector("#chapter-materials a").textContent'), "章节原文");
  // 空模型 key 是明确的依赖失败，不调用外部网关；验证关键词就绪及新键重试。
  await navigate("/console");
  await eventually(() => js('[...document.querySelectorAll("#materials button")].some(b => b.textContent === "构建或重试索引")'));
  await js('[...document.querySelectorAll("#materials button")].find(b => b.textContent === "查询索引状态").click()');
  await eventually(() => js('document.querySelector("#materials .status").textContent === "尚未构建索引。"'));
  await js('[...document.querySelectorAll("#materials button")].find(b => b.textContent === "构建或重试索引").focus()');
  await key("Enter");
  await eventually(() => js('document.querySelector("#materials .status").textContent.includes("关键词就绪")'));
  await js('[...document.querySelectorAll("#materials button")].find(b => b.textContent === "构建或重试索引").click()');
  await eventually(() => js(`(async () => {
    const id = document.querySelector('#materials a').getAttribute('href').split('/').at(-1);
    const result = await fetch('/api/v1/materials/'+id+'/index-builds').then(r => r.json());
    return result.data.items.length === 2 && result.data.items[0].status === 'keyword_only';
  })()`));
  assert.equal(await js('document.documentElement.scrollWidth <= innerWidth'), true);
  await screenshot("index-build-mobile.png");
  await send("Emulation.setDeviceMetricsOverride", {width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await screenshot("index-build-desktop.png");
  const browserSource = "😀" + "填充文字。".repeat(130) + "\n\n星河礼堂每周二开放。";
  await js(`(async () => {
    const created = await fetch('/api/v1/materials',{method:'POST',headers:{'Content-Type':'application/json','X-CampusClaw-Request':'same-origin','Idempotency-Key':'browser-codepoints'},body:JSON.stringify({title:'码点验证原文',text:${JSON.stringify(browserSource)}})}).then(r=>r.json());
    const result = await fetch('/api/v1/materials/'+created.data.id+'/index-builds',{method:'POST',headers:{'Content-Type':'application/json','X-CampusClaw-Request':'same-origin','Idempotency-Key':'browser-codepoint-index'},body:'{}'});
    if (result.status !== 503) throw Error('空 key 应明确报依赖失败');
  })()`);
  await navigate("/search");
  await eventually(() => js('!!document.getElementById("search-form") && !document.getElementById("search-scope").disabled'));
  await send("Fetch.enable", {patterns:[{urlPattern:origin+"/api/v1/searches",requestStage:"Request"}]});
  paused = undefined;
  await js('document.getElementById("search-query").value="星河礼堂";document.querySelector("#search-form button").focus()');
  await key("Enter");
  await eventually(async () => paused);
  assert.equal(await js('document.getElementById("search-status").textContent'), "正在检索资料…");
  await send("Fetch.fulfillRequest",{requestId:paused,responseCode:503,responseHeaders:[{name:"Content-Type",value:"application/json"}],body:Buffer.from(JSON.stringify({code:1500,message:"合成依赖失败",data:null,request_id:"browser-synthetic"})).toString("base64")});
  await eventually(() => js('!document.getElementById("search-retry").hidden'));
  await send("Fetch.disable");
  await js('document.getElementById("search-retry").click()');
  await eventually(() => js('document.querySelectorAll("#search-results li").length === 1'));
  await js('document.querySelector("#search-results button").focus()');
  await key("Enter");
  await eventually(() => js('!!document.querySelector("#citation-source mark")'));
  assert.equal(await js('document.querySelector("#citation-source mark").textContent === document.querySelector("#search-results pre").textContent'), true);
  assert.equal(await js('document.getElementById("citation-source").textContent'), browserSource);
  await screenshot("search-citation-desktop.png");
  await send("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:false});
  assert.equal(await js('document.documentElement.scrollWidth <= innerWidth'), true);
  await screenshot("search-citation-mobile.png");
  await js('document.getElementById("search-mode").value="vector";document.querySelector("#search-form button").click()');
  await eventually(() => js('document.getElementById("search-status").textContent.includes("关键词") && !document.getElementById("search-retry").hidden'));
  await js('document.getElementById("search-mode").value="keyword";document.getElementById("search-query").value="珊瑚天文台不存在编号";document.querySelector("#search-form button").click()');
  await eventually(() => js('document.getElementById("search-status").textContent.includes("资料中未找到相关内容")'));
  const citationFixture = await js(`(async () => {
    const result = await fetch('/api/v1/searches',{method:'POST',headers:{'Content-Type':'application/json','X-CampusClaw-Request':'same-origin'},body:JSON.stringify({query:'星河礼堂',mode:'keyword'})}).then(r=>r.json());
    return result.data.items[0];
  })()`);
  await navigate("/ask");
  await eventually(() => js('!!document.getElementById("answer-text") && !document.getElementById("search-scope").disabled'));
  assert.equal(await js('document.getElementById("search-mode").value'), "hybrid");
  await send("Fetch.enable",{patterns:[{urlPattern:origin+"/api/v1/material-answers",requestStage:"Request"}]});
  paused = undefined;
  await js('document.getElementById("search-mode").value="keyword";document.getElementById("search-query").value="星河礼堂何时开放？";document.querySelector("#search-form button").focus()');
  await key("Enter");
  await eventually(async () => paused);
  assert.deepEqual(JSON.parse(pausedPayload), {question:"星河礼堂何时开放？",mode:"keyword"});
  await send("Fetch.fulfillRequest",{requestId:paused,responseCode:200,responseHeaders:[{name:"Content-Type",value:"application/json"}],body:Buffer.from(JSON.stringify({code:0,message:"成功",data:{answer:"星河礼堂每周二开放。",citations:[{...citationFixture,number:1}]},request_id:"browser-answer-fixture"})).toString("base64")});
  await eventually(() => js('document.getElementById("answer-text").textContent === "星河礼堂每周二开放。"'));
  await send("Fetch.disable");
  await js('document.querySelector("#search-results button").focus()');
  await key("Enter");
  await eventually(() => js('!!document.querySelector("#citation-source mark")'));
  await send("Emulation.setDeviceMetricsOverride",{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await screenshot("answer-citation-desktop.png");
  await send("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:false});
  assert.equal(await js('document.documentElement.scrollWidth <= innerWidth'), true);
  await screenshot("answer-citation-mobile.png");
  await js('document.getElementById("search-query").value="珊瑚天文台不存在编号";document.querySelector("#search-form button").click()');
  await eventually(() => js('document.getElementById("answer-text").textContent === "资料中未找到相关内容"'));
  assert.equal(await js('document.querySelectorAll("#search-results li").length'),0);
  await js('document.getElementById("search-query").value="星河礼堂何时开放？";document.querySelector("#search-form button").click()');
  await eventually(() => js('document.getElementById("search-status").textContent.includes("模型") && !document.getElementById("search-retry").hidden'));
  assert.equal(await js('document.getElementById("answer-text").hidden'),true);
  await writeFile(output + "/result.json", JSON.stringify({passed:true,widths:[1440,390],checks:["登录返回","四态与故障重试","键盘创建与浏览","选中状态","真实资料归类","学生只读与原文","教师改名与删章归回未分类","索引空状态与键盘构建","缺模型密钥保留关键词","失败后新键重试","检索四态与503重试","码点出处高亮","问答默认混合与当前问题","显式HTTP回答夹具及授权出处","真实后端无证据拒答","模型故障不显示旧回答"]},null,2));
  console.log("章节浏览器主路径通过：键盘、四态、归类、学生原文和两档宽度");
} finally {
  socket.close();
}
