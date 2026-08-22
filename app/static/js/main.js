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

  function bindRow(row) {
    var select = row.querySelector(".exercise-category-select");
    var input = row.querySelector("input[name='exercise_name']");
    var datalist = row.querySelector("datalist");
    var removeBtn = row.querySelector(".exercise-row-remove");

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
  }

  container.querySelectorAll(".exercise-entry-row").forEach(bindRow);

  addBtn.addEventListener("click", function () {
    var fragment = template.content.cloneNode(true);
    var row = fragment.querySelector(".exercise-entry-row");
    container.appendChild(fragment);
    bindRow(row);
  });
})();
