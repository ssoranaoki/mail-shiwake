// メール仕分けの画面の動き。Python（app.py の Api）は window.pywebview.api から呼ぶ。
// pywebview.api は window.onload では間に合わないことがあるので、pywebviewready を待つ（pywebview の資料のとおり）。
(() => {
  // フォルダの色は、振り分け先の並び順で決める（どんな名前のフォルダでも色分けされるように）
  const PALETTE = ["#D55E00", "#0072B2", "#009E73", "#B36B00", "#CC79A7", "#56B4E9", "#7a5195", "#5b6670"];
  let order = [];
  let flagNote = "";
  // いま何をしているか（ボタンの横）。begin で出し、end で消す。途中の文は Python が window.setActivity で替える
  let busy = 0;
  function begin(text) {
    busy += 1;
    $("activity-text").textContent = text;
    $("activity").hidden = false;
  }
  function end() {
    busy = Math.max(0, busy - 1);
    if (!busy) $("activity").hidden = true;
  }
  window.setActivity = (text) => {
    if (busy) $("activity-text").textContent = text;
  }; // 旗付きのお手本が足りないときの案内
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
      // 信頼（最近の当たり・外れ）。信頼があれば自動で移す対象になる
      if (f.trust) {
        const t = f.trust;
        li.append(t.trusted
          ? el("span", "trust ok", "自動 ✓")
          : el("span", "trust", t.count ? `信頼 ${t.count - t.misses} / ${t.window}` : ""));
        if (t.trusted) li.title = `最近の ${t.count} 通で選び直し ${t.misses} 通。自動で移す対象です`;
        else if (t.count) li.title = `最近の ${t.count} 通で選び直し ${t.misses} 通（${t.window} 通で選び直しが1通以下になると、自動で移す対象になります）`;
      }
      // お手本が少ないフォルダは、あと何通あるとよいかを出す（0通のフォルダは提案に出てこない）
      if (f.needed) {
        li.classList.add("few");
        li.title = f.count ? `お手本があと ${f.needed} 通あると、提案が安定します` : "お手本が無いので、まだ提案に出てきません";
        li.append(el("span", "need", f.count ? `あと ${f.needed} 通` : "まだ提案に出ません"));
      }
      ul.appendChild(li);
    });
  }

  function showMails(data) {
    $("list-title").textContent = `届いたメール（${data.source} ／ ${data.folderName}）`;
    const ul = $("mails");
    ul.textContent = "";
    const main = data.mails.filter((m) => m.group !== "bulk");
    const bulk = data.mails.filter((m) => m.group === "bulk");
    const checks = []; // まとめて移すメール（チェック欄と、そのカードの移す先）
    main.forEach((m) => {
      const li = el("li", "card with-check");
      // 迷っていないメールにだけチェック欄を付ける（迷っている・大事かもは1通ずつ確かめる）
      const cell = el("div", "check");
      if (m.autoMove) {
        const cb = el("input");
        cb.type = "checkbox";
        cb.checked = true;
        cb.setAttribute("aria-label", `「${m.subject}」をまとめて移す`);
        cb.addEventListener("change", updateMany);
        cell.append(cb);
        checks.push({ cb, m, li, pickOf: () => li.querySelector("select").value });
      }
      const av = el("div", "avatar", m.folder.slice(0, 1));
      av.style.background = color(m.folder);
      av.setAttribute("aria-hidden", "true");
      const text = el("div", "text");
      const subj = el("p", "subject");
      if (m.important) subj.append(el("span", "important", "★ 大事かも"));
      // 件名を押すと、Outlook でそのメールを開く（中身を読んでから判断できるように）
      const title = el("button", "subject-link", m.subject || "（件名なし）");
      title.type = "button";
      title.title = "Outlook で開く";
      title.addEventListener("click", () => openMail(m));
      subj.append(title);
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
      if (m.unsure) {
        sug.append(el("span", "unsure", `迷っています：${m.second} かも`));
        const open = el("button", "open-mail", "Outlook で開く");
        open.type = "button";
        open.addEventListener("click", () => openMail(m));
        sug.append(open);
      }
      const move = el("button", "move", "移す");
      move.type = "button";
      move.addEventListener("click", () => moveMail(m, pick.value, li));
      right.append(sug, move);
      li.append(cell, av, text, right);
      ul.appendChild(li);
    });
    // 一覧の上の「提案どおりにまとめて移す」
    const bar = $("main-actions");
    bar.textContent = "";
    const many = el("button", "primary", "");
    many.type = "button";
    function updateMany() {
      const n = checks.filter((c) => c.cb.checked).length;
      many.textContent = `チェックした ${n} 通を、選んだフォルダへまとめて移す`;
      many.disabled = n === 0;
    }
    if (checks.length) {
      updateMany();
      many.addEventListener("click", () => moveMany(checks.filter((c) => c.cb.checked)));
      bar.append(many, el("span", "hint", "迷っているメールと大事かものメールは入りません。1通ずつ確かめてください。"));
    }
    showBulk(bulk, data.bulkFolder);
    const unsure = main.filter((m) => m.unsure).length;
    const important = main.filter((m) => m.important).length;
    if (!data.moved && !data.bulkMoved && !data.manyMoved) {
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
    else {
      begin("Outlook のフォルダを読んでいます…");
      window.pywebview.api.folder_choices().then((d) => { folderList = d.folders; fill(folderList); })
        .catch(() => { pick.options[0].text = "フォルダを読めませんでした"; }).finally(end);
    }
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
      begin("配信メールを移しています…");
      let data;
      try { data = await window.pywebview.api.move_bulk(ids, folder); } finally { end(); }
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
    $("main-actions").textContent = "";
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

  // 自動で移したメールの一覧（この窓を開いている間）。1通ずつ「元に戻す」
  const autoLog = [];
  function showAutoLog() {
    const box = $("auto-log");
    box.textContent = "";
    if (!autoLog.length) { box.hidden = true; return; }
    box.hidden = false;
    const det = el("details");
    det.append(el("summary", null, `自動で ${autoLog.length} 通移しました（中を見て、違っていたら元に戻せます）`));
    const ul = el("ul");
    autoLog.forEach((a) => {
      const li = el("li");
      const undo = el("button", "plain", "元に戻す");
      undo.type = "button";
      undo.addEventListener("click", () => undoAuto(a, undo));
      li.append(el("span", "subject", a.subject || "（件名なし）"), el("span", "to", `→ ${a.folder}`), undo);
      ul.append(li);
    });
    det.append(ul);
    box.append(det);
  }

  async function runAuto() {
    begin("自動で移しています…");
    let data;
    try { data = await window.pywebview.api.auto_move(); } finally { end(); }
    showFolders(data.folders);
    autoLog.push(...data.autoMoved.items);
    showMails(data);
    showAutoLog();
    const r = data.autoMoved;
    $("status").textContent = `自動で ${r.count} 通移しました。` + (r.failed ? `${r.failed} 通は移せませんでした。` : "") + "違っていたら「元に戻す」を押してください。";
  }

  async function undoAuto(a, btn) {
    btn.disabled = true;
    try {
      begin("元に戻しています…");
      let data;
      try { data = await window.pywebview.api.undo_auto(a.id); } finally { end(); }
      autoLog.splice(autoLog.indexOf(a), 1);
      showFolders(data.folders);
      showMails(data);
      showAutoLog();
      $("status").textContent = `「${a.subject}」を元に戻しました。このメールは、これからは自動では移しません。「${a.folder}」の信頼も1つ下げました。`;
    } catch (e) {
      btn.disabled = false;
      $("status").textContent = `元に戻せませんでした：${e && e.message ? e.message : e}`;
    }
  }

  async function openMail(m) {
    begin("Outlook でメールを開いています…");
    try {
      await window.pywebview.api.open_mail(m.id);
      $("status").textContent = `「${m.subject}」を Outlook で開きました。読んだら、こちらでフォルダを選んで「移す」を押してください。`;
    } catch (e) {
      $("status").textContent = `開けませんでした：${e && e.message ? e.message : e}`;
    } finally {
      end();
    }
  }

  async function moveMany(chosen) {
    const moves = chosen.map((c) => ({ id: c.m.id, folder: c.pickOf() }));
    document.querySelectorAll("#mails button, #mails select, #mails input, #main-actions button").forEach((x) => (x.disabled = true));
    $("status").textContent = `${moves.length} 通を移しています…`;
    try {
      begin("メールを移しています…");
      let data;
      try { data = await window.pywebview.api.move_many(moves); } finally { end(); }
      showFolders(data.folders);
      const r = data.manyMoved;
      const msg = `${r.count} 通を移しました。` + (r.failed ? `${r.failed} 通は移せませんでした。` : "") + "移したメールも、これからはお手本になります。";
      if (data.listError) {
        $("mails").textContent = "";
        $("main-actions").textContent = "";
        $("status").textContent = msg + `ただ、残りのメールの読み直しに失敗しました（${data.listError}）。「お手本を覚える」を押して読み直してください。`;
        return;
      }
      showMails(data);
      $("status").textContent = msg;
    } catch (e) {
      document.querySelectorAll("#mails button, #mails select, #mails input, #main-actions button").forEach((x) => (x.disabled = false));
      $("status").textContent = `移せませんでした：${e && e.message ? e.message : e}`;
    }
  }

  async function moveMail(m, folder, li) {
    li.querySelectorAll("button, select").forEach((x) => (x.disabled = true));
    $("status").textContent = `「${m.subject}」を「${folder}」へ移しています…`;
    try {
      begin("メールを移しています…");
      let data;
      try { data = await window.pywebview.api.move(m.id, folder); } finally { end(); }
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
      begin("Outlook のフォルダを読んでいます…");
      let data;
      try { data = await window.pywebview.api.folder_choices(); } finally { end(); }
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
      begin("振り分け先を保存しています…");
      try { await window.pywebview.api.save_targets(targets); } finally { end(); }
      $("picker").close();
      load();
    } catch (e) {
      $("picker-msg").textContent = `保存できませんでした：${e && e.message ? e.message : e}`;
    }
  }

  async function load() {
    begin("お手本を覚えています…");
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
      const data = await api.mails();
      showMails(data);
      $("auto-toggle").checked = data.autoMove.enabled;
      $("auto-toggle").disabled = false;
      $("refresh").value = String(data.refreshMinutes);
      $("refresh").disabled = false;
      schedule(data.refreshMinutes);
      // スイッチがオンなら、信頼のあるフォルダへの確かな提案を自動で移す
      if (data.autoMove.enabled && data.mails.some((m) => m.autoReady)) await runAuto();
    } catch (e) {
      $("status").textContent = `うまく読めませんでした：${e && e.message ? e.message : e}`;
    } finally {
      $("learn").disabled = false;
      end();
      if (refreshMinutes) schedule(refreshMinutes); // 失敗しても次の回を予約する（Outlook が閉じていた、など）
    }
  }

  // 決まった間隔で「お手本を覚える」を繰り返す。人が操作の途中なら、その回は飛ばす
  let timer = null;
  let refreshMinutes = 0;
  function schedule(minutes) {
    refreshMinutes = minutes;
    clearTimeout(timer);
    $("refresh-next").textContent = "";
    if (!minutes) return;
    const at = new Date(Date.now() + minutes * 60000);
    $("refresh-next").textContent = `次は ${at.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" })}`;
    timer = setTimeout(() => {
      if (userIsEditing()) {
        $("status").textContent = "操作の途中なので、読み直しは次の回にします。";
        schedule(minutes);
        return;
      }
      load(); // load の最後で次の回を予約する
    }, minutes * 60000);
  }
  function userIsEditing() {
    return busy > 0 || $("picker").open
      || document.querySelector(".card.rechosen") !== null
      || document.querySelector("#mails input[type=checkbox]:not(:checked), #bulk input[type=checkbox]:not(:checked)") !== null;
  }
  $("refresh").addEventListener("change", async (e) => {
    const minutes = Number(e.target.value);
    await window.pywebview.api.set_refresh(minutes);
    schedule(minutes);
    $("status").textContent = minutes ? `${minutes} 分ごとに読み直します。` : "読み直しをやめました。";
  });

  $("learn").addEventListener("click", load);
  $("auto-toggle").addEventListener("change", async (e) => {
    const on = e.target.checked;
    await window.pywebview.api.set_auto_move(on);
    $("status").textContent = on
      ? "自動で移すをオンにしました。「自動 ✓」の付いたフォルダへの確かな提案を、起動したときと「お手本を覚える」のときに自動で移します。"
      : "自動で移すをオフにしました。";
    if (on) load();
  });
  $("choose").addEventListener("click", openPicker);
  $("picker-save").addEventListener("click", savePicker);
  $("picker-cancel").addEventListener("click", () => $("picker").close());
  window.addEventListener("pywebviewready", load);
})();
