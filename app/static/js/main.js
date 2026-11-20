(function () {
  var toggle = document.getElementById("nav-toggle");
  var nav = document.getElementById("app-nav");
  if (toggle && nav) {
    var setNavOpen = function (open) {
      nav.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "關閉選單" : "開啟選單");
    };
    toggle.addEventListener("click", function () {
      setNavOpen(!nav.classList.contains("open"));
    });
    // 浮動選單：點選單以外的地方或按 Esc 即收合
    document.addEventListener("click", function (event) {
      if (nav.classList.contains("open") && !nav.contains(event.target) && !toggle.contains(event.target)) {
        setNavOpen(false);
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("open")) {
        setNavOpen(false);
        toggle.focus();
      }
    });
  }

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var message = form.getAttribute("data-confirm");
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll(".password-toggle").forEach(function (btn) {
    var input = btn.closest(".password-field").querySelector("input");
    if (!input) return;
    btn.addEventListener("click", function () {
      var visible = btn.getAttribute("data-visible") === "true";
      input.type = visible ? "password" : "text";
      btn.setAttribute("data-visible", visible ? "false" : "true");
      btn.setAttribute("aria-label", visible ? "顯示密碼" : "隱藏密碼");
    });
  });

  document.querySelectorAll("[data-toggle-target]").forEach(function (btn) {
    var target = document.getElementById(btn.getAttribute("data-toggle-target"));
    if (!target) return;
    btn.addEventListener("click", function () {
      target.hidden = !target.hidden;
    });
  });

  document.querySelectorAll("[data-open-dialog]").forEach(function (btn) {
    var dialog = document.getElementById(btn.getAttribute("data-open-dialog"));
    if (!dialog) return;
    btn.addEventListener("click", function () {
      dialog.showModal();
    });
  });

  document.querySelectorAll("[data-close-dialog]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var dialog = btn.closest("dialog");
      if (dialog) dialog.close();
    });
  });
})();

(function () {
  var container = document.getElementById("exercise-rows");
  var addBtn = document.getElementById("add-exercise-row");
  var template = document.getElementById("exercise-row-template");
  if (!container || !addBtn || !template) return;

  var catalogMapEl = document.getElementById("exercise-catalog-map");
  var catalogMap = {};
  if (catalogMapEl) {
    try {
      catalogMap = JSON.parse(catalogMapEl.textContent);
    } catch (err) {
      catalogMap = {};
    }
  }

  var CUSTOM_VALUE = "__custom__";

  function addOption(select, value, text) {
    var option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    select.appendChild(option);
  }

  // 依分類重建訓練項目下拉選單，最後一項固定為「其他（自行輸入）」
  function refreshNameSelect(row) {
    var categorySelect = row.querySelector(".exercise-category-select");
    var nameSelect = row.querySelector(".exercise-name-select");
    if (!categorySelect || !nameSelect) return;
    var names = catalogMap[categorySelect.value] || [];
    nameSelect.innerHTML = "";
    addOption(nameSelect, "", categorySelect.value ? "請選擇訓練項目" : "請先選擇分類");
    names.forEach(function (name) {
      addOption(nameSelect, name, name);
    });
    addOption(nameSelect, CUSTOM_VALUE, "其他（自行輸入）");
    nameSelect.value = "";
  }

  // 下拉選單的選擇寫入實際送出的 exercise_name 欄位；選「其他」時才顯示自訂輸入框
  function syncNameInput(row, focusCustom) {
    var nameSelect = row.querySelector(".exercise-name-select");
    var input = row.querySelector("input[name='exercise_name']");
    if (!nameSelect || !input) return;
    if (nameSelect.value === CUSTOM_VALUE) {
      input.hidden = false;
      if (focusCustom) {
        input.value = "";
        input.focus();
      }
    } else {
      input.hidden = true;
      input.value = nameSelect.value;
    }
  }

  function rowSummary(row) {
    var name = (row.querySelector("input[name='exercise_name']") || {}).value || "";
    if (!name.trim()) return "尚未填寫";
    var category = (row.querySelector(".exercise-category-select") || {}).value || "";
    var sets = (row.querySelector("input[name='exercise_sets']") || {}).value;
    var reps = (row.querySelector("input[name='exercise_reps']") || {}).value;
    var weight = (row.querySelector("input[name='exercise_weight_kg']") || {}).value;
    var parts = [category, name].filter(Boolean);
    var repsPart = [];
    if (sets) repsPart.push(sets + "組");
    if (reps) repsPart.push(reps + "次");
    var metrics = [];
    if (repsPart.length) metrics.push(repsPart.join(" x "));
    if (weight) metrics.push(weight + "kg");
    var summary = parts.join(" · ");
    if (metrics.length) summary += "（" + metrics.join(" · ") + "）";
    return summary;
  }

  function setCollapsed(row, collapsed) {
    row.dataset.collapsed = collapsed ? "true" : "false";
    var summaryEl = row.querySelector(".exercise-row-summary");
    if (summaryEl) {
      summaryEl.textContent = rowSummary(row);
      summaryEl.classList.toggle("muted", summaryEl.textContent === "尚未填寫");
    }
  }

  function bindRow(row) {
    var select = row.querySelector(".exercise-category-select");
    var nameSelect = row.querySelector(".exercise-name-select");
    var removeBtn = row.querySelector(".exercise-row-remove");
    var collapseBtn = row.querySelector(".exercise-row-collapse");
    var toggleBtn = row.querySelector(".exercise-row-toggle");

    if (select) {
      select.addEventListener("change", function () {
        refreshNameSelect(row);
        syncNameInput(row, false);
      });
    }
    if (nameSelect) {
      nameSelect.addEventListener("change", function () {
        syncNameInput(row, true);
      });
    }
    if (removeBtn) {
      removeBtn.addEventListener("click", function () {
        row.remove();
      });
    }
    if (collapseBtn) {
      collapseBtn.addEventListener("click", function () {
        setCollapsed(row, true);
      });
    }
    if (toggleBtn) {
      toggleBtn.addEventListener("click", function () {
        setCollapsed(row, row.dataset.collapsed !== "true");
      });
    }
    setCollapsed(row, row.dataset.collapsed === "true");
  }

  container.querySelectorAll(".exercise-entry-row").forEach(function (row) {
    bindRow(row);
    var name = (row.querySelector("input[name='exercise_name']") || {}).value || "";
    setCollapsed(row, !!name.trim());
  });

  addBtn.addEventListener("click", function () {
    container.querySelectorAll(".exercise-entry-row").forEach(function (row) {
      var name = (row.querySelector("input[name='exercise_name']") || {}).value || "";
      if (name.trim() && row.dataset.collapsed !== "true") {
        setCollapsed(row, true);
      }
    });
    var fragment = template.content.cloneNode(true);
    var row = fragment.querySelector(".exercise-entry-row");
    container.appendChild(fragment);
    bindRow(row);
    setCollapsed(row, false);
  });
})();

