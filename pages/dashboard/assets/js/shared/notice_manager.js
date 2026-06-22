function createNoticeManager(deps) {
  const { t, textValue } = deps;

  function show(message, tone = "error") {
    const modal = document.getElementById("noticeModal");
    const messageNode = document.getElementById("noticeModalMessage");
    if (!modal || !messageNode) return;
    const text = textValue(message).trim() || t("request_failed");
    messageNode.textContent = text;
    messageNode.classList.toggle("is-error", tone === "error");
    messageNode.classList.toggle("is-success", tone === "success");
    modal.classList.add("open");
  }

  function close() {
    const modal = document.getElementById("noticeModal");
    const messageNode = document.getElementById("noticeModalMessage");
    if (messageNode) {
      messageNode.textContent = "";
      messageNode.classList.remove("is-error", "is-success");
    }
    if (modal) {
      modal.classList.remove("open");
    }
  }

  return { show, close };
}
