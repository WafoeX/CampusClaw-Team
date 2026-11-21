import assert from "node:assert/strict";

const viewport = (send, width) => send("Emulation.setDeviceMetricsOverride", {
  width, height: 900, deviceScaleFactor: 1, mobile: width === 390,
});

async function checkContrast(js, foreground, background) {
  const ratio = await js(`(() => {
    const luminance = color => {
      const channels = color.match(/\\d+/g).slice(0, 3).map(channel => {
        const value = Number(channel) / 255;
        return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
      });
      return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
    };
    const text = luminance(getComputedStyle(document.querySelector(${JSON.stringify(foreground)})).color);
    const surface = luminance(getComputedStyle(document.querySelector(${JSON.stringify(background)})).backgroundColor);
    return (Math.max(text, surface) + .05) / (Math.min(text, surface) + .05);
  })()`);
  assert.ok(ratio >= 4.5, `${foreground} / ${background}: ${ratio.toFixed(2)}:1`);
}

async function checkViewport(js, width) {
  assert.equal(await js("innerWidth"), width);
  assert.ok(await js("document.documentElement.scrollWidth <= innerWidth"), `${width}px 横向溢出`);
}

async function tabFromPage(send, js, selector) {
  await send("Input.dispatchKeyEvent", {type: "rawKeyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9});
  await send("Input.dispatchKeyEvent", {type: "keyUp", key: "Tab", code: "Tab"});
  assert.ok(await js(`document.activeElement.matches(${JSON.stringify(selector)}) && document.activeElement.matches(":focus-visible") && getComputedStyle(document.activeElement).outlineStyle === "solid" && parseFloat(getComputedStyle(document.activeElement).outlineWidth) >= 2`));
}

export async function checkLoginTheme({send, js, wait}) {
  await wait(() => js('!!document.getElementById("login-name")'));
  for (const width of [1440, 390]) {
    await viewport(send, width);
    await checkViewport(js, width);
  }
  await checkContrast(js, ".hint", ".sign-in");
  await checkContrast(js, "#sign-in button", "#sign-in button");
  await tabFromPage(send, js, "#login-name");
  await js(`document.getElementById("login-name").value = "demo_a_teacher";
    document.getElementById("password").value = "InvalidThemeTestPassword";
    document.querySelector("#sign-in button").click()`);
  await wait(() => js('document.getElementById("feedback").hasAttribute("data-error") && !document.querySelector("#sign-in button").disabled'));
  assert.match(await js('document.getElementById("feedback").textContent'), /请重试/);
  await checkContrast(js, "#feedback", "#feedback");
}

export async function checkStudentTheme({origin, send, js, wait, navigate, socket}) {
  for (const [path, heading] of [["/materials", "班级资料"], ["/ask", "资料问答"], ["/quizzes", "班级测验"]]) {
    await navigate(path);
    const active = `nav a[aria-current=page][href="${path}"]`;
    await wait(() => js(`location.pathname === ${JSON.stringify(path)} && !!document.querySelector(${JSON.stringify(active)})`));
    assert.equal(await js('document.querySelector(".page-intro h1").textContent'), heading);
    assert.equal(await js(`document.querySelector('nav a[href="/console"]') === null`), true);
    assert.ok(await js(`parseFloat(getComputedStyle(document.querySelector(${JSON.stringify(active)})).borderInlineStartWidth) >= 3`));
    await checkContrast(js, active, active);
    for (const width of [1440, 390]) {
      await viewport(send, width);
      await checkViewport(js, width);
    }
    await tabFromPage(send, js, "nav a:first-child");
  }
  assert.equal(await js('fetch("/console", {redirect:"manual"}).then(r => r.status)'), 403);

  await navigate("/search");
  await wait(() => js('location.pathname === "/search" && document.getElementById("search-scope")?.disabled === false'));
  await js(`document.getElementById("search-query").value = "无匹配的合成检索编号";
    document.querySelector("#search-form button").click()`);
  await wait(() => js('document.getElementById("search-status").textContent.includes("资料中未找到相关内容")'));
  assert.equal(await js('document.querySelectorAll("#search-results li").length'), 0);
  await checkContrast(js, "#search-status", 'section[aria-labelledby="search-title"]');

  let paused;
  function observe({data}) {
    const event = JSON.parse(data);
    if (event.method === "Fetch.requestPaused") paused = event.params.requestId;
  }
  socket.addEventListener("message", observe);
  try {
    await send("Fetch.enable", {patterns: [{urlPattern: origin + "/api/v1/searches"}]});
    await js('document.querySelector("#search-form button").click()');
    const requestId = await wait(async () => paused);
    assert.equal(await js('document.querySelector("#search-form button").disabled'), true);
    await send("Fetch.fulfillRequest", {
      requestId,
      responseCode: 503,
      responseHeaders: [{name: "Content-Type", value: "application/json"}],
      body: Buffer.from(JSON.stringify({code: 1500, message: "合成检索依赖故障，请重试", request_id: "theme-browser"})).toString("base64"),
    });
    await wait(() => js('!document.getElementById("search-retry").hidden && !document.querySelector("#search-form button").disabled'));
    assert.match(await js('document.getElementById("search-status").textContent'), /请重试/);
    await checkContrast(js, "#search-status", "#search-status");
  } finally {
    await send("Fetch.disable");
    socket.removeEventListener("message", observe);
  }
  console.log("STUDENT_THEME_BROWSER_OK: login, navigation, 390/1440 widths, contrast, keyboard, empty and retry");
}
