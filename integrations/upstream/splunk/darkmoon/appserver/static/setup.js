/*
 * Darkmoon setup page.
 * Stores the base URL in darkmoon.conf and the API token in storage/passwords
 * (encrypted). No secret is ever written to a .conf file or logged.
 */
require([
  'jquery',
  'splunkjs/mvc',
  'splunkjs/mvc/simplexml/ready!'
], function ($, mvc) {
  'use strict';

  var app = 'darkmoon';
  var service = mvc.createService({ owner: 'nobody', app: app });

  var $status = $('#dm_status');

  function setStatus(text, ok) {
    $status.text(text).removeClass('ok err').addClass(ok ? 'ok' : 'err');
  }

  // Pre-fill current settings (non-secret only).
  service.get('configs/conf-darkmoon/settings', {}, function (err, resp) {
    if (!err && resp && resp.data && resp.data.entry && resp.data.entry.length) {
      var c = resp.data.entry[0].content || {};
      if (c.base_url) { $('#dm_base_url').val(c.base_url); }
      $('#dm_verify_tls').val(String(c.verify_tls) === '0' ? '0' : '1');
    }
  });

  function saveSettings(baseUrl, verifyTls, next) {
    service.post('configs/conf-darkmoon/settings',
      { base_url: baseUrl, verify_tls: verifyTls }, function (err) {
        if (err) { setStatus('Failed to save settings.', false); return; }
        next();
      });
  }

  function markConfigured(next) {
    service.post('apps/local/' + app, { configured: 'true' }, function () {
      // reload endpoint is best-effort; ignore errors
      next();
    });
  }

  function saveToken(token, next) {
    if (!token) { next(); return; }
    var sp = service.storagePasswords({ owner: 'nobody', app: app });
    // Remove any prior 'darkmoon' credential, then create fresh.
    sp.fetch(function (ferr, coll) {
      function create() {
        sp.create({ name: 'darkmoon', password: token, realm: '' }, function (cerr) {
          if (cerr) { setStatus('Settings saved, but token could not be stored.', false); return; }
          next();
        });
      }
      if (!ferr && coll) {
        var existing = coll.item(':darkmoon:') || coll.item('darkmoon');
        if (existing) { existing.remove(function () { create(); }); return; }
      }
      create();
    });
  }

  $('#dm_save').on('click', function () {
    var baseUrl = ($('#dm_base_url').val() || '').trim().replace(/\/+$/, '');
    var verifyTls = $('#dm_verify_tls').val() === '0' ? '0' : '1';
    var token = $('#dm_token').val() || '';
    setStatus('Saving...', true);
    saveSettings(baseUrl, verifyTls, function () {
      saveToken(token, function () {
        markConfigured(function () {
          $('#dm_token').val('');
          setStatus('Configuration saved.', true);
        });
      });
    });
  });
});
