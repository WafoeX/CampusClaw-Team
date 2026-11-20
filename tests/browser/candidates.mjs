// L10-N07 的既有候选题 202 链路；作业 202 仍由课程方确认。
import assert from "node:assert/strict";
import { readFile, writeFile, access, rename } from "node:fs/promises";

export async function candidates({api, request, navigate, js, wait, send, socket}) {
  const folder = "/tmp/browser-control/";
  const signal = async (name, value) => {
    await writeFile(folder + name + ".tmp", value);
    await rename(folder + name + ".tmp", folder + name);
  };
  const source = await api("/api/v1/materials", "POST", {
    title: "手机异步合成资料", text: "串联电路各处电流相等。",
  }, {"Idempotency-Key": "h5-async-source"});
  await signal("source", source.id);
  await wait(async () => { await access(folder + "indexed"); return true; });
  await navigate("/console/questions");
  await wait(() => js('!!document.getElementById("generation-form") && document.getElementById("notice").textContent === "已加载。"'));
  let acceptedStatus, polls = 0, posts = 0;
  const observe = ({data}) => {
    const message = JSON.parse(data);
    if (message.method !== "Network.responseReceived") return;
    const response = message.params.response;
    if (response.url.endsWith("/api/v1/question-generation-jobs")) {
      acceptedStatus = response.status;
      posts++;
    }
    if (response.url.includes("/api/v1/teaching-jobs/")) polls++;
  };
  socket.addEventListener("message", observe);
  try {
    await js(`{
      const form = document.getElementById("generation-form");
      form.elements.source_id.value = ${JSON.stringify(source.id)};
      form.elements.count.value = "1";
      form.querySelector("button[type=submit]").click();
    }`);
    await wait(() => js('document.getElementById("generation-status").textContent === "等待处理。"'));
    assert.equal(acceptedStatus, 202);
    const task = await js('new URL(location.href).searchParams.get("task")');
    assert.match(task, /^[0-9a-f-]{36}$/);
    const path = "/api/v1/teaching-jobs/" + task;
    const states = [(await api(path)).state];
    await signal("claim", task);
    await wait(() => js('document.getElementById("generation-status").textContent === "正在生成。"'));
    states.push((await api(path)).state);
    await signal("complete", task);
    await wait(() => js('document.getElementById("generation-status").textContent === "候选题已加入题库，等待审核。"'));
    const result = await api(path);
    states.push(result.state);
    assert.deepEqual(states, ["pending", "running", "succeeded"]);
    const question = await api("/api/v1/questions/" + result.result.question_ids[0]);
    assert.equal(question.origin, "ai");
    assert.equal(question.reviewed, false);
    assert.equal(question.source_snapshot.material_id, source.id);
    await wait(() => js('document.getElementById("question-list").textContent.includes("AI 候选")'));
    const terminalPolls = polls;
    await new Promise(resolve => setTimeout(resolve, 2500));
    assert.equal(polls, terminalPolls, "成功后应停止自动轮询");
    await send("Page.reload", {ignoreCache: true});
    await wait(() => js('document.getElementById("generation-status")?.textContent === "候选题已加入题库，等待审核。"'));
    assert.equal(await js('new URL(location.href).searchParams.get("task")'), task);
    assert.equal(posts, 1, "刷新应只查询既有任务");
    const persisted = await wait(async () => JSON.parse(await readFile(folder + "verified", "utf8")));
    assert.deepEqual(persisted, {task_id: task, outbox: 1, results: 1, drafts: 1});
    assert.equal((await request(path)).status, 200);
    console.log("H5_ASYNC_BROWSER_OK: candidate=202, states=pending/running/succeeded, refresh=readonly, batch=1");
    const auditLink = await js('document.getElementById("generation-audit-link")?.textContent');
    assert.ok(auditLink.includes(task), "题库页应展示同一任务 ID 的审计入口");
    assert.ok(
      await js('document.getElementById("generation-audit-link").href').then(href => href.endsWith('/console/audits?job_id=' + task)),
      "审计入口应指向按任务 ID 筛选的审计页",
    );
    await navigate("/console/audits?job_id=" + task);
    await wait(() => js('document.getElementById("audit-status").textContent.includes("已显示")'));
    const auditBody = await js('document.body.textContent');
    for (const word of ["手机异步合成资料", "串联电路各处电流相等", "正确", "错误", "prompt", "answer"]) {
      assert.ok(!auditBody.includes(word), "审计页面不得暴露题干、答案、资料正文或凭据：" + word);
    }
    assert.ok(auditBody.includes("受理候选题任务") && auditBody.includes("候选题任务结算"), "审计列表应含受理与终态事件");
    assert.ok(auditBody.includes(task), "审计列表应显示同一任务 ID");
    await js('document.querySelectorAll("#audit-list li button")[0].click()');
    await wait(() => js('!document.getElementById("audit-detail-panel").hidden'));
    const detailBody = await js('document.getElementById("audit-detail").textContent');
    for (const word of ["手机异步合成资料", "串联电路各处电流相等", "prompt"]) {
      assert.ok(!detailBody.includes(word), "审计详情不得暴露正文或凭据：" + word);
    }
    assert.ok(detailBody.includes("记录 ID：") && detailBody.includes(task), "审计详情应展示同一任务 ID 的元数据");
    console.log("H5_AUDIT_BROWSER_OK: audit link=task, list=admit+terminal, detail=metadata-only");
    return task;
  } finally {
    socket.removeEventListener("message", observe);
  }
}
