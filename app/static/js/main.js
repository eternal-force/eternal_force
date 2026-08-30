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
