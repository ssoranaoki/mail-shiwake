// メール仕分けの画面の動き。Python（app.py の Api）は window.pywebview.api から呼ぶ。
// pywebview.api は window.onload では間に合わないことがあるので、pywebviewready を待つ（pywebview の資料のとおり）。
(() => {
  // フォルダの色は、振り分け先の並び順で決める（どんな名前のフォルダでも色分けされるように）
  const PALETTE = ["#D55E00", "#0072B2", "#009E73", "#B36B00", "#CC79A7", "#56B4E9", "#7a5195", "#5b6670"];
  let order = [];
  const $ = (id) => document.getElementById(id);
  const color = (name) => { const i = order.indexOf(name); return i < 0 ? "#5b6670" : PALETTE[i % PALETTE.length]; };
  const ICON_FOLDER = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h6l2 2h10v10H3z"/></svg>';

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function showFolders(folders) {
    order = folders.map((f) => f.name);
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

  // 振り分け先のフォルダが見つからないとき（はじめて起動したときなど）に、何をすればいいかを出す
  // missing（見つからないフォルダ）があればフォルダを作る案内、無ければ（empty）お手本のメールを入れる案内
  function showGuide(learned) {
    $("list-title").textContent = "はじめに";
    $("mails").textContent = "";
    const box = el("div", "guide");
    const missing = learned.missing && learned.missing.length;
    box.append(el("h2", null, missing ? "振り分け先のフォルダを用意してください" : "お手本のメールを入れてください"),
               el("p", null, missing ? "Outlook で、次のフォルダが見つかりませんでした。"
                                     : "振り分け先のフォルダは見つかりましたが、中にメールが1通もありません。"));
    const chips = el("p", "chips");
    (missing ? learned.missing : learned.folders.map((f) => f.name)).forEach((name) => chips.append(el("span", "chip", name)));
    const ol = el("ol");
    (missing ? [`Outlook で、${learned.where}にこのフォルダを作る`,
                "それぞれに、お手本になるメールを何通か入れる",
                "上の「お手本を覚える」を押す"]
             : ["Outlook で、それぞれのフォルダに、お手本になるメールを何通か入れる（ドラッグで移す）",
                "上の「お手本を覚える」を押す"]).forEach((t) => ol.append(el("li", null, t)));
    const sub = el("p", "sub");
    const open = el("button", "link", "振り分け先を選ぶ");
    open.type = "button";
    open.addEventListener("click", openPicker);
    sub.append("Outlook にあるほかのフォルダを使いたいときは、", open, " から選べます。");
    box.append(chips, ol, sub);
    $("status").textContent = "";
    $("status").append(box);
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

  // 振り分け先を選ぶ窓。Outlook のメールのフォルダをチェックで選び、保存したらお手本を覚え直す
  async function openPicker() {
    const dlg = $("picker"), list = $("picker-list");
    $("picker-msg").textContent = "";
    list.textContent = "Outlook のフォルダを読んでいます…";
    $("picker-save").disabled = true;
    dlg.showModal();
    try {
      const data = await window.pywebview.api.folder_choices();
      list.textContent = "";
      if (!data.folders.length) {
        list.textContent = "選べるメールのフォルダがありません。Outlook でフォルダを作ってから、もう一度開いてください。";
        return;
      }
      data.folders.forEach((f) => {
        const label = el("label", "pick-row");
        label.style.paddingLeft = `${10 + f.depth * 22}px`;
        const box = el("input");
        box.type = "checkbox";
        box.value = f.path;
        box.checked = data.selected.includes(f.path);
        label.append(box, el("span", "name", f.name), el("span", "count", `${f.count} 通`));
        list.append(label);
      });
      $("picker-save").disabled = false;
    } catch (e) {
      list.textContent = `フォルダを読めませんでした：${e && e.message ? e.message : e}`;
    }
  }

  async function savePicker() {
    const targets = [...$("picker-list").querySelectorAll("input:checked")].map((b) => b.value);
    if (targets.length < 2) {
      $("picker-msg").textContent = "振り分け先は2つ以上選んでください。";
      return;
    }
    try {
      await window.pywebview.api.save_targets(targets);
      $("picker").close();
      load();
    } catch (e) {
      $("picker-msg").textContent = `保存できませんでした：${e && e.message ? e.message : e}`;
    }
  }

  async function load() {
    $("learn").disabled = true;
    $("choose").disabled = false;
    try {
      const api = window.pywebview.api;
      $("status").textContent = "振り分け先のフォルダからお手本を覚えています…（モデルの読み込みに数秒、はじめて使うときはモデルのダウンロード（約207MB）に数分かかります）";
      const learned = await api.learn();
      showFolders(learned.folders);
      if ((learned.missing && learned.missing.length) || learned.empty) {
        showGuide(learned);
        return;
      }
      $("list-title").textContent = "届いたメール";
      $("status").textContent = "Outlook のメールを読んでいます…";
      showMails(await api.mails());
    } catch (e) {
      $("status").textContent = `うまく読めませんでした：${e && e.message ? e.message : e}`;
    } finally {
      $("learn").disabled = false;
    }
  }

  $("learn").addEventListener("click", load);
  $("choose").addEventListener("click", openPicker);
  $("picker-save").addEventListener("click", savePicker);
  $("picker-cancel").addEventListener("click", () => $("picker").close());
  window.addEventListener("pywebviewready", load);
})();
