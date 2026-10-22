/* ------------------------------------------------------------------
   FixLogo · lógica do frontend
   ------------------------------------------------------------------ */
(() => {
  'use strict';

  const ACCEPTED_TYPES = new Set(['image/jpeg', 'image/png']);
  const DEFAULT_MAX_BYTES = 25 * 1024 * 1024;
  const REQUEST_TIMEOUT_MS = 45_000;

  const els = {
    apiStatus: document.getElementById('apiStatus'),
    apiDot: document.querySelector('[data-status-dot]'),
    apiText: document.querySelector('[data-status-text]'),
    logoWarning: document.getElementById('logoWarning'),
    uploadCard: document.getElementById('uploadCard'),
    dropzone: document.getElementById('dropzone'),
    fileInput: document.getElementById('fileInput'),
    maxSizeLabel: document.getElementById('maxSizeLabel'),
    processingCard: document.getElementById('processingCard'),
    processingStep: document.getElementById('processingStep'),
    processingFileName: document.getElementById('processingFileName'),
    resultCard: document.getElementById('resultCard'),
    resultMeta: document.getElementById('resultMeta'),
    resultExpiry: document.getElementById('resultExpiry'),
    compare: document.getElementById('compare'),
    imgBefore: document.getElementById('imgBefore'),
    imgAfter: document.getElementById('imgAfter'),
    compareRange: document.getElementById('compareRange'),
    downloadBtn: document.getElementById('downloadBtn'),
    downloadLabel: document.getElementById('downloadLabel'),
    resetBtn: document.getElementById('resetBtn'),
    toast: document.getElementById('toast'),
  };

  const state = {
    file: null,
    beforeUrl: null,
    afterUrl: null,
    maxBytes: DEFAULT_MAX_BYTES,
    ttlMinutes: 60,
    busy: false,
    stepTimer: null,
  };

  /* ------------------------------------------------------------------
     Inicialização
     ------------------------------------------------------------------ */
  init();

  function init() {
    bindEvents();
    updateCompare(50);
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

    // Evita que o navegador abra a imagem fora da área de upload.
    document.addEventListener('dragover', (event) => event.preventDefault());
    document.addEventListener('drop', (event) => event.preventDefault());

    document.addEventListener('paste', (event) => {
      const items = event.clipboardData ? event.clipboardData.items : null;
      if (!items) return;
      for (const item of items) {
        if (item.kind === 'file' && ACCEPTED_TYPES.has(item.type)) {
          event.preventDefault();
          handleFiles([item.getAsFile()]);
          break;
        }
      }
    });

    els.compareRange.addEventListener('input', (event) => updateCompare(event.target.value));
    els.resetBtn.addEventListener('click', reset);
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
      if (config.file_ttl_minutes) {
        state.ttlMinutes = config.file_ttl_minutes;
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
     Fluxo: seleção -> processamento -> resultado
     ------------------------------------------------------------------ */
  function handleFiles(fileList) {
    const file = fileList && fileList[0];
    if (!file || state.busy) return;

    const typeOk = ACCEPTED_TYPES.has(file.type) || /\.(jpe?g|png)$/i.test(file.name);
    if (!typeOk) {
      showToast('Formato não suportado. Envie imagens JPG, JPEG ou PNG.', 'error');
      return;
    }
    if (file.size === 0) {
      showToast('O arquivo selecionado está vazio.', 'error');
      return;
    }
    if (file.size > state.maxBytes) {
      showToast(
        `Arquivo muito grande (${formatBytes(file.size)}). O limite é ${formatBytes(state.maxBytes)}.`,
        'error'
      );
      return;
    }

    processFile(file);
  }

  async function processFile(file) {
    state.busy = true;
    state.file = file;
    clearObjectUrls();

    setPanel('processing');
    els.processingFileName.textContent = `${file.name} · ${formatBytes(file.size)}`;
    startStepAnimation();

    // Pré-visualização local do original para o comparador.
    state.beforeUrl = URL.createObjectURL(file);
    els.imgBefore.src = state.beforeUrl;

    const formData = new FormData();
    formData.append('file', file, file.name);

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
        throw new Error(payload.detail || 'Não foi possível processar a imagem.');
      }

      await showResult(payload, file);
      showToast('Imagem pronta! Faça o download e publique.', 'success');
    } catch (error) {
      const message =
        error.name === 'AbortError'
          ? 'O processamento demorou demais. Tente novamente com uma foto menor.'
          : error instanceof TypeError
            ? 'Não foi possível conectar ao servidor. Verifique se ele está em execução.'
            : error.message || 'Erro inesperado ao processar a imagem.';
      showToast(message, 'error');
      reset({ keepToast: true });
    } finally {
      clearTimeout(timeoutId);
      stopStepAnimation();
      state.busy = false;
    }
  }

  async function showResult(payload, file) {
    state.afterUrl = payload.preview_url;
    els.imgAfter.src = payload.preview_url;
    els.imgAfter.alt = `Foto ${file.name} com a logomarca do petshop`;

    await Promise.allSettled([els.imgAfter.decode(), els.imgBefore.decode()]);
    fitCompareAspect();

    const dimensions =
      payload.width && payload.height ? `${payload.width} × ${payload.height} px` : 'Foto processada';
    const elapsed = payload.processing_ms ? ` · ${formatDuration(payload.processing_ms)}` : '';
    const logoSize = payload.logo_width ? ` · logo ${payload.logo_width} px de largura` : '';
    els.resultMeta.textContent = `${dimensions}${logoSize}${elapsed}`;

    els.downloadBtn.href = payload.download_url;
    els.downloadBtn.setAttribute('download', payload.download_name || 'foto-logo.jpg');
    els.downloadLabel.textContent = payload.download_name
      ? `Baixar ${payload.download_name}`
      : 'Baixar imagem';

    const ttl = payload.expires_in_minutes || state.ttlMinutes;
    els.resultExpiry.textContent = `Link de download válido por ${ttl} minuto${ttl === 1 ? '' : 's'}.`;

    setPanel('result');
    updateCompare(50);
    scrollToResults();
  }

  function fitCompareAspect() {
    const img = els.imgAfter;
    if (img.naturalWidth && img.naturalHeight) {
      els.compare.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
    }
  }

  function scrollToResults() {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    els.resultCard.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'center',
    });
  }

  function reset() {
    clearObjectUrls();
    els.fileInput.value = '';
    els.imgBefore.removeAttribute('src');
    els.imgAfter.removeAttribute('src');
    els.compare.style.aspectRatio = '4 / 3';
    updateCompare(50);
    setPanel('upload');
    els.dropzone.focus({ preventScroll: true });
  }

  function clearObjectUrls() {
    if (state.beforeUrl) {
      URL.revokeObjectURL(state.beforeUrl);
      state.beforeUrl = null;
    }
    state.afterUrl = null;
  }

  function setPanel(name) {
    els.uploadCard.hidden = name !== 'upload';
    els.processingCard.hidden = name !== 'processing';
    els.resultCard.hidden = name !== 'result';
  }

  /* ------------------------------------------------------------------
     Comparador antes/depois
     ------------------------------------------------------------------ */
  function updateCompare(value) {
    const position = Math.max(0, Math.min(100, Number(value) || 0));
    els.compare.style.setProperty('--position', `${position}%`);
    els.compareRange.value = String(position);
    els.compareRange.setAttribute('aria-valuetext', `${position}% da foto com logomarca visível`);
  }

  /* ------------------------------------------------------------------
     Micro-interações
     ------------------------------------------------------------------ */
  const STEPS = [
    'Enviando a foto para o servidor',
    'Aplicando a logomarca no canto inferior esquerdo',
    'Gerando a pré-visualização',
  ];

  function startStepAnimation() {
    let index = 0;
    els.processingStep.textContent = STEPS[0];
    state.stepTimer = setInterval(() => {
      index = Math.min(index + 1, STEPS.length - 1);
      els.processingStep.textContent = STEPS[index];
    }, 1800);
  }

  function stopStepAnimation() {
    if (state.stepTimer) {
      clearInterval(state.stepTimer);
      state.stepTimer = null;
    }
  }

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
