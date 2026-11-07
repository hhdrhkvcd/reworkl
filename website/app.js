'use strict';

const installPaths = {
  windows: {
    path: 'Документы/Paradox Interactive/Hearts of Iron IV/mod',
    note: 'Если Документы находятся в OneDrive, используй папку Документы внутри OneDrive.',
  },
  linux: {
    path: '~/.local/share/Paradox Interactive/Hearts of Iron IV/mod',
    note: 'Для нативной версии Linux. В Proton используй пользовательскую папку HOI4 внутри своего префикса.',
  },
  mac: {
    path: '~/Documents/Paradox Interactive/Hearts of Iron IV/mod',
    note: 'Открой Finder → Переход → Переход к папке. Знак ~ обозначает твою домашнюю папку.',
  },
};

let toastTimeout;
function notify(message) {
  const toast = document.querySelector('#toast');
  toast.textContent = message;
  toast.classList.add('visible');
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove('visible'), 3500);
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (_) {
      // Clipboard access may be denied by the preview iframe. Try the local
      // selection fallback without leaving the user with an inert button.
    }
  }
  const field = document.createElement('textarea');
  field.value = text;
  field.setAttribute('readonly', '');
  field.className = 'clipboard-fallback';
  document.body.appendChild(field);
  field.select();
  const copied = document.execCommand('copy');
  field.remove();
  if (!copied) throw new Error('Clipboard permission denied');
}

const osTabs = [...document.querySelectorAll('[data-os]')];
function selectOS(tab, focus = false) {
  const current = installPaths[tab.dataset.os];
  osTabs.forEach((item) => {
    const selected = item === tab;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  document.querySelector('#install-path').textContent = current.path;
  document.querySelector('#path-note').textContent = current.note;
  document.querySelector('#install-path-panel').setAttribute('aria-labelledby', tab.id);
  if (focus) tab.focus();
}
osTabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectOS(tab));
  tab.addEventListener('keydown', (event) => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % osTabs.length;
    if (event.key === 'ArrowLeft') next = (index + osTabs.length - 1) % osTabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = osTabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      selectOS(osTabs[next], true);
    }
  });
});

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    const checksum = button.dataset.copy === 'checksum';
    const text = document.querySelector(checksum ? '#checksum-value' : '#install-path').textContent.trim();
    button.disabled = true;
    try {
      await copyText(text);
      notify(checksum ? 'SHA-256 скопирован' : 'Путь скопирован');
      const icon = button.querySelector('use');
      if (icon) {
        const previous = icon.getAttribute('href');
        icon.setAttribute('href', '/assets/icons.svg#check');
        setTimeout(() => icon.setAttribute('href', previous), 1800);
      }
    } catch (_) {
      notify('Браузер запретил копирование. Выдели и скопируй текст вручную.');
    } finally {
      button.disabled = false;
    }
  });
});

document.querySelectorAll('[data-download]').forEach((link) => {
  link.addEventListener('click', () => {
    // The browser manages the real download. Do not invent a progress bar or
    // report success before the archive has actually arrived on the device.
    document.querySelector('#download-status').textContent = 'Загрузка откроется в новой вкладке. Проверь список загрузок браузера.';
  });
});

const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
function closeMenu() {
  navigation.classList.remove('is-open');
  menuButton.setAttribute('aria-expanded', 'false');
  menuButton.setAttribute('aria-label', 'Открыть меню');
}
menuButton.addEventListener('click', () => {
  const opened = navigation.classList.toggle('is-open');
  menuButton.setAttribute('aria-expanded', String(opened));
  menuButton.setAttribute('aria-label', opened ? 'Закрыть меню' : 'Открыть меню');
});
navigation.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeMenu();
});
document.addEventListener('click', (event) => {
  if (!navigation.contains(event.target) && !menuButton.contains(event.target)) closeMenu();
});
