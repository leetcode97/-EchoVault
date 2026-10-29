/* 🏆 EchoVault 前端播放器逻辑 */
(function () {
  "use strict";

  var state = {
    tracks: [],        // 全部曲目
    view: "all",       // all | albums | artists | playlist
    query: "",
    queue: [],         // 当前播放队列
    index: -1,
    playing: false,
    albums: [],
    artists: [],
    playlists: [],     // [{name, count, tracks}]
    activePlaylist: null,
  };

  var audio = document.getElementById("audio");
  var seekBar = document.getElementById("p-seek");
  var volBar = document.getElementById("p-volume");
  var rateSel = document.getElementById("p-rate");
  var curLabel = document.getElementById("p-cur");
  var durLabel = document.getElementById("p-dur");

  /* ---------- 工具 ---------- */
  function coverUrl(id) { return "/api/cover/" + id; }
  function streamUrl(id) { return "/api/stream/" + id; }
  function fmt(sec) {
    if (!isFinite(sec) || sec < 0) sec = 0;
    sec = Math.round(sec);
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" + s : s);
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------- 数据加载 ---------- */
  function loadLibrary() {
    return fetch("/api/library").then(function (r) { return r.json(); }).then(function (d) {
      state.tracks = d.tracks || [];
      return fetch("/api/stats").then(function (r) { return r.json(); });
    }).then(function (st) {
      var el = document.getElementById("statsbar");
      var btn = '<button class="tab" id="btn-rescan" style="margin-left:8px;padding:3px 12px;font-size:12px;">🔄 重新扫描</button>';
      if (st.error) {
        el.innerHTML = '<span style="color:#B45309;">⚠ ' + escapeHtml(st.error) + "</span>" + btn;
      } else {
        var secs = st.total_seconds;
        var durStr = "";
        if (secs >= 3600) durStr = Math.floor(secs / 3600) + " 小时 " + Math.floor((secs % 3600) / 60) + " 分钟";
        else if (secs >= 60) durStr = Math.floor(secs / 60) + " 分钟 " + (secs % 60) + " 秒";
        else durStr = secs + " 秒";
        el.innerHTML = "共 " + st.tracks + " 首 · " + st.albums + " 张专辑 · " + st.artists + " 位歌手 · 总时长 " + durStr + btn;
      }
      var b = document.getElementById("btn-rescan");
      if (b) b.addEventListener("click", rescan);
      return st;
    });
  }

  function loadAlbums() {
    return fetch("/api/albums").then(function (r) { return r.json(); }).then(function (d) { state.albums = d.albums || []; });
  }
  function loadArtists() {
    return fetch("/api/artists").then(function (r) { return r.json(); }).then(function (d) { state.artists = d.artists || []; });
  }
  function loadPlaylists() {
    return fetch("/api/playlists").then(function (r) { return r.json(); }).then(function (d) {
      state.playlists = d.playlists || [];
      renderPlaylistTabs();
    });
  }

  /* 把歌单渲染进导航（动态 tab） */
  function renderPlaylistTabs() {
    var tabs = document.getElementById("tabs");
    if (!tabs) return;
    tabs.querySelectorAll(".tab[data-view='playlist']").forEach(function (b) { b.remove(); });
    state.playlists.forEach(function (pl) {
      var b = document.createElement("button");
      b.className = "tab";
      b.setAttribute("data-view", "playlist");
      b.setAttribute("data-playlist", pl.name);
      b.textContent = pl.name + " · " + pl.count;
      tabs.appendChild(b);
    });
    // 当前激活的歌单 tab 高亮
    if (state.view === "playlist") {
      tabs.querySelectorAll(".tab").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-playlist") === state.activePlaylist);
      });
    }
  }

  /* ---------- 过滤 ---------- */
  function filteredTracks() {
    var q = state.query.trim().toLowerCase();
    if (!q) return state.tracks;
    return state.tracks.filter(function (t) {
      return t.title.toLowerCase().indexOf(q) >= 0
        || t.artist.toLowerCase().indexOf(q) >= 0
        || t.album.toLowerCase().indexOf(q) >= 0
        || (t.genre || "").toLowerCase().indexOf(q) >= 0;
    });
  }

  /* ---------- 渲染 ---------- */
  function trackRow(t, i, extra) {
    var cover = t.has_cover
      ? '<img class="r-cover" src="' + coverUrl(t.id) + '" alt="">'
      : '<div class="r-cover" style="display:flex;align-items:center;justify-content:center;font-size:18px;">🎵</div>';
    var eq = (state.playing && state.queue[state.index] && state.queue[state.index].id === t.id)
      ? '<span class="r-eq" style="color:#3D7E9E;">♪</span>' : '<span class="r-eq"></span>';
    var extraHtml = extra || "";
    return '<div class="row" data-i="' + i + '">'
      + cover
      + '<div class="r-main"><div class="r-title">' + escapeHtml(t.title) + "</div>"
      + '<div class="r-sub">' + escapeHtml(t.artist) + " · " + escapeHtml(t.album) + "</div></div>"
      + '<div class="r-time">' + fmt(t.duration) + "</div>"
      + extraHtml
      + eq
      + "</div>";
  }

  function addBtn(t) {
    return '<button class="r-btn btn-add" data-path="' + escapeHtml(t.path) + '" title="加入歌单" aria-label="加入歌单">＋</button>';
  }
  function removeBtn(t) {
    return '<button class="r-btn btn-remove" data-path="' + escapeHtml(t.path) + '" title="移出歌单" aria-label="移出歌单">−</button>';
  }

  function render() {
    var view = document.getElementById("view");

    if (state.view === "playlist") {
      var pl = null;
      for (var pi = 0; pi < state.playlists.length; pi++) {
        if (state.playlists[pi].name === state.activePlaylist) { pl = state.playlists[pi]; break; }
      }
      if (!pl) { emptyView(view, "歌单不存在"); return; }
      if (!pl.tracks.length) {
        emptyView(view, "「" + pl.name + "」还是空的\n在全部歌曲里点 ＋ 即可加入");
        return;
      }
      var htmlp = '<div class="card-list">';
      pl.tracks.forEach(function (t, i) { htmlp += trackRow(t, i, removeBtn(t)); });
      htmlp += "</div>";
      view.innerHTML = htmlp;
      view.querySelectorAll(".row").forEach(function (el) {
        el.addEventListener("click", function () { playQueue(pl.tracks, parseInt(el.getAttribute("data-i"), 10)); });
      });
      view.querySelectorAll(".btn-remove").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
          e.stopPropagation();
          removeFromPlaylist(state.activePlaylist, btn.getAttribute("data-path"));
        });
      });
      return;
    }

    if (state.view === "albums") {
      if (!state.albums.length) { emptyView(view, "还没有专辑数据"); return; }
      var html = '<div class="grid">';
      state.albums.forEach(function (a) {
        html += '<div class="card" data-album="' + escapeHtml(a.name) + '" data-artist="' + escapeHtml(a.artist) + '">'
          + '<img class="c-cover" src="' + coverUrl(a.cover_id) + '" alt="" onerror="this.style.visibility=\'hidden\'">'
          + '<div class="c-name">' + escapeHtml(a.name) + "</div>"
          + '<div class="c-sub">' + escapeHtml(a.artist) + " · " + a.count + " 首</div></div>";
      });
      html += "</div>";
      view.innerHTML = html;
      view.querySelectorAll(".card").forEach(function (el) {
        el.addEventListener("click", function () {
          var name = el.getAttribute("data-album");
          var artist = el.getAttribute("data-artist");
          var list = state.tracks.filter(function (t) { return t.album === name && (t.albumartist || t.artist) === artist; });
          playQueue(list, 0);
        });
      });
      return;
    }

    if (state.view === "artists") {
      if (!state.artists.length) { emptyView(view, "还没有歌手数据"); return; }
      var html2 = '<div class="grid">';
      state.artists.forEach(function (a) {
        html2 += '<div class="card" data-artist="' + escapeHtml(a.name) + '">'
          + '<img class="c-cover" src="' + coverUrl(a.cover_id) + '" alt="" onerror="this.style.visibility=\'hidden\'">'
          + '<div class="c-name">' + escapeHtml(a.name) + "</div>"
          + '<div class="c-sub">' + a.count + " 首</div></div>";
      });
      html2 += "</div>";
      view.innerHTML = html2;
      view.querySelectorAll(".card").forEach(function (el) {
        el.addEventListener("click", function () {
          var name = el.getAttribute("data-artist");
          var list = state.tracks.filter(function (t) { return (t.albumartist || t.artist) === name; });
          playQueue(list, 0);
        });
      });
      return;
    }

    var list = filteredTracks();
    if (!list.length) {
      emptyView(view, state.query ? "没有匹配的歌曲" : "曲库是空的");
      return;
    }
    var html3 = '<div class="card-list">';
    list.forEach(function (t, i) { html3 += trackRow(t, i, addBtn(t)); });
    html3 += "</div>";
    view.innerHTML = html3;
    view.querySelectorAll(".row").forEach(function (el) {
      el.addEventListener("click", function () {
        var i = parseInt(el.getAttribute("data-i"), 10);
        var src = filteredTracks();
        if (state.queue.length && sameQueue(src)) {
          playAt(i);
        } else {
          playQueue(src, i);
        }
      });
    });
    view.querySelectorAll(".btn-add").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        showPlaylistPicker(btn.getAttribute("data-path"));
      });
    });
  }

  function sameQueue(src) {
    if (state.queue.length !== src.length) return false;
    for (var i = 0; i < src.length; i++) {
      if (state.queue[i].id !== src[i].id) return false;
    }
    return true;
  }

  function emptyView(view, msg) {
    view.innerHTML = '<div class="empty">' + escapeHtml(msg)
      + "<div>把 mp3 放入音乐目录后，点击下方按钮重新扫描。</div>"
      + '<div class="e-code">音乐目录：项目下 music/ 文件夹（或 config.json 中 music_dir 指定的路径）</div>'
      + '<div style="margin-top:14px;"><button class="tab" id="btn-rescan">🔄 重新扫描</button></div>'
      + "</div>";
    var btn = document.getElementById("btn-rescan");
    if (btn) btn.addEventListener("click", rescan);
  }

  function rescan() {
    fetch("/api/rescan", { method: "POST" }).then(function (r) { return r.json(); }).then(function () {
      return refreshAll();
    }).catch(function (e) { alert("重新扫描失败：" + e); });
  }

  function refreshAll() {
    return loadLibrary().then(loadAlbums).then(loadArtists).then(loadPlaylists).then(render);
  }

  /* ---------- 歌单操作 ---------- */
  function addToPlaylist(name, path) {
    return fetch("/api/playlists/" + encodeURIComponent(name) + "/tracks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path })
    }).then(function (r) {
      if (!r.ok) { return r.json().then(function (d) { throw new Error(d.detail || r.status); }); }
      return r.json();
    }).then(function () {
      return refreshAll();
    }).catch(function (e) { alert("加入歌单失败：" + e.message); });
  }

  function removeFromPlaylist(name, path) {
    return fetch("/api/playlists/" + encodeURIComponent(name) + "/tracks?path=" + encodeURIComponent(path), {
      method: "DELETE"
    }).then(function (r) {
      if (!r.ok) { return r.json().then(function (d) { throw new Error(d.detail || r.status); }); }
      return r.json();
    }).then(function () {
      return refreshAll();
    }).catch(function (e) { alert("移出歌单失败：" + e.message); });
  }

  /* 歌单选择浮层 */
  var plPicker = document.getElementById("pl-picker");
  function showPlaylistPicker(path) {
    if (!plPicker) return;
    var list = document.getElementById("pl-picker-list");
    list.innerHTML = "";
    if (!state.playlists.length) {
      list.innerHTML = '<div style="font-size:13px;color:#6B7280;padding:8px 0;">还没有歌单</div>';
    }
    state.playlists.forEach(function (pl) {
      var b = document.createElement("button");
      b.className = "pl-opt";
      b.textContent = pl.name + "（" + pl.count + " 首）";
      b.addEventListener("click", function () {
        plPicker.classList.add("hidden");
        addToPlaylist(pl.name, path);
      });
      list.appendChild(b);
    });
    plPicker.classList.remove("hidden");
  }
  var plClose = document.getElementById("pl-picker-close");
  if (plClose) plClose.addEventListener("click", function () { plPicker.classList.add("hidden"); });
  if (plPicker) plPicker.addEventListener("click", function (e) {
    if (e.target === plPicker) plPicker.classList.add("hidden");
  });

  /* 自动感知：后台扫描完成后网页自动出现新歌（无需手动刷新） */
  var lastScanned = null;
  function pollStats() {
    fetch("/api/stats").then(function (r) { return r.json(); }).then(function (st) {
      var s = st.scanned_at || 0;
      if (lastScanned !== null && Math.abs(s - lastScanned) > 0.001) {
        refreshAll();
      }
      lastScanned = s;
    }).catch(function () {});
  }
  setInterval(pollStats, 15000);

  /* ---------- 播放 ---------- */
  function playQueue(list, i) {
    if (!list.length) return;
    state.queue = list;
    playAt(i);
  }

  function playAt(i) {
    if (i < 0 || i >= state.queue.length) return;
    state.index = i;
    var t = state.queue[i];
    audio.src = streamUrl(t.id);
    audio.play().catch(function () { /* 自动播放策略限制时忽略 */ });
    updatePlayerUI(t);
    render();
  }

  function updatePlayerUI(t) {
    document.getElementById("p-title").textContent = t.title;
    document.getElementById("p-artist").textContent = t.artist + " · " + t.album;
    var img = document.getElementById("p-cover");
    img.src = t.has_cover ? coverUrl(t.id) : "/icons/icon-192.png";
    durLabel.textContent = fmt(t.duration);
    curLabel.textContent = "0:00";
    seekBar.value = 0;
    setMediaSession(t);
  }

  function setMediaSession(t) {
    if (!("mediaSession" in navigator)) return;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: t.title,
        artist: t.artist,
        album: t.album,
        artwork: t.has_cover
          ? [{ src: coverUrl(t.id), sizes: "512x512", type: "image/jpeg" }]
          : [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
      });
      navigator.mediaSession.setActionHandler("play", function () { audio.play(); });
      navigator.mediaSession.setActionHandler("pause", function () { audio.pause(); });
      navigator.mediaSession.setActionHandler("previoustrack", function () { playAt(state.index - 1); });
      navigator.mediaSession.setActionHandler("nexttrack", function () { playAt(state.index + 1); });
    } catch (e) { /* 部分浏览器不支持时忽略 */ }
  }

  function playPause() {
    if (audio.src && !audio.paused) {
      audio.pause();
    } else if (audio.src) {
      audio.play();
    } else if (state.tracks.length) {
      playQueue(filteredTracks(), 0);
    }
  }

  /* ---------- 事件 ---------- */
  document.getElementById("btn-play").addEventListener("click", playPause);
  document.getElementById("btn-next").addEventListener("click", function () { playAt(state.index + 1); });
  document.getElementById("btn-prev").addEventListener("click", function () { playAt(state.index - 1); });

  audio.addEventListener("play", function () {
    state.playing = true;
    document.getElementById("btn-play").textContent = "❚❚";
    render();
  });
  audio.addEventListener("pause", function () {
    state.playing = false;
    document.getElementById("btn-play").textContent = "▶";
  });
  audio.addEventListener("ended", function () { playAt(state.index + 1); });
  audio.addEventListener("timeupdate", function () {
    if (isFinite(audio.duration)) {
      curLabel.textContent = fmt(audio.currentTime);
      seekBar.value = Math.round(audio.currentTime / audio.duration * 1000);
    }
  });
  audio.addEventListener("loadedmetadata", function () {
    if (isFinite(audio.duration)) durLabel.textContent = fmt(audio.duration);
  });
  audio.addEventListener("error", function () {
    curLabel.textContent = "无法播放";
  });

  var seeking = false;
  seekBar.addEventListener("input", function () { seeking = true; });
  seekBar.addEventListener("change", function () {
    if (isFinite(audio.duration) && audio.duration > 0) {
      audio.currentTime = seekBar.value / 1000 * audio.duration;
    }
    seeking = false;
  });
  audio.addEventListener("timeupdate", function () {
    if (!seeking && isFinite(audio.duration)) {
      seekBar.value = Math.round(audio.currentTime / audio.duration * 1000);
    }
  });

  volBar.addEventListener("input", function () {
    audio.volume = volBar.value / 100;
    localStorage.setItem("ev_volume", volBar.value);
  });
  rateSel.addEventListener("change", function () {
    audio.playbackRate = parseFloat(rateSel.value);
  });

  document.getElementById("search").addEventListener("input", function () {
    state.query = this.value;
    render();
  });

  /* Tab 切换（事件委托，覆盖动态注入的歌单 tab） */
  var tabsEl = document.getElementById("tabs");
  if (tabsEl) tabsEl.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".tab") : null;
    if (!btn) return;
    document.querySelectorAll(".tab").forEach(function (b) { b.classList.remove("active"); });
    btn.classList.add("active");
    state.view = btn.getAttribute("data-view");
    state.activePlaylist = btn.getAttribute("data-playlist") || null;
    if (state.view === "albums" && !state.albums.length) loadAlbums().then(render);
    else if (state.view === "artists" && !state.artists.length) loadArtists().then(render);
    else render();
  });

  /* 键盘快捷键：空格播放/暂停，←/→ 切歌（不在输入框时） */
  document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea") return;
    if (e.code === "Space") { e.preventDefault(); playPause(); }
    else if (e.key === "ArrowRight") playAt(state.index + 1);
    else if (e.key === "ArrowLeft") playAt(state.index - 1);
  });

  /* 恢复音量/倍速偏好 */
  (function () {
    var v = localStorage.getItem("ev_volume");
    if (v !== null) { volBar.value = v; audio.volume = v / 100; }
    var r = localStorage.getItem("ev_rate");
    if (r !== null) { rateSel.value = r; audio.playbackRate = parseFloat(r); }
  })();

  /* 开机即加载 */
  loadLibrary().then(loadPlaylists).then(render).catch(function (e) {
    document.getElementById("view").innerHTML =
      '<div class="empty">加载曲库失败：' + escapeHtml(String(e)) + "</div>";
  });

  /* Service Worker 注册（PWA 离线壳） */
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }
})();
