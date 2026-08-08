(function () {
  'use strict';

  function initFlowerPickers() {
    document.querySelectorAll('[data-flower-icon-picker]').forEach(function (picker) {
      if (picker.dataset.ready) return;
      picker.dataset.ready = 'true';
      var input = picker.querySelector('input[type="hidden"]');
      picker.querySelectorAll('.flower-icon-option').forEach(function (button) {
        button.addEventListener('click', function () {
          input.value = button.dataset.value || '';
          picker.querySelectorAll('.flower-icon-option').forEach(function (item) {
            var selected = item === button;
            item.classList.toggle('is-selected', selected);
            item.setAttribute('aria-pressed', selected ? 'true' : 'false');
          });
        });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFlowerPickers);
  } else {
    initFlowerPickers();
  }
})();