// 下拉選單＋「其他」自訂輸入框(訓練項目表單的分類)：下拉的選擇寫入實際送出的文字欄位，選「其他」時才顯示輸入框。
(function () {
  document.querySelectorAll("select[data-custom-input]").forEach(function (select) {
    var input = document.getElementById(select.getAttribute("data-custom-input"));
    if (!input) return;
    select.addEventListener("change", function () {
      if (select.value === "__custom__") {
        input.hidden = false;
        input.value = "";
        input.focus();
      } else {
        input.hidden = true;
        input.value = select.value;
      }
    });
  });
})();

// 登入後彈跳公告(REQ-044)：左右滑動檢視多則公告，勾選「今日不再顯示」後當天不再彈出這些公告。
(function () {
  var dialog = document.getElementById("announcement-popup");
  if (!dialog || typeof dialog.showModal !== "function") return;

  var today = dialog.getAttribute("data-today");
  var storageKey = "ef-announcements-hidden:" + dialog.getAttribute("data-user-id");
  var track = dialog.querySelector(".announcement-track");
  var counter = dialog.querySelector(".announcement-popup-counter");
  var footer = dialog.querySelector(".announcement-popup-footer");
  var dotsEl = dialog.querySelector(".announcement-dots");
  var prevBtn = dialog.querySelector(".announcement-prev");
  var nextBtn = dialog.querySelector(".announcement-next");
  var hideToday = dialog.querySelector(".announcement-hide-today");

  function readHidden() {
    try {
      var saved = JSON.parse(localStorage.getItem(storageKey) || "null");
      if (saved && saved.date === today && Array.isArray(saved.ids)) return saved.ids;
    } catch (err) {
      // localStorage 無法使用(例如無痕模式)時，視為沒有隱藏任何公告
    }
    return [];
  }

  var hiddenIds = readHidden();
  var slides = Array.prototype.filter.call(
    dialog.querySelectorAll(".announcement-slide"),
    function (slide) {
      var hidden = hiddenIds.indexOf(slide.getAttribute("data-announcement-id")) !== -1;
      slide.hidden = hidden;
      return !hidden;
    }
  );
  if (slides.length === 0) return;

  var current = 0;
  var dots = slides.map(function (slide, index) {
    var dot = document.createElement("button");
    dot.type = "button";
    dot.className = "announcement-dot";
    dot.setAttribute("aria-label", "第 " + (index + 1) + " 則公告");
    dot.addEventListener("click", function () {
      goTo(index);
    });
    dotsEl.appendChild(dot);
    return dot;
  });

  function render() {
    counter.textContent = slides.length > 1 ? current + 1 + " / " + slides.length : "";
    prevBtn.disabled = current === 0;
    nextBtn.disabled = current === slides.length - 1;
    dots.forEach(function (dot, index) {
      dot.setAttribute("aria-current", index === current ? "true" : "false");
    });
  }

  function goTo(index) {
    current = Math.max(0, Math.min(slides.length - 1, index));
    track.scrollTo({ left: current * track.clientWidth, behavior: "smooth" });
    render();
  }

  footer.hidden = slides.length < 2;
  prevBtn.addEventListener("click", function () {
    goTo(current - 1);
  });
  nextBtn.addEventListener("click", function () {
    goTo(current + 1);
  });

  // 使用者用手指/觸控板滑動時，依捲動位置同步目前頁碼
  var scrollTimer = null;
  track.addEventListener("scroll", function () {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(function () {
      var index = Math.round(track.scrollLeft / track.clientWidth);
      if (index !== current && index >= 0 && index < slides.length) {
        current = index;
        render();
      }
    }, 80);
  });

  // 手機左右滑動：每則公告本身可上下捲動，瀏覽器常把手指的水平滑動吃掉而不會帶動外層左右捲動，
  // 因此 CSS 以 touch-action: pan-y 只讓瀏覽器處理上下捲動，左右滑動由這裡判斷方向後換頁。
  var SWIPE_MIN_DISTANCE = 40;
  var touchStartX = null;
  var touchStartY = null;
  track.addEventListener(
    "touchstart",
    function (event) {
      if (event.touches.length !== 1) {
        touchStartX = null;
        return;
      }
      touchStartX = event.touches[0].clientX;
      touchStartY = event.touches[0].clientY;
    },
    { passive: true }
  );
  track.addEventListener(
    "touchend",
    function (event) {
      if (touchStartX === null) return;
      var dx = event.changedTouches[0].clientX - touchStartX;
      var dy = event.changedTouches[0].clientY - touchStartY;
      touchStartX = null;
      if (Math.abs(dx) < SWIPE_MIN_DISTANCE || Math.abs(dx) < Math.abs(dy)) return;
      goTo(dx < 0 ? current + 1 : current - 1);
    },
    { passive: true }
  );
  track.addEventListener("touchcancel", function () {
    touchStartX = null;
  });

  track.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      goTo(current - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      goTo(current + 1);
    }
  });

  // 點視窗外的半透明背景也可關閉(背景點擊的 target 是 dialog 本身)
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });

  dialog.addEventListener("close", function () {
    if (!hideToday.checked) return;
    var ids = readHidden().concat(
      slides.map(function (slide) {
        return slide.getAttribute("data-announcement-id");
      })
    );
    try {
      localStorage.setItem(storageKey, JSON.stringify({ date: today, ids: ids }));
    } catch (err) {
      // 無法儲存時僅本次關閉，下次登入仍會顯示
    }
  });

  render();
  dialog.showModal();
})();

