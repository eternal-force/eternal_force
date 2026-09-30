(function () {
  var toggle = document.getElementById("nav-toggle");
  var nav = document.getElementById("app-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
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

  var nextRowId = 0;

  function refreshDatalist(row) {
    var select = row.querySelector(".exercise-category-select");
    var datalist = row.querySelector("datalist");
    if (!select || !datalist) return;
    var names = catalogMap[select.value] || [];
    datalist.innerHTML = "";
    names.forEach(function (name) {
      var option = document.createElement("option");
      option.value = name;
      datalist.appendChild(option);
    });
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
    var input = row.querySelector("input[name='exercise_name']");
    var datalist = row.querySelector("datalist");
    var removeBtn = row.querySelector(".exercise-row-remove");
    var collapseBtn = row.querySelector(".exercise-row-collapse");
    var toggleBtn = row.querySelector(".exercise-row-toggle");

    if (datalist && !datalist.id) {
      datalist.id = "exercise-name-options-js-" + nextRowId;
      nextRowId += 1;
    }
    if (input && datalist) {
      input.setAttribute("list", datalist.id);
    }
    if (select) {
      select.addEventListener("change", function () {
        refreshDatalist(row);
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
