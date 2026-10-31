// メール仕分けの画面の動き。Python（app.py の Api）は window.pywebview.api から呼ぶ。
// pywebview.api は window.onload では間に合わないことがあるので、pywebviewready を待つ（pywebview の資料のとおり）。
(() => {
  const COLORS = { "請求書": "#D55E00", "注文": "#0072B2", "問い合わせ": "#009E73", "お知らせ": "#B36B00" };
  const OTHER = "#5b6670";
  const $ = (id) => document.getElementById(id);
  const color = (name) => COLORS[name] || OTHER;
  const ICON_FOLDER = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h6l2 2h10v10H3z"/></svg>';

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function showFolders(folders) {
    const ul = $("folders");
    ul.textContent = "";
    folders.forEach((f) => {
      const li = el("li");
      li.innerHTML = ICON_FOLDER;
      li.firstChild.style.color = color(f.name);
      li.append(el("span", "name", f.name), el("span", "count", `(${f.count})`));
      ul.appendChild(li);
    });
  }

  function showMails(data) {
    $("list-title").textContent = `届いたメール（${data.source} ／ ${data.folderName}）`;
    const ul = $("mails");
    ul.textContent = "";
    data.mails.forEach((m) => {
      const li = el("li", "card");
      const av = el("div", "avatar", m.folder.slice(0, 1));
      av.style.background = color(m.folder);
      av.setAttribute("aria-hidden", "true");
      const text = el("div", "text");
      text.append(el("p", "subject", m.subject || "（件名なし）"), el("p", "snippet", m.snippet));
      const right = el("div", "right");
      const sug = el("div", "suggest");
      // 提案のフォルダを最初に選んでおき、違っていたら人が選び直す
      const pick = el("select", "pick");
      pick.setAttribute("aria-label", `「${m.subject}」を移す先のフォルダ`);
      data.targets.forEach((f) => pick.add(new Option(`→ ${f}`, f, f === m.folder, f === m.folder)));
      pick.addEventListener("change", () => {
        const changed = pick.value !== m.folder;
        li.classList.toggle("rechosen", changed);
        av.textContent = pick.value.slice(0, 1);
        av.style.background = color(pick.value);
      });
      sug.append(pick);
      if (m.unsure) sug.append(el("span", "unsure", `迷っています：${m.second} かも`));
      const move = el("button", "move", "移す");
      move.type = "button";
      move.addEventListener("click", () => moveMail(m, pick.value, li));
      right.append(sug, move);
      li.append(av, text, right);
      ul.appendChild(li);
    });
    const unsure = data.mails.filter((m) => m.unsure).length;
    if (!data.moved) {
      $("status").textContent = data.mails.length
        ? `${data.mails.length} 通に提案を付けました。` + (unsure ? `迷っているメールが ${unsure} 通あります。` : "") + "違っていたら、フォルダを選び直してから「移す」を押してください。"
        : "届いたメールはありません。";
    }
  }

  async function moveMail(m, folder, li) {
    li.querySelectorAll("button, select").forEach((x) => (x.disabled = true));
    $("status").textContent = `「${m.subject}」を「${folder}」へ移しています…`;
    try {
      const data = await window.pywebview.api.move(m.id, folder);
      showFolders(data.folders);
      if (data.listError) {
        li.remove(); // 移すのはできている。一覧の読み直しだけ失敗した
        $("status").textContent = `「${data.moved.subject}」を「${data.moved.folder}」へ移しました。ただ、残りのメールの読み直しに失敗しました（${data.listError}）。「お手本を覚える」を押して読み直してください。`;
        return;
      }
      showMails(data);
      const again = folder !== m.folder ? "（選び直したフォルダです）" : "";
      $("status").textContent = `「${data.moved.subject}」を「${data.moved.folder}」へ移しました${again}。このメールも、これからはお手本になります。`;
    } catch (e) {
      li.querySelectorAll("button, select").forEach((x) => (x.disabled = false));
      $("status").textContent = `移せませんでした：${e && e.message ? e.message : e}`;
    }
  }

  async function load() {
    $("learn").disabled = true;
    try {
      const api = window.pywebview.api;
      $("status").textContent = "振り分け先のフォルダからお手本を覚えています…（モデルの読み込みに数秒、はじめて使うときはモデルのダウンロード（約207MB）に数分かかります）";
      showFolders((await api.learn()).folders);
      $("status").textContent = "Outlook のメールを読んでいます…";
      showMails(await api.mails());
    } catch (e) {
      $("status").textContent = `うまく読めませんでした：${e && e.message ? e.message : e}`;
    } finally {
      $("learn").disabled = false;
    }
  }

  $("learn").addEventListener("click", load);
  window.addEventListener("pywebviewready", load);
})();
