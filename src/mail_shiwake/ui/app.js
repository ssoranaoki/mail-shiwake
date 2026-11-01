// メール仕分けの画面の動き。Python（app.py の Api）は window.pywebview.api から呼ぶ。
// pywebview.api は window.onload では間に合わないことがあるので、pywebviewready を待つ（pywebview の資料のとおり）。
(() => {
  // フォルダの色は、振り分け先の並び順で決める（どんな名前のフォルダでも色分けされるように）
  const PALETTE = ["#D55E00", "#0072B2", "#009E73", "#B36B00", "#CC79A7", "#56B4E9", "#7a5195", "#5b6670"];
  let order = [];
  let flagNote = ""; // 旗付きのお手本が足りないときの案内
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
    const main = data.mails.filter((m) => m.group !== "bulk");
    const bulk = data.mails.filter((m) => m.group === "bulk");
    main.forEach((m) => {
      const li = el("li", "card");
      const av = el("div", "avatar", m.folder.slice(0, 1));
      av.style.background = color(m.folder);
      av.setAttribute("aria-hidden", "true");
      const text = el("div", "text");
      const subj = el("p", "subject");
      if (m.important) subj.append(el("span", "important", "★ 大事かも"));
      subj.append(m.subject || "（件名なし）");
      text.append(subj, el("p", "snippet", m.snippet));
      if (m.important) li.classList.add("is-important");
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
    showBulk(bulk, data.bulkFolder);
    const unsure = main.filter((m) => m.unsure).length;
    const important = main.filter((m) => m.important).length;
    if (!data.moved && !data.bulkMoved) {
      $("status").textContent = data.mails.length
        ? `${main.length} 通に提案を付けました。` + (important ? `大事かもしれないメールが ${important} 通あります。` : "")
          + (unsure ? `迷っているメールが ${unsure} 通あります。` : "")
          + (bulk.length ? `配信メール ${bulk.length} 通は、下にまとめました。` : "")
          + "違っていたら、フォルダを選び直してから「移す」を押してください。"
        : "届いたメールはありません。";
      if (flagNote) $("status").append(el("span", "flag-note", flagNote));
    }
  }

  // 配信メール（メルマガ・宣伝・一斉のお知らせ）を下の1つの箱にまとめる。移す先を選んで「まとめて移す」
  let folderList = null; // 移す先に選べるフォルダ（最初に箱を出したときに1回だけ読む）
  function showBulk(bulk, bulkFolder) {
    const box = $("bulk");
    box.textContent = "";
    if (!bulk.length) return;
    const g = el("section", "bulk-box");
    g.setAttribute("aria-label", "配信メール");
    const head = el("div", "bulk-head");
    const pick = el("select", "pick");
    pick.setAttribute("aria-label", "配信メールを移す先のフォルダ");
    pick.add(new Option("移す先を選ぶ…", ""));
    const go = el("button", "move", "まとめて移す");
    go.type = "button";
    go.disabled = true;
    const fill = (list) => {
      list.forEach((f) => pick.add(new Option(`→ ${f.path}`, f.path, false, f.path === bulkFolder)));
      go.disabled = !pick.value;
    };
    if (folderList) fill(folderList);
    else window.pywebview.api.folder_choices().then((d) => { folderList = d.folders; fill(folderList); })
      .catch(() => { pick.options[0].text = "フォルダを読めませんでした"; });
    pick.addEventListener("change", () => (go.disabled = !pick.value));
    const count = el("span", "cnt");
    const right = el("div", "bulk-right");
    right.append(pick, go);
    head.append(el("span", "bulk-title", "📨 配信メール"), count, right);
    const details = el("details");
    details.append(el("summary", null, "中を見る（チェックを外したメールは移しません）"));
    const list = el("ul", "bulk-list");
    bulk.forEach((m) => {
      const li = el("li");
      const lab = el("label");
      const cb = el("input");
      cb.type = "checkbox";
      cb.checked = true;
      cb.value = m.id;
      cb.addEventListener("change", update);
      lab.append(cb, el("span", "subject", m.subject || "（件名なし）"), el("span", "snippet", m.snippet));
      li.append(lab);
      list.append(li);
    });
    function update() {
      const n = list.querySelectorAll("input:checked").length;
      count.textContent = n === bulk.length ? `${bulk.length} 通` : `${n} / ${bulk.length} 通`;
    }
    update();
    details.append(list);
    go.addEventListener("click", () => moveBulk([...list.querySelectorAll("input:checked")].map((b) => b.value), pick.value, g));
    g.append(head, details);
    box.append(g);
  }

  async function moveBulk(ids, folder, g) {
    if (!ids.length) {
      $("status").textContent = "移す配信メールが選ばれていません。";
      return;
    }
    g.querySelectorAll("button, select, input").forEach((x) => (x.disabled = true));
    $("status").textContent = `配信メール ${ids.length} 通を「${folder}」へ移しています…`;
    try {
      const data = await window.pywebview.api.move_bulk(ids, folder);
      showFolders(data.folders);
      const r = data.bulkMoved;
      const msg = `配信メール ${r.count} 通を「${r.folder}」へ移しました。` + (r.failed ? `${r.failed} 通は移せませんでした。` : "");
      if (data.listError) {
        $("bulk").textContent = "";
        $("status").textContent = msg + `ただ、残りのメールの読み直しに失敗しました（${data.listError}）。「お手本を覚える」を押して読み直してください。`;
        return;
      }
      showMails(data);
      $("status").textContent = msg;
    } catch (e) {
      g.querySelectorAll("button, select, input").forEach((x) => (x.disabled = false));
      $("status").textContent = `移せませんでした：${e && e.message ? e.message : e}`;
    }
  }

  // 振り分け先のフォルダが見つからないとき（はじめて起動したときなど）に、何をすればいいかを出す
  // missing（見つからないフォルダ）があればフォルダを作る案内、無ければ（empty）お手本のメールを入れる案内
  function showGuide(learned) {
    $("list-title").textContent = "はじめに";
    $("mails").textContent = "";
    $("bulk").textContent = "";
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
      flagNote = learned.flagged < learned.minFlagged
        ? `大事なメールの見分け：Outlook で大事なメールに旗を付けてください（いま ${learned.flagged} 通。${learned.minFlagged} 通以上で「★ 大事かも」の印が付きます）。`
        : "";
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
