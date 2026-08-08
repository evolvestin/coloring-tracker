(function () {
  'use strict';

  var allowedTags = { b: true, i: true, u: true, s: true, code: true, pre: true, a: true };

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function safePreview(source) {
    var documentFragment = new DOMParser().parseFromString(source || '', 'text/html').body;

    function render(node) {
      if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.nodeValue);
      if (node.nodeType !== Node.ELEMENT_NODE) return '';
      var tag = node.tagName.toLowerCase();
      var content = Array.from(node.childNodes).map(render).join('');
      if (!allowedTags[tag]) return content;
      if (tag === 'a') {
        var href = node.getAttribute('href') || '';
        if (!/^(https?:\/\/|tg:\/\/|mailto:)/i.test(href)) return content;
        return '<a href="' + escapeHtml(href) + '" target="_blank" rel="noopener">' + content + '</a>';
      }
      return '<' + tag + '>' + content + '</' + tag + '>';
    }

    return Array.from(documentFragment.childNodes).map(render).join('').replace(/\n/g, '<br>');
  }

  function replaceSelection(textarea, before, after, placeholder) {
    var start = textarea.selectionStart;
    var end = textarea.selectionEnd;
    var selected = textarea.value.slice(start, end) || placeholder;
    textarea.setRangeText(before + selected + after, start, end, 'select');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.focus();
  }

  function insertLink(textarea) {
    var url = window.prompt('Вставьте адрес ссылки (https://...)');
    if (!url) return;
    replaceSelection(textarea, '<a href="' + escapeHtml(url.trim()) + '">', '</a>', 'текст ссылки');
  }

  function initReplyEditors() {
    document.querySelectorAll('textarea[name="admin_reply"]').forEach(function (textarea) {
      if (textarea.dataset.editorReady) return;
      textarea.dataset.editorReady = 'true';
      var wrapper = document.createElement('div');
      wrapper.className = 'telegram-reply-editor';
      textarea.parentNode.insertBefore(wrapper, textarea);
      wrapper.appendChild(textarea);

      var toolbar = document.createElement('div');
      toolbar.className = 'telegram-reply-toolbar';
      toolbar.innerHTML = [
        ['b', 'Жирный', '<b>', '</b>'],
        ['i', 'Курсив', '<i>', '</i>'],
        ['u', 'Подчёркивание', '<u>', '</u>'],
        ['s', 'Зачёркивание', '<s>', '</s>'],
        ['code', 'Код', '<code>', '</code>'],
        ['pre', 'Блок кода', '<pre>', '</pre>'],
        ['link', 'Ссылка', null, null]
      ].map(function (item) {
        return '<button type="button" data-format="' + item[0] + '" title="' + item[1] + '">' +
          (item[0] === 'link' ? '↗' : item[0].toUpperCase()) + '</button>';
      }).join('');
      wrapper.insertBefore(toolbar, textarea);

      var info = document.createElement('div');
      info.className = 'telegram-reply-info';
      var count = document.createElement('span');
      var hint = document.createElement('span');
      hint.textContent = 'Выделите текст и нажмите кнопку';
      info.appendChild(hint);
      info.appendChild(count);
      wrapper.appendChild(info);

      var preview = document.createElement('div');
      preview.className = 'telegram-reply-preview';
      preview.innerHTML = '<span class="telegram-reply-placeholder">Предпросмотр сообщения в Telegram появится здесь</span>';
      wrapper.appendChild(preview);

      function refresh() {
        count.textContent = textarea.value.length + ' / 4096';
        var rendered = safePreview(textarea.value);
        preview.innerHTML = rendered || '<span class="telegram-reply-placeholder">Предпросмотр сообщения в Telegram появится здесь</span>';
      }

      toolbar.addEventListener('mousedown', function (event) {
        if (event.target.closest('button')) event.preventDefault();
      });
      toolbar.addEventListener('click', function (event) {
        var button = event.target.closest('button[data-format]');
        if (!button) return;
        var format = button.dataset.format;
        if (format === 'link') {
          insertLink(textarea);
        } else {
          replaceSelection(textarea, '<' + format + '>', '</' + format + '>', 'текст');
        }
        refresh();
      });
      textarea.addEventListener('input', refresh);
      refresh();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initReplyEditors);
  } else {
    initReplyEditors();
  }
})();
