/*
 * Each saved token has an immutable random realm. The connection stanza points
 * to that generation, so a failed or concurrent save cannot overwrite the token
 * selected by an older connection. Tokens live only in storage/passwords.
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
  var loaded = false;
  var saving = false;
  var currentBase = '';
  var currentRealm = '';
  $('#dm_save').prop('disabled', true);

  function setStatus(text, ok) {
    $status.text(text).removeClass('ok err').addClass(ok ? 'ok' : 'err');
  }

  function finish(text, ok) {
    saving = false;
    $('#dm_save').prop('disabled', !loaded);
    setStatus(text, ok);
  }

  function checkedBase(raw, verifyTls) {
    if (typeof raw !== 'string' || !/^https?:\/\//i.test(raw) || raw.length > 8192 || /[\s\\?#\x00-\x1f\x7f]/.test(raw)) {
      throw new Error('Enter an HTTP(S) base URL without credentials, query or fragment.');
    }
    var parsed = new URL(raw);
    if (!parsed.hostname || parsed.username || parsed.password || parsed.port === '0' ||
        (verifyTls === '1' && parsed.protocol !== 'https:')) {
      throw new Error('Verified HTTPS is required unless trusted-lab mode is explicitly selected.');
    }
    return parsed.href.replace(/\/+$/, '');
  }

  service.get('configs/conf-darkmoon/settings', {}, function (err, resp) {
    var entries = resp && resp.data && resp.data.entry;
    var content = Array.isArray(entries) && entries.length === 1 && entries[0] && entries[0].content;
    if (err || !content || typeof content !== 'object' || Array.isArray(content)) {
      setStatus('Connection settings could not be read. Reopen setup before saving.', false);
      return;
    }
    var realm = content.credential_realm === undefined ? '' : content.credential_realm;
    if (typeof realm !== 'string' || realm && !/^darkmoon-[0-9a-f]{32}$/.test(realm)) {
      setStatus('The saved credential reference is invalid. Repair the connection settings before saving.', false);
      return;
    }
    var tlsValue = String(content.verify_tls === undefined ? '1' : content.verify_tls).toLowerCase();
    if (['0', '1', 'true', 'false', 'yes', 'no'].indexOf(tlsValue) < 0) {
      setStatus('The saved TLS setting is invalid. Repair the connection settings before saving.', false);
      return;
    }
    var verifyTls = ['0', 'false', 'no'].indexOf(tlsValue) >= 0 ? '0' : '1';
    if (content.base_url) {
      try { currentBase = checkedBase(content.base_url, verifyTls); }
      catch (ignored) {
        // Keep the invalid existing value visible so it can be corrected.
        currentBase = '';
      }
      $('#dm_base_url').val(content.base_url);
    }
    currentRealm = realm;
    $('#dm_verify_tls').val(verifyTls);
    loaded = true;
    $('#dm_save').prop('disabled', false);
  });

  function saveSettings(baseUrl, verifyTls, realm) {
    service.post('configs/conf-darkmoon/settings', {
      base_url: baseUrl,
      verify_tls: verifyTls,
      credential_realm: realm
    }, function (err) {
      if (err) {
        finish('Configuration was not confirmed. Reopen setup before retrying; a new encrypted credential may already be stored.', false);
        loaded = false;
        $('#dm_save').prop('disabled', true);
        return;
      }
      currentBase = baseUrl;
      currentRealm = realm;
      $('#dm_token').val('');
      service.post('apps/local/' + app, { configured: 'true' }, function (markError) {
        finish(markError ? 'Connection saved. App setup completion could not be confirmed.' : 'Configuration saved.', !markError);
      });
    });
  }

  function saveNewToken(token, next) {
    if (!window.crypto || typeof window.crypto.getRandomValues !== 'function') {
      finish('Secure credential-reference generation is unavailable in this browser.', false);
      return;
    }
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    var realm = 'darkmoon-' + Array.prototype.map.call(bytes, function (value) {
      return ('0' + value.toString(16)).slice(-2);
    }).join('');
    var passwords = service.storagePasswords({ owner: 'nobody', app: app });
    passwords.create({ name: 'darkmoon', password: token, realm: realm }, function (err) {
      if (err) {
        finish('The new credential could not be confirmed; connection settings were not changed.', false);
        return;
      }
      next(realm);
    });
  }

  $('#dm_save').on('click', function () {
    if (!loaded || saving) { return; }
    var verifyTls = $('#dm_verify_tls').val() === '0' ? '0' : '1';
    var token = $('#dm_token').val() || '';
    var baseUrl;
    try {
      baseUrl = checkedBase(($('#dm_base_url').val() || '').trim(), verifyTls);
      if (token && (token.length > 16384 || token !== token.trim() || /[\x00-\x1f\x7f]/.test(token))) {
        throw new Error('Enter a token without surrounding whitespace or control characters.');
      }
      if (!token && baseUrl !== currentBase) {
        throw new Error('Enter the token for the new base URL. Existing credentials are not reused for another connection.');
      }
    } catch (error) {
      setStatus(error.message || 'Connection settings are invalid.', false);
      return;
    }
    saving = true;
    $('#dm_save').prop('disabled', true);
    setStatus('Saving...', true);
    if (token) {
      saveNewToken(token, function (realm) { saveSettings(baseUrl, verifyTls, realm); });
    } else {
      saveSettings(baseUrl, verifyTls, currentRealm);
    }
  });
});
