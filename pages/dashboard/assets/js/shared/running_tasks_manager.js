function createRunningTasksManager(deps) {
  const { t, escapeHtml, getActiveTestTaskId, onViewTaskClick } = deps;

  let taskSeq = 0;
  const runningTasks = [];
  let panelOpen = false;
  let outsideCloseBound = false;

  function buildTestStatsText(stats) {
    const completed = Math.max(0, Number(stats?.completed || 0));
    const total = Math.max(0, Number(stats?.total || 0));
    const success = Math.max(0, Number(stats?.success || 0));
    const fail = Math.max(0, Number(stats?.fail || 0));
    return `${t("test_stats_runs", { completed, total })} | ${t("test_stats_success", { count: success })} | ${t("test_stats_fail", { count: fail })}`;
  }

  function updateTestStats(stats = null) {
    const node = document.getElementById("testProgressText");
    if (!node) return;
    if (!stats) {
      node.textContent = "";
      return;
    }
    node.textContent = buildTestStatsText(stats);
  }

  function createRunningTask(kind, title, extra = {}) {
    const id = `task_${Date.now()}_${++taskSeq}`;
    const task = {
      id,
      kind,
      title: title || kind,
      running: true,
      completed: 0,
      total: 0,
      success: 0,
      fail: 0,
      summary: "",
      ...extra,
    };
    runningTasks.push(task);
    renderRunningTasks();
    return task;
  }

  function getRunningTask(taskId) {
    return runningTasks.find((task) => task.id === taskId) || null;
  }

  function patchRunningTask(taskId, patch = {}) {
    const task = getRunningTask(taskId);
    if (!task) return null;
    Object.assign(task, patch);
    renderRunningTasks();
    if (getActiveTestTaskId() === taskId) {
      updateTestStats(task);
    }
    return task;
  }

  function finishRunningTask(taskId, patch = {}) {
    const task = getRunningTask(taskId);
    if (!task) return;
    Object.assign(task, patch, { running: false });
    renderRunningTasks();
  }

  function bindOutsideClose() {
    if (outsideCloseBound) return;
    outsideCloseBound = true;
    document.addEventListener("click", (event) => {
      if (!panelOpen) return;
      const fab = document.getElementById("runningTasksFab");
      if (!fab) return;
      if (fab.contains(event.target)) return;
      panelOpen = false;
      renderRunningTasks();
    });
  }

  function onToggleRunningTasksPanel() {
    const active = runningTasks.filter((task) => task.running);
    if (!active.length) {
      panelOpen = false;
      renderRunningTasks();
      return;
    }
    panelOpen = !panelOpen;
    renderRunningTasks();
  }

  function renderRunningTasks() {
    bindOutsideClose();
    const fab = document.getElementById("runningTasksFab");
    const bar = document.getElementById("runningTasksBar");
    const toggle = document.getElementById("runningTasksToggle");
    const countNode = document.getElementById("runningTasksCount");
    if (!fab || !bar || !toggle || !countNode) return;
    const active = runningTasks.filter((task) => task.running);
    countNode.textContent = String(active.length);
    const toggleLabel = `${t("running_tasks")} (${active.length})`;
    toggle.title = toggleLabel;
    toggle.setAttribute("aria-label", toggleLabel);
    if (!active.length) {
      panelOpen = false;
      fab.classList.remove("open");
      fab.classList.remove("expanded");
      bar.innerHTML = "";
      return;
    }
    fab.classList.add("open");
    fab.classList.toggle("expanded", panelOpen);
    const chips = active
      .map(
        (task) => `
        <span class="running-task-chip">
          <strong>${escapeHtml(task.title)}</strong>
          <span>${escapeHtml(buildTestStatsText(task))}</span>
          <button type="button" class="btn-square" onclick="onViewTaskClick('${task.id}')">${escapeHtml(t("view"))}</button>
        </span>
      `
      )
      .join("");
    bar.innerHTML = `
        <div class="running-tasks-row">
          <strong>${escapeHtml(t("running_tasks"))}</strong>
          ${chips}
        </div>
      `;
  }

  return {
    buildTestStatsText,
    updateTestStats,
    createRunningTask,
    getRunningTask,
    patchRunningTask,
    finishRunningTask,
    onToggleRunningTasksPanel,
    renderRunningTasks,
  };
}
