// Невеликі покращення інтерфейсу. Сайт працює і без цього файлу.
document.addEventListener("DOMContentLoaded", function () {
  // Кнопка меню на вузьких екранах
  var menuBtn = document.getElementById("menuBtn");
  var side = document.getElementById("side");
  if (menuBtn && side) {
    menuBtn.addEventListener("click", function () {
      side.classList.toggle("open");
    });
  }

  // Закриття повідомлень по хрестику, а успішних - автоматично
  document.querySelectorAll(".alert").forEach(function (alert) {
    var close = alert.querySelector(".alert-x");
    if (close) {
      close.addEventListener("click", function () { alert.remove(); });
    }
    if (alert.classList.contains("alert-success")) {
      setTimeout(function () { alert.remove(); }, 5000);
    }
  });

  // Фільтри-випадні списки застосовуються одразу після вибору
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () { select.form.submit(); });
  });

  // Форма матеріалу: вибір позиції з каталогу підставляє назву, одиницю та ціну
  var catalog = document.getElementById("id_catalog_item");
  if (catalog) {
    var saveBox = document.getElementById("id_save_to_catalog");
    var saveField = saveBox ? saveBox.closest(".field") : null;
    var lastFilled = {name: "", price: ""};
    var toggleSave = function () {
      if (saveField) { saveField.style.display = catalog.value ? "none" : ""; }
      if (saveBox && catalog.value) { saveBox.checked = false; }
    };
    catalog.addEventListener("change", function () {
      var option = catalog.options[catalog.selectedIndex];
      var nameInput = document.getElementById("id_name");
      var priceInput = document.getElementById("id_unit_price");
      if (option.value) {
        nameInput.value = option.dataset.name;
        document.getElementById("id_unit").value = option.dataset.unit;
        priceInput.value = option.dataset.price;
        lastFilled = {name: option.dataset.name, price: option.dataset.price};
      } else {
        // повернулися до «свій матеріал»: прибираємо лише те, що підставили автоматично
        if (nameInput.value === lastFilled.name) { nameInput.value = ""; }
        if (priceInput.value === lastFilled.price) { priceInput.value = ""; }
      }
      toggleSave();
    });
    toggleSave();
  }
});
