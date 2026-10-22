/* ------------------------------------------------------------------
   FixLogo · lógica do frontend

   Fluxo: o usuário envia quantas fotos quiser (em lote ou em envios
   sucessivos). O backend devolve um link de download individual para
   cada foto — não há pré-visualização.
   ------------------------------------------------------------------ */
(() => {
  'use strict';

  const ACCEPTED_TYPES = new Set(['image/jpeg', 'image/png']);
  const DEFAULT_MAX_BYTES = 25 * 1024 * 1024;
  const MAX_CHUNK = 10;
  const REQUEST_TIMEOUT_MS = 180_000;

  const ICONS = {
    image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="h-5 w-5"><rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="8.5" cy="9.5" r="1.6"/><path d="m4 17 5-5 4.5 4.5L16.5 13l3.5 3.5"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="h-5 w-5"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5"/><path d="M12 16.5h.01"/></svg>',
    download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-4 w-4"><path d="M12 4v11"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M5 20h14"/></svg>',
    share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-4 w-4"><path d="M12 16V4"/><path d="m8 8 4-4 4 4"/><path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/></svg>',
  };

  const els = {
    apiStatus: document.getElementById('apiStatus'),
    apiDot: document.querySelector('[data-status-dot]'),
    apiText: document.querySelector('[data-status-text]'),
    logoWarning: document.getElementById('logoWarning'),
    dropzone: document.getElementById('dropzone'),
    fileInput: document.getElementById('fileInput'),
    maxSizeLabel: document.getElementById('maxSizeLabel'),
    progressCard: document.getElementById('progressCard'),
    progressText: document.getElementById('progressText'),
    progressBar: document.getElementById('progressBar'),
    progressFill: document.getElementById('progressFill'),
    resultsCard: document.getElementById('resultsCard'),
    resultsSummary: document.getElementById('resultsSummary'),
    resultsList: document.getElementById('resultsList'),
    resultsNote: document.getElementById('resultsNote'),
    addMoreBtn: document.getElementById('addMoreBtn'),
    toast: document.getElementById('toast'),
  };

  const state = {
    maxBytes: DEFAULT_MAX_BYTES,
    maxBatchFiles: 20,
    maxBatchBytes: 90 * 1024 * 1024,
    ttlMinutes: 60,
    chain: Promise.resolve(),
    results: [],
    canShare: false,
  };

  /* ------------------------------------------------------------------
     Inicialização
     ------------------------------------------------------------------ */
  init();

  function init() {
    state.canShare = detectFileShare();
    bindEvents();
    loadConfig();
    checkHealth();
  }

  function bindEvents() {
    els.dropzone.addEventListener('click', () => els.fileInput.click());
    els.dropzone.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        els.fileInput.click();
      }
    });

    els.fileInput.addEventListener('change', () => {
      if (els.fileInput.files && els.fileInput.files.length) {
        handleFiles(els.fileInput.files);
      }
      // Permite selecionar o mesmo arquivo novamente depois.
      els.fileInput.value = '';
    });

    ['dragenter', 'dragover'].forEach((type) => {
      els.dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        event.stopPropagation();
        els.dropzone.classList.add('is-dragover');
      });
    });

    ['dragleave', 'dragend'].forEach((type) => {
      els.dropzone.addEventListener(type, (event) => {
        if (event.relatedTarget && els.dropzone.contains(event.relatedTarget)) return;
        els.dropzone.classList.remove('is-dragover');
      });
    });

    els.dropzone.addEventListener('drop', (event) => {
      event.preventDefault();
      event.stopPropagation();
      els.dropzone.classList.remove('is-dragover');
      if (event.dataTransfer && event.dataTransfer.files.length) {
        handleFiles(event.dataTransfer.files);
      }
    });

    // Evita que o navegador abra imagens fora da área de upload.
    document.addEventListener('dragover', (event) => event.preventDefault());
    document.addEventListener('drop', (event) => event.preventDefault());

    document.addEventListener('paste', (event) => {
      const items = event.clipboardData ? event.clipboardData.items : null;
      if (!items) return;
      const pasted = [];
      for (const item of items) {
        if (item.kind === 'file' && ACCEPTED_TYPES.has(item.type)) {
          const file = item.getAsFile();
          if (file) pasted.push(file);
        }
      }
      if (pasted.length) {
        event.preventDefault();
        handleFiles(pasted);
      }
    });

    els.addMoreBtn.addEventListener('click', () => els.fileInput.click());
  }

  /* ------------------------------------------------------------------
     Configuração e status do servidor
     ------------------------------------------------------------------ */
  async function loadConfig() {
    try {
      const response = await fetch('/api/config', { headers: { Accept: 'application/json' } });
      if (!response.ok) return;
      const config = await response.json();

      if (config.max_upload_mb) {
        state.maxBytes = Math.round(config.max_upload_mb * 1024 * 1024);
        els.maxSizeLabel.textContent = `${config.max_upload_mb} MB`;
      }
      if (config.max_batch_files) {
        state.maxBatchFiles = config.max_batch_files;
      }
      if (config.max_batch_mb) {
        state.maxBatchBytes = Math.round(config.max_batch_mb * 1024 * 1024);
      }
      if (config.file_ttl_minutes) {
        state.ttlMinutes = config.file_ttl_minutes;
        updateResultsSummary();
      }
      if (config.logo && config.logo.available === false) {
        els.logoWarning.classList.remove('hidden');
      }
    } catch {
      /* configuração é opcional: mantém os valores padrão */
    }
  }

  async function checkHealth() {
    if (!els.apiStatus) return;
    try {
      const response = await fetch('/api/health', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('offline');
      const health = await response.json();
      if (health.logo_available === false) {
        setStatus('warn', 'Logo pendente');
        els.logoWarning.classList.remove('hidden');
      } else {
        setStatus('ok', 'Servidor online');
      }
    } catch {
      setStatus('error', 'Servidor indisponível');
    }
  }

  function setStatus(kind, text) {
    const palette = {
      ok: ['bg-emerald-500', 'text-slate-600'],
      warn: ['bg-amber-400', 'text-amber-700'],
      error: ['bg-red-500', 'text-red-600'],
    };
    const [dot, textColor] = palette[kind] || palette.ok;
    els.apiDot.className = `h-2 w-2 rounded-full ${dot}`;
    els.apiText.textContent = text;
    els.apiText.classList.remove('text-slate-600', 'text-amber-700', 'text-red-600');
    els.apiText.classList.add(textColor);
  }

  /* ------------------------------------------------------------------
     Envio em lote
     ------------------------------------------------------------------ */
  function handleFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    const accepted = [];
    for (const file of files) {
      const typeOk = ACCEPTED_TYPES.has(file.type) || /\.(jpe?g|png)$/i.test(file.name);
      if (!typeOk) {
        addResult({
          ok: false,
          original_name: file.name,
          error: 'Formato não suportado. Envie imagens JPG, JPEG ou PNG.',
        });
        continue;
      }
      if (file.size === 0) {
        addResult({ ok: false, original_name: file.name, error: 'O arquivo selecionado está vazio.' });
        continue;
      }
      if (file.size > state.maxBytes) {
        addResult({
          ok: false,
          original_name: file.name,
          error: `Arquivo muito grande (${formatBytes(file.size)}). O limite é ${formatBytes(state.maxBytes)} por foto.`,
        });
        continue;
      }
      accepted.push(file);
    }

    if (!accepted.length) return;

    // Enfileira para não sobrepor envios feitos em sequência.
    state.chain = state.chain.then(() => processFiles(accepted));
  }

  async function processFiles(files) {
    const firstBatch = state.results.length === 0;
    const chunks = buildChunks(files);

    let done = 0;
    let succeeded = 0;
    let failed = 0;

    showProgress(files.length);

    try {
      for (const chunk of chunks) {
        try {
          const payload = await sendChunk(chunk);
          if (payload.expires_in_minutes) state.ttlMinutes = payload.expires_in_minutes;

          for (const item of payload.items || []) {
            addResult(item);
            if (item.ok) succeeded += 1;
            else failed += 1;
          }
        } catch (error) {
          const message = describeRequestError(error);
          for (const file of chunk) {
            addResult({ ok: false, original_name: file.name, error: message });
            failed += 1;
          }
          showToast(message, 'error');
        }

        done += chunk.length;
        updateProgress(done, files.length);
      }

      if (succeeded && !failed) {
        showToast(`${succeeded} foto${succeeded === 1 ? '' : 's'} pronta${succeeded === 1 ? '' : 's'} para download.`, 'success');
      } else if (!succeeded) {
        showToast('Nenhuma foto pôde ser processada.', 'error');
      } else {
        showToast(`${succeeded} foto(s) prontas e ${failed} com erro.`, 'info');
      }
    } finally {
      hideProgress();
      updateResultsSummary();

      if (firstBatch && state.results.length) {
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        els.resultsCard.scrollIntoView({
          behavior: reduceMotion ? 'auto' : 'smooth',
          block: 'start',
        });
      }
    }
  }

  /** Divide o lote em requisições que respeitam o limite de arquivos e de bytes. */
  function buildChunks(files) {
    const maxFiles = Math.max(1, Math.min(MAX_CHUNK, state.maxBatchFiles || MAX_CHUNK));
    const maxBytes = state.maxBatchBytes || Number.POSITIVE_INFINITY;
    const chunks = [];
    let current = [];
    let currentBytes = 0;

    for (const file of files) {
      const exceedsCount = current.length >= maxFiles;
      const exceedsBytes = current.length > 0 && currentBytes + file.size > maxBytes;
      if (exceedsCount || exceedsBytes) {
        chunks.push(current);
        current = [];
        currentBytes = 0;
      }
      current.push(file);
      currentBytes += file.size;
    }
    if (current.length) chunks.push(current);
    return chunks;
  }

  async function sendChunk(chunk) {
    const formData = new FormData();
    for (const file of chunk) {
      formData.append('files', file, file.name);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch('/api/process', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      const payload = await readJson(response);
      if (!response.ok) {
        throw new Error(payload.detail || 'Não foi possível processar as fotos.');
      }
      return payload;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  function describeRequestError(error) {
    if (error.name === 'AbortError') {
      return 'O envio demorou demais. Tente novamente com menos fotos por vez.';
    }
    if (error instanceof TypeError) {
      return 'Não foi possível conectar ao servidor. Verifique se ele está em execução.';
    }
    return error.message || 'Erro inesperado ao processar as fotos.';
  }

  /* ------------------------------------------------------------------
     Lista de resultados
     ------------------------------------------------------------------ */
  function addResult(item) {
    state.results.push(item);
    els.resultsCard.hidden = false;

    const ok = Boolean(item.ok);
    const row = document.createElement('li');
    row.className = `result-row flex flex-wrap items-center gap-3 rounded-2xl border px-3 py-3 sm:px-4 ${
      ok ? 'border-slate-200 bg-white' : 'border-red-200 bg-red-50/70'
    }`;

    const icon = document.createElement('span');
    icon.className = `grid h-9 w-9 flex-none place-items-center rounded-xl ${
      ok ? 'bg-brand-50 text-brand-600' : 'bg-red-100 text-red-600'
    }`;
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = ok ? ICONS.image : ICONS.alert;

    const info = document.createElement('div');
    info.className = 'min-w-0 flex-1';

    const name = document.createElement('p');
    name.className = `truncate text-sm font-medium ${ok ? 'text-slate-900' : 'text-red-900'}`;
    name.textContent = item.original_name || 'foto';
    name.title = item.original_name || 'foto';

    const detail = document.createElement('p');
    detail.className = `mt-0.5 text-xs ${ok ? 'text-slate-500' : 'text-red-700'}`;
    detail.textContent = ok
      ? describeSuccess(item)
      : item.error || 'Não foi possível processar esta foto.';

    info.append(name, detail);
    row.append(icon, info);

    if (ok && item.download_url) {
      const primaryClass =
        'inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-brand-600 to-emerald-500 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:from-brand-700 hover:to-emerald-600 focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-200 disabled:cursor-wait disabled:opacity-70';
      const secondaryClass =
        'inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus-visible:ring-4 focus-visible:ring-slate-200';

      const actions = document.createElement('div');
      actions.className = 'flex w-full items-center justify-end gap-2 sm:w-auto';

      const link = document.createElement('a');
      link.href = item.download_url;
      link.setAttribute('download', item.download_name || '');
      link.setAttribute('aria-label', `Baixar ${item.download_name || item.original_name || 'foto'}`);
      link.className = state.canShare ? secondaryClass : primaryClass;
      link.innerHTML = `${ICONS.download}<span>Baixar</span>`;

      if (state.canShare) {
        const shareButton = document.createElement('button');
        shareButton.type = 'button';
        shareButton.className = primaryClass;
        shareButton.setAttribute(
          'aria-label',
          `Compartilhar ${item.original_name || 'foto'} no Instagram ou em outro aplicativo`
        );
        shareButton.innerHTML = `${ICONS.share}<span>Compartilhar</span>`;
        // Adianta o download da imagem no toque, aumentando a chance de o
        // navegador aceitar abrir o menu nativo logo no clique.
        shareButton.addEventListener('pointerdown', () => prefetchShareFile(item));
        shareButton.addEventListener('focus', () => prefetchShareFile(item));
        shareButton.addEventListener('click', () => shareItem(item, shareButton));
        actions.append(shareButton);
      }

      actions.append(link);
      row.append(actions);
    }

    els.resultsList.appendChild(row);
    updateResultsSummary();
  }

  /**
   * Abre o menu nativo de compartilhamento (Web Share API nível 2) com a
   * imagem processada. No celular, o usuário escolhe o Instagram, escreve a
   * legenda no app e publica. A legenda não pode ser preenchida pelo site.
   */
  async function shareItem(item, button) {
    if (!state.canShare) {
      window.location.href = item.download_url;
      return;
    }

    const label = button.querySelector('span');
    const originalLabel = label ? label.textContent : '';
    button.disabled = true;
    if (label) label.textContent = 'Abrindo…';

    try {
      const file = await getShareFile(item);

      if (!navigator.canShare({ files: [file] })) {
        throw new Error('Compartilhamento de arquivos não suportado.');
      }

      await navigator.share({ files: [file], title: file.name });
    } catch (error) {
      // AbortError = o usuário fechou o menu sem compartilhar.
      if (!error || error.name !== 'AbortError') {
        showToast('Não foi possível abrir o compartilhamento. Use o botão Baixar.', 'error');
      }
    } finally {
      button.disabled = false;
      if (label) label.textContent = originalLabel || 'Compartilhar';
    }
  }

  const shareFileCache = new WeakMap();

  function getShareFile(item) {
    let promise = shareFileCache.get(item);
    if (promise) return promise;

    promise = (async () => {
      const response = await fetch(item.download_url);
      if (!response.ok) throw new Error('Não foi possível carregar a imagem.');
      const blob = await response.blob();
      const filename = item.download_name || 'foto-logo.jpg';
      return new File([blob], filename, {
        type: item.media_type || blob.type || 'image/jpeg',
      });
    })();

    shareFileCache.set(item, promise);
    promise.catch(() => shareFileCache.delete(item));
    return promise;
  }

  function prefetchShareFile(item) {
    if (!state.canShare || !item || !item.download_url) return;
    getShareFile(item).catch(() => {});
  }

  function detectFileShare() {
    if (!navigator.share || !navigator.canShare) return false;
    try {
      const probe = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'probe.jpg', {
        type: 'image/jpeg',
      });
      return navigator.canShare({ files: [probe] });
    } catch {
      return false;
    }
  }

  function describeSuccess(item) {
    const parts = [];
    if (item.width && item.height) parts.push(`${item.width} × ${item.height} px`);
    if (item.processing_ms != null) parts.push(formatDuration(item.processing_ms));
    return parts.join(' · ');
  }

  function updateResultsSummary() {
    if (!els.resultsSummary) return;
    const total = state.results.length;
    const ok = state.results.filter((item) => item.ok).length;
    const failed = total - ok;

    if (!total) {
      els.resultsSummary.textContent = '';
      els.resultsNote.textContent = '';
      return;
    }

    els.resultsSummary.textContent = failed
      ? `${ok} de ${total} foto(s) com link de download · ${failed} com erro`
      : `${ok} foto(s) com link de download`;

    if (!ok) {
      els.resultsNote.textContent = 'Nenhuma foto gerou link de download.';
      return;
    }

    const ttl = state.ttlMinutes;
    const expiry = `Os links expiram em ${ttl} minuto${ttl === 1 ? '' : 's'}.`;
    els.resultsNote.textContent = state.canShare
      ? `Toque em "Compartilhar" para abrir o Instagram no celular, escrever a legenda e publicar. ${expiry}`
      : `Cada link baixa apenas a sua foto. ${expiry}`;
  }

  /* ------------------------------------------------------------------
     Progresso do lote
     ------------------------------------------------------------------ */
  function showProgress(total) {
    els.progressCard.hidden = false;
    updateProgress(0, total);
  }

  function updateProgress(done, total) {
    const percent = total ? Math.round((done / total) * 100) : 0;
    els.progressFill.style.width = `${percent}%`;
    els.progressBar.setAttribute('aria-valuenow', String(percent));
    els.progressText.textContent =
      done >= total ? 'Finalizando…' : `Processando ${done} de ${total} foto(s)…`;
  }

  function hideProgress() {
    els.progressCard.hidden = true;
  }

  /* ------------------------------------------------------------------
     Micro-interações
     ------------------------------------------------------------------ */
  function showToast(message, variant = 'info', duration = 6000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.dataset.variant = variant;

    const text = document.createElement('p');
    text.className = 'flex-1 leading-snug';
    text.textContent = message;

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast__close';
    close.setAttribute('aria-label', 'Fechar aviso');
    close.textContent = '✕';
    close.addEventListener('click', () => toast.remove());

    toast.append(text, close);
    els.toast.appendChild(toast);

    while (els.toast.children.length > 2) {
      els.toast.firstElementChild.remove();
    }

    if (duration > 0) {
      setTimeout(() => toast.remove(), duration);
    }
  }

  /* ------------------------------------------------------------------
     Utilitários
     ------------------------------------------------------------------ */
  async function readJson(response) {
    try {
      return await response.json();
    } catch {
      return {};
    }
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB';
    const units = ['B', 'KB', 'MB', 'GB'];
    const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / 1024 ** exponent;
    return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
  }

  function formatDuration(milliseconds) {
    const seconds = milliseconds / 1000;
    return seconds < 1 ? `${Math.round(milliseconds)} ms` : `${seconds.toFixed(1).replace('.', ',')} s`;
  }
})();