// 頁面瀏覽紀錄：離開或切走頁面時回報「頁面載入花多久」與「在前景停留多久」(只累計看得到頁面的時間)。
(function () {
  var url = document.body && document.body.getAttribute("data-page-view-url");
  if (!url || !navigator.sendBeacon) {
    return;
  }
  var visibleMs = 0;
  var visibleSince = document.visibilityState === "visible" ? Date.now() : null;

  var loadMs = function () {
    var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
    if (nav && nav.loadEventEnd > 0) {
      return Math.round(nav.loadEventEnd);
    }
    return null;
  };

  var report = function () {
    if (visibleSince !== null) {
      visibleMs += Date.now() - visibleSince;
      visibleSince = null;
    }
    var body = JSON.stringify({ load_ms: loadMs(), duration_ms: Math.round(visibleMs) });
    navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
  };

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      report();
    } else if (visibleSince === null) {
      visibleSince = Date.now();
    }
  });
  // 登出後就無法回報了，所以按登出時先回報這一頁。
  document.addEventListener("submit", function (event) {
    if (event.target.classList && event.target.classList.contains("logout-form")) {
      report();
    }
  });
  // 從上一頁快取(bfcache)回來時重新開始計時。
  window.addEventListener("pageshow", function (event) {
    if (event.persisted && document.visibilityState === "visible" && visibleSince === null) {
      visibleSince = Date.now();
    }
  });
})();
