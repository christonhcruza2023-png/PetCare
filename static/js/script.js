/* ==========================================================================
   PetCare — front-end behaviour (vanilla JS)
   Modules: theme, sidebar, toasts, modals, form validation, image preview
   ========================================================================== */
(function () {
  'use strict';

  var THEME_KEY = 'petcare.theme';

  /* ---------------------------------------------------------------------
     Theme switching (localStorage + OS preference)
     --------------------------------------------------------------------- */
  function currentTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  function systemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function setTheme(theme, persist) {
    applyTheme(theme);
    if (persist) {
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* ignore */ }
    }
  }

  // Initial theme is already applied by the inline <head> script.
  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      setTheme(next, true);
      announce('Switched to ' + next + ' mode');
    });
  }

  // Follow OS changes only while the user has no explicit preference.
  try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (!currentTheme()) applyTheme(e.matches ? 'dark' : 'light');
    });
  } catch (e) { /* older browsers */ }

  // Settings page: radio buttons preview the theme live.
  document.querySelectorAll('[data-theme-choice]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      setTheme(radio.value === 'system' ? systemTheme() : radio.value, true);
    });
  });

  /* ---------------------------------------------------------------------
     Mobile sidebar
     --------------------------------------------------------------------- */
  var sidebar = document.getElementById('sidebar');
  var scrim = document.getElementById('sidebar-scrim');
  var menuToggle = document.getElementById('menu-toggle');

  function setSidebar(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('is-open', open);
    if (scrim) scrim.hidden = !open;
    if (menuToggle) menuToggle.setAttribute('aria-expanded', String(open));
    document.body.style.overflow = open ? 'hidden' : '';
  }

  if (menuToggle) {
    menuToggle.addEventListener('click', function () {
      setSidebar(!sidebar.classList.contains('is-open'));
    });
  }
  if (scrim) scrim.addEventListener('click', function () { setSidebar(false); });

  // Close on Escape.
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      setSidebar(false);
      closeModal();
    }
  });

  // Close the drawer after navigating (mobile).
  if (sidebar) {
    sidebar.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        if (window.innerWidth <= 768) setSidebar(false);
      });
    });
  }

  /* ---------------------------------------------------------------------
     Toast notifications
     --------------------------------------------------------------------- */
  var stack = document.getElementById('toast-stack');

  function dismissToast(toast) {
    if (!toast) return;
    toast.classList.add('is-leaving');
    setTimeout(function () { toast.remove(); }, 220);
  }

  if (stack) {
    stack.querySelectorAll('.toast').forEach(function (toast) {
      var close = toast.querySelector('.toast__close');
      if (close) close.addEventListener('click', function () { dismissToast(toast); });
      if (toast.hasAttribute('data-auto-dismiss')) {
        setTimeout(function () { dismissToast(toast); }, 5000);
      }
    });
  }

  // Announcements made from JS (e.g. theme change) are announced politely.
  var liveRegion = null;
  function announce(message) {
    if (!liveRegion) {
      liveRegion = document.createElement('div');
      liveRegion.className = 'sr-only';
      liveRegion.setAttribute('role', 'status');
      liveRegion.setAttribute('aria-live', 'polite');
      document.body.appendChild(liveRegion);
    }
    liveRegion.textContent = message;
  }

  /* ---------------------------------------------------------------------
     Account menu (tap-to-open on touch devices)
     --------------------------------------------------------------------- */
  var userMenu = document.querySelector('.user-menu');
  if (userMenu) {
    var avatar = userMenu.querySelector('.avatar');
    if (avatar) {
      avatar.addEventListener('click', function (e) {
        if (window.innerWidth > 768) return; // hover handles desktop
        e.stopPropagation();
        userMenu.classList.toggle('is-open');
      });
    }
    document.addEventListener('click', function (e) {
      if (userMenu && !userMenu.contains(e.target)) userMenu.classList.remove('is-open');
    });
  }

  /* ---------------------------------------------------------------------
     Delete confirmation modal
     --------------------------------------------------------------------- */
  var modal = document.getElementById('confirm-modal');
  var modalForm = document.getElementById('confirm-modal-form');
  var modalTitle = document.getElementById('confirm-modal-title');
  var modalMessage = document.getElementById('confirm-modal-message');
  var lastFocused = null;

  function openModal(name, petId, url) {
    if (!modal || !modalForm) return;
    lastFocused = document.activeElement;
    modalTitle.textContent = 'Delete ' + name + '?';
    modalMessage.textContent = 'Are you sure you want to delete this pet record? This action cannot be undone.';
    modalForm.action = url;
    modal.hidden = false;
    var submit = document.getElementById('confirm-modal-submit');
    if (submit) submit.focus();
  }

  function closeModal() {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    if (modalForm) modalForm.removeAttribute('action');
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  document.querySelectorAll('.js-delete-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      openModal(btn.dataset.petName || 'this pet', btn.dataset.petId, btn.dataset.deleteUrl);
    });
  });

  /* ---------------------------------------------------------------------
     Confirmation for inline <form> submits (e.g. deleting a user account)
     --------------------------------------------------------------------- */
  document.querySelectorAll('form[data-confirm]').forEach(function (frm) {
    frm.addEventListener('submit', function (e) {
      if (frm.dataset.confirmed === '1') return;
      e.preventDefault();
      var kind = frm.dataset.confirm;
      var message = kind === 'delete-user'
        ? 'Are you sure you want to delete this account? This action cannot be undone.'
        : 'Are you sure you want to perform this action? This action cannot be undone.';

      if (modal && modalForm && modalMessage) {
        lastFocused = document.activeElement;
        modalTitle.textContent = 'Are you sure?';
        modalMessage.textContent = message;
        modalForm.setAttribute('action', '');
        modal.hidden = false;
        // Re-use the modal, but submit THIS form instead.
        modalForm.onsubmit = function () { return true; };
        var confirmBtn = document.getElementById('confirm-modal-submit');
        if (confirmBtn) {
          confirmBtn.focus();
          confirmBtn.onclick = function (ev) {
            ev.preventDefault();
            modal.hidden = true;
            frm.dataset.confirmed = '1';
            frm.submit();
          };
        }
      } else if (window.confirm(message)) {
        frm.dataset.confirmed = '1';
        frm.submit();
      }
    });
  });

  if (modal) {
    modal.querySelectorAll('[data-close-modal]').forEach(function (el) {
      el.addEventListener('click', closeModal);
    });
    // Basic focus trap.
    modal.addEventListener('keydown', function (e) {
      if (e.key !== 'Tab') return;
      var focusables = modal.querySelectorAll('button, [href], input, select, textarea');
      if (!focusables.length) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
  }

  /* ---------------------------------------------------------------------
     Pet photo upload preview (add + edit forms)
     --------------------------------------------------------------------- */
  var fileInput = document.getElementById('photo');
  var previewBox = document.getElementById('upload-preview');
  var previewImg = document.getElementById('upload-preview-img');
  var clearBtn = document.getElementById('upload-clear');

  var ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
  var MAX_BYTES = 5 * 1024 * 1024; // mirrors the server limit

  function resetPreview() {
    if (!fileInput) return;
    fileInput.value = '';
    if (previewBox) previewBox.hidden = true;
    if (previewImg) previewImg.removeAttribute('src');
  }

  function showPreview(file) {
    var url = URL.createObjectURL(file);
    previewImg.onload = function () { URL.revokeObjectURL(url); };
    previewImg.src = url;
    previewBox.hidden = false;
  }

  if (fileInput && previewBox) {
    fileInput.addEventListener('change', function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) { resetPreview(); return; }

      var ext = (file.name.split('.').pop() || '').toLowerCase();
      var extOk = ['jpg', 'jpeg', 'png', 'webp'].indexOf(ext) !== -1;

      if (!extOk || (file.type && ALLOWED.indexOf(file.type) === -1)) {
        fieldError('photo', 'Only JPG, JPEG, PNG and WEBP images are allowed.');
        resetPreview();
        return;
      }
      if (file.size > MAX_BYTES) {
        fieldError('photo', 'Image is too large. Maximum allowed size is 5 MB.');
        resetPreview();
        return;
      }
      clearFieldError('photo');
      showPreview(file);
    });
  }

  if (clearBtn) clearBtn.addEventListener('click', resetPreview);

  /* ---------------------------------------------------------------------
     Client-side form validation (mirrors the server rules)
     --------------------------------------------------------------------- */
  function fieldError(name, message) {
    var input = document.querySelector('[name="' + name + '"]');
    if (!input) return;
    var existing = input.parentElement.querySelector('.field__error--js');
    if (existing) existing.remove();
    var span = document.createElement('span');
    span.className = 'field__error field__error--js';
    span.textContent = message;
    input.setAttribute('aria-invalid', 'true');
    input.insertAdjacentElement('afterend', span);
  }

  function clearFieldError(name) {
    var input = document.querySelector('[name="' + name + '"]');
    if (!input) return;
    var existing = input.parentElement.querySelector('.field__error--js');
    if (existing) existing.remove();
    input.removeAttribute('aria-invalid');
  }

  var form = document.getElementById('pet-form');
  if (form) {
    // Clear a field's error as soon as the user edits it.
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      el.addEventListener('input', function () { clearFieldError(el.name); });
    });

    form.addEventListener('submit', function (e) {
      var errors = 0;

      var petName = form.pet_name.value.trim();
      clearFieldError('pet_name');
      if (!petName) { fieldError('pet_name', 'Pet name is required.'); errors++; }

      var animalType = form.animal_type.value;
      clearFieldError('animal_type');
      if (!animalType) { fieldError('animal_type', 'Please choose an animal type.'); errors++; }

      var ownerName = form.owner_name.value.trim();
      clearFieldError('owner_name');
      if (!ownerName) { fieldError('owner_name', 'Owner name is required.'); errors++; }

      var email = form.owner_email.value.trim();
      clearFieldError('owner_email');
      if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email)) {
        fieldError('owner_email', 'Please enter a valid e-mail address.');
        errors++;
      }

      var weight = form.weight.value.trim();
      clearFieldError('weight');
      if (weight && (isNaN(Number(weight)) || Number(weight) <= 0)) {
        fieldError('weight', 'Weight must be a positive number (kg).');
        errors++;
      }

      var dob = form.date_of_birth.value;
      var est = form.estimated_age.value.trim();
      clearFieldError('estimated_age');
      if (dob && est) {
        fieldError('estimated_age', 'Provide either a date of birth or an estimated age, not both.');
        errors++;
      }
      if (dob && new Date(dob) > new Date()) {
        fieldError('date_of_birth', 'Date of birth cannot be in the future.');
        errors++;
      }

      if (errors > 0) {
        e.preventDefault();
        var firstErr = form.querySelector('.field__error--js');
        if (firstErr) {
          firstErr.scrollIntoView({ behavior: 'smooth', block: 'center' });
          var input = firstErr.previousElementSibling;
          if (input && input.focus) input.focus();
        }
        return;
      }

      // Show the loading state; the browser then submits normally.
      var submitBtn = document.getElementById('submit-btn');
      if (submitBtn) {
        submitBtn.classList.add('is-loading');
        var spinner = submitBtn.querySelector('.btn__spinner');
        if (spinner) spinner.hidden = false;
        submitBtn.disabled = true;
      }
    });
  }

  /* ---------------------------------------------------------------------
     Settings: pressing a theme radio should feel instant
     (handled above via data-theme-choice)
     --------------------------------------------------------------------- */
})();