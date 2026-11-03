function updateRatioAndDurationChips() {
      const info = getActiveDimensionsAndFrames();
      const rTxt = document.getElementById('chip-ratio-txt');
      const rIcon = document.getElementById('chip-ratio-icon');
      const rChip = document.getElementById('chip-ratio');
      const leftRLbl = document.getElementById('left-ratio-lbl');
      const leftRIcon = document.getElementById('left-ratio-icon');
      const dims = RATIO_ICON_SIZES[currentRatio] || [10, 10];

      if (rTxt && rIcon) {
        if (info.isCustomSize) {
          rTxt.textContent = `${info.width}×${info.height}`;
          rIcon.style.width = '11px';
          rIcon.style.height = '11px';
        } else {
          rTxt.textContent = currentRatio;
          rIcon.style.width = dims[0] + 'px';
          rIcon.style.height = dims[1] + 'px';
        }
      }
      if (leftRLbl && leftRIcon) {
        leftRLbl.textContent = info.isCustomSize ? `${info.width}×${info.height}` : currentRatio;
        leftRIcon.style.width = dims[0] + 'px';
        leftRIcon.style.height = dims[1] + 'px';
      }
      if (rChip) {
        rChip.title = `${info.width}×${info.height} px`;
      }
      const readout = document.getElementById('pop-res-readout');
      if (readout) readout.textContent = `${info.width} × ${info.height} px`;
      const cw = document.getElementById('pop-custom-w');
      const ch = document.getElementById('pop-custom-h');
      if (cw && ch) { cw.value = info.width; ch.value = info.height; }
      const rtw = document.getElementById('pop-rt-custom-w');
      const rth = document.getElementById('pop-rt-custom-h');
      if (rtw && rth) { rtw.value = info.width; rth.value = info.height; }
      const rtReadout = document.getElementById('pop-tier-res-readout');
      if (rtReadout) rtReadout.textContent = `${info.width} × ${info.height} px`;
      const rtChipTxt = document.getElementById('chip-res-tier-txt');
      if (rtChipTxt && info.activeResTier) {
        rtChipTxt.textContent = info.isCustomSize ? `${info.width}×${info.height}` : info.activeResTier.label;
      }
      const qMap = (info.spec && info.spec.qualitySteps) || { High: 20, Ultra: 28, Fast: 8 };
      const tierLabels = ['High', 'Ultra', 'Fast'];
      const tierDefaultStep = qMap[tierLabels[qualityTierIdx]] || info.spec.steps || 20;
      const activeSteps = customStepsOverride || tierDefaultStep;
      const qChipTxt = document.getElementById('chip-quality-txt');
      if (qChipTxt) {
        const matchedName = tierLabels.find(nm => qMap[nm] === activeSteps);
        qChipTxt.textContent = matchedName || `${activeSteps}st`;
      }
      const twQ = document.getElementById('tweak-quality');
      const twSVal = document.getElementById('tweak-steps-val');
      if (twSVal) twSVal.textContent = `${activeSteps} Steps`;
      if (twQ) {
        let sOpt = twQ.querySelector(`option[value="${activeSteps}"]`);
        if (!sOpt) {
          sOpt = document.createElement('option');
          sOpt.value = String(activeSteps);
          sOpt.textContent = `Custom (${activeSteps} Steps)`;
          twQ.prepend(sOpt);
        }
        twQ.value = String(activeSteps);
      }
      const twR = document.getElementById('tweak-ratio');
      if (twR) {
        if (info.isCustomSize) {
          let cOpt = twR.querySelector('option[value="CUSTOM"]');
          if (!cOpt) {
            cOpt = document.createElement('option');
            cOpt.value = 'CUSTOM';
            twR.prepend(cOpt);
          }
          cOpt.textContent = `Custom (${info.width}×${info.height}px)`;
          twR.value = 'CUSTOM';
        } else if (Array.from(twR.options).some(o => o.value === currentRatio)) {
          twR.value = currentRatio;
        }
      }

      document.querySelectorAll('#pop-ratio .ratio-card').forEach(c => {
        c.classList.toggle('active', !info.isCustomSize && c.getAttribute('data-r') === currentRatio);
      });
      document.querySelectorAll('#vert-ratio-popup .vert-ratio-item').forEach(it => {
        const isMatch = !info.isCustomSize && it.getAttribute('data-vr') === currentRatio;
        it.classList.toggle('active', isMatch);
        const chk = it.querySelector('.vr-check');
        if (chk) chk.textContent = isMatch ? '✓' : '';
      });

      const actualSec = Math.round((info.frames / 24) * 10) / 10;
      const durText = `${actualSec}s (${info.frames}f)`;
      const dTxt = document.getElementById('chip-duration-txt');
      const dChip = document.getElementById('chip-duration');
      if (dTxt) dTxt.textContent = durText;
      if (dChip) dChip.title = `${info.frames} frames @ 24fps`;
      const leftDur = document.getElementById('left-dur-lbl');
      if (leftDur) leftDur.textContent = durText;

      const sel = document.getElementById('model-picker');
      const mLbl = document.getElementById('chip-model-lbl');
      const leftMLbl = document.getElementById('left-model-lbl');
      if (sel && sel.selectedOptions.length) {
        const labelStr = sel.selectedOptions[0].textContent.trim();
        if (mLbl) mLbl.textContent = labelStr;
        if (leftMLbl) leftMLbl.textContent = labelStr;
        const bInfo = getModelBundleReadiness(sel.value);
        const g1 = document.getElementById('gen-btn-lbl');
        const g2 = document.getElementById('left-gen-btn-lbl');
        if (g1 && !g1.textContent.startsWith('Generating') && !g1.textContent.startsWith('Rendering') && !g1.textContent.startsWith('Checking')) {
          g1.textContent = bInfo.ready ? 'GENERATE' : 'SETUP';
        }
        if (g2 && !g2.textContent.startsWith('Generating') && !g2.textContent.startsWith('Rendering') && !g2.textContent.startsWith('Checking')) {
          g2.textContent = bInfo.ready ? 'Generate' : 'Setup';
        }
      }
    }

    function toggleVertRatioPopup(ev) {
      if (ev) ev.stopPropagation();
      const pop = document.getElementById('vert-ratio-popup');
      if (!pop) return;
      const wasOpen = pop.classList.contains('open');
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      if (!wasOpen) pop.classList.add('open');
    }

    function toggleDockPopover(popId, ev) {
      if (ev) ev.stopPropagation();
      const target = document.getElementById(popId);
      if (!target) return;
      const wasOpen = target.classList.contains('open');
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      if (!wasOpen) {
        if (popId === 'pop-model') renderVisualModelPopover();
        if (popId === 'pop-duration') renderVisualDurationPopover();
        if (popId === 'pop-ratio') updateRatioAndDurationChips();
        if (popId === 'pop-quality') renderVisualQualityPopover();
        if (popId === 'pop-res-tier') renderVisualResTierPopover();
        target.classList.add('open');

        const anchor = ev ? (ev.currentTarget || ev.target.closest('.left-select-card, .chip, .chip-split-btn, .director-card')) : null;
        if (anchor) {
          const rect = anchor.getBoundingClientRect();
          const inSidebar = Boolean(anchor.closest('#sidebar-workspace'));
          const composerEl = anchor.closest('.composer');
          if (inSidebar) {
            target.style.left = Math.min(window.innerWidth - 340, rect.right + 10) + 'px';
            target.style.bottom = Math.max(16, window.innerHeight - rect.bottom) + 'px';
            target.style.top = 'auto';
          } else if (composerEl) {
            const compRect = composerEl.getBoundingClientRect();
            target.style.left = Math.max(16, Math.min(window.innerWidth - 410, rect.left)) + 'px';
            target.style.bottom = Math.max(16, window.innerHeight - compRect.top + 12) + 'px';
            target.style.top = 'auto';
          } else {
            target.style.left = Math.max(16, Math.min(window.innerWidth - 410, rect.left)) + 'px';
            target.style.bottom = Math.max(16, window.innerHeight - rect.top + 10) + 'px';
            target.style.top = 'auto';
          }
        }
      }
    }

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.dock-popover') && !e.target.closest('.vert-ratio-popup') && !e.target.closest('.chip') && !e.target.closest('.chip-split-btn') && !e.target.closest('.left-select-card') && !e.target.closest('.director-card')) {
        document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      }
    });

    function selectVisualRatio(r) {
      customWidthOverride = null;
      customHeightOverride = null;
      currentRatio = r;
      updateRatioAndDurationChips();
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
    }

    function applyPopoverCustomSize(source) {
      const wId = source === 'rt' ? 'pop-rt-custom-w' : 'pop-custom-w';
      const hId = source === 'rt' ? 'pop-rt-custom-h' : 'pop-custom-h';
      const w = parseInt(document.getElementById(wId).value, 10);
      const h = parseInt(document.getElementById(hId).value, 10);
      if (w >= 256 && h >= 256) {
        customWidthOverride = Math.round(w / 32) * 32;
        customHeightOverride = Math.round(h / 32) * 32;
        updateRatioAndDurationChips();
        renderVisualResTierPopover();
        if (tweakingWorkflowObj) syncSimpleValuesIntoTweakingWorkflow();
        document.getElementById('pop-ratio').classList.remove('open');
        document.getElementById('pop-res-tier').classList.remove('open');
        showToast(`Custom Size: ${customWidthOverride}×${customHeightOverride}px`);
      }
    }

    const MODEL_REQUIRED_BUNDLES = {
      shinjutsu_svd_33mb: ['shinjutsu_svd_33mb', 'birefnet_lite_84mb', 'minimax_h3_ref2va_int8', 'qwen3vl_32b_h3_int8', 'minimax_h3_video_vae', 'minimax_h3_audio_vae'],
      shinjutsu_16gb_turbo: ['shinjutsu_svd_33mb', 'birefnet_lite_84mb', 'minimax_h3_ref2va_w6a8', 'minimax_h3_ref2v_turbo_lora', 'qwen3vl_32b_h3_int8', 'minimax_h3_video_vae', 'minimax_h3_audio_vae'],
      shinjutsu_pro_pod: ['shinjutsu_svd_33mb', 'birefnet_lite_84mb', 'minimax_h3_ref2va_unpruned', 'qwen3vl_32b_h3_int8', 'minimax_h3_video_vae', 'minimax_h3_audio_vae'],
      minimax_h3_ref2va_int8: ['minimax_h3_ref2va_int8', 'qwen3vl_32b_h3_int8', 'minimax_h3_video_vae', 'minimax_h3_audio_vae'],
      minimax_h3_fl2va_int8: ['minimax_h3_fl2va_int8', 'minimax_h3_fl2v_turbo_lora', 'qwen3vl_32b_h3_int8', 'minimax_h3_video_vae', 'minimax_h3_audio_vae'],
      ltx23_22b_fp8: ['ltx23_22b_fp8', 'ltx23_distilled_lora', 'ltx23_gemma3_te', 'ltx23_spatial_upscaler'],
      wan22_animate_14b: ['wan22_animate_14b'],
      flux2_klein_4b: ['flux2_klein_4b', 'flux2_klein_te', 'flux3_klein_vae'],
      flux3_klein: ['flux3_klein', 'flux3_klein_te', 'flux3_klein_vae'],
      krea2_turbo_fp8: ['krea2_turbo_fp8'],
      flux1_dev_fp8: ['flux1_dev_fp8'],
      minimax_music_3: ['minimax_music3_dit', 'minimax_music3_te', 'minimax_music3_vae']
    };

    function getModelBundleReadiness(modelId) {
      const reqIds = MODEL_REQUIRED_BUNDLES[modelId] || [modelId];
      const missing = [];
      const allEntries = [];
      reqIds.forEach(rid => {
        const entry = cachedModels.find(m => m.id === rid || m.name === rid);
        if (entry) {
          allEntries.push(entry);
          if (!entry.installed) missing.push(entry);
        } else {
          const fallbackEntry = { id: rid, name: rid, title: rid, folder: 'diffusion_models', size_mb: 1500, installed: false };
          allEntries.push(fallbackEntry);
          missing.push(fallbackEntry);
        }
      });
      return {
        ready: missing.length === 0 && allEntries.length === reqIds.length,
        missing,
        allEntries
      };
    }

    let activeSetupBundleIds = [];
    let activeSetupBundleTitle = '';

    function scrollSettingsModalToTop() {
      const mb = document.querySelector('#settings-modal .modal-body');
      if (mb) mb.scrollTop = 0;
      const banner = document.getElementById('tpl-install-banner');
      if (banner && banner.style.display !== 'none') {
        try { banner.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {}
      }
    }

    function renderActiveSetupBanner() {
      const banner = document.getElementById('tpl-install-banner');
      const itemsBox = document.getElementById('tpl-banner-items');
      const titleEl = document.getElementById('tpl-banner-title');
      const subEl = document.getElementById('tpl-banner-sub');
      const allBtn = document.getElementById('tpl-banner-install-all-btn');
      if (!banner || !itemsBox) return;
      if (!activeSetupBundleIds.length) {
        banner.style.display = 'none';
        return;
      }

      const entries = activeSetupBundleIds
        .map(rid => cachedModels.find(m => m.id === rid || m.name === rid))
        .filter(Boolean);
      if (!entries.length) {
        banner.style.display = 'none';
        return;
      }

      const missing = entries.filter(m => !m.installed);
      pendingTemplateMissingModels = missing;
      banner.style.display = 'flex';
      if (titleEl) {
        titleEl.textContent = `Setup: ${activeSetupBundleTitle || 'Required Models'}`;
      }
      if (subEl) {
        subEl.textContent = missing.length > 0
          ? `${entries.length - missing.length} of ${entries.length} required components installed. Install all missing or manage individual files below.`
          : `All ${entries.length} required components are installed and ready.`;
      }
      if (allBtn) {
        allBtn.style.display = missing.length > 0 ? 'inline-flex' : 'none';
      }

      itemsBox.innerHTML = entries.map(m => {
        const dl = m.download_state || {};
        const isDownloading = dl.status === 'downloading';
        const rawMb = m.actual_size_mb || m.size_mb || 0;
        const sizeLabel = rawMb >= 1000 ? `${(rawMb / 1024).toFixed(1)} GB` : `${rawMb} MB`;
        const folderPath = `models/${m.folder || 'diffusion_models'}/${m.name}`;

        let actHtml = '';
        if (isDownloading) {
          actHtml = `<span class="badge" style="color:var(--accent); border-color:rgba(242,255,89,0.4);">Downloading ${dl.percent || 0}%</span>`;
        } else if (m.installed) {
          actHtml = `
            <span class="badge ready">Installed (${sizeLabel})</span>
            ${m.source === 'local_disk' ? `<button class="act-btn danger" style="padding:3px 8px; font-size:11px;" onclick="deleteModel('${m.id}')">Remove</button>` : ''}
          `;
        } else {
          actHtml = `
            <span class="badge">${sizeLabel}</span>
            <button class="act-btn primary" style="padding:3px 9px; font-size:11px;" onclick="downloadModel('${m.id}')">Setup</button>
          `;
        }

        return `
          <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; padding:7px 10px; border-radius:9px; background:rgba(15,15,19,0.85); border:1px solid var(--border);">
            <div style="min-width:0; flex:1;">
              <div style="font-size:12px; font-weight:700; color:var(--text);">${m.title || m.name}</div>
              <div style="font-size:10.5px; color:var(--muted); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${folderPath}">${folderPath}</div>
            </div>
            <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
              ${actHtml}
            </div>
          </div>
        `;
      }).join('');
    }

    function openModelBundleSetup(modelId, modelLabel, ev) {
      if (ev) ev.stopPropagation();
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      const reqIds = MODEL_REQUIRED_BUNDLES[modelId] || [modelId];
      activeSetupBundleIds = reqIds.slice();
      activeSetupBundleTitle = modelLabel || modelId;
      openSettingsModal('models');
      renderActiveSetupBanner();
      setTimeout(scrollSettingsModalToTop, 20);
    }

    function openTemplateAdderForCurrentMode() {
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      openSettingsModal('templates');
      const catKey = currentMode === 'soul' ? 'images' : currentMode;
      filterSettingsTemplatesByCat(catKey);
    }

    function renderVisualModelPopover() {
      const box = document.getElementById('pop-model-list');
      const sel = document.getElementById('model-picker');
      const curVal = sel.value;
      const mTag = document.getElementById('pop-model-mode-tag');
      if (mTag && MODE_CONFIG[currentMode]) {
        mTag.textContent = MODE_CONFIG[currentMode].title;
      }
      const addWrap = document.getElementById('pop-model-add-wrap');
      if (addWrap) {
        addWrap.style.display = currentMode === 'shinjutsu' ? 'none' : 'flex';
      }
      const MODEL_SUBTITLES = {
        shinjutsu_pro_pod: '48GB+ Cloud GPU · Unpruned 31.7GB · 20 Steps',
        shinjutsu_svd_33mb: '32GB VRAM (RTX 5090) · Pruned INT8 19.5GB · 20 Steps',
        shinjutsu_16gb_turbo: '16–24GB VRAM · W6A8 14.9GB + Turbo · 8 Steps',
        wan22_animate_14b: 'Pose-driven character animation (16GB VRAM)',
        ltx23_22b_fp8: 'Fast joint audio + video synthesis',
        minimax_h3_ref2va_int8: 'High-coherence multimodal video',
        minimax_h3_fl2va_int8: 'MiniMax H3 Image-to-Video + 8-Step Turbo',
        flux3_klein: 'FLUX 3 Image Klein · 16-Step Distilled',
        krea2_turbo_fp8: 'Ultra-realistic 4K DSLR skin & lighting',
        flux1_dev_fp8: 'High-detail studio composition',
        qwen_img21: 'Precision editing & typography',
        minimax_music_3: 'Full-band music & vocals generator'
      };
      box.innerHTML = Array.from(sel.options).map(opt => {
        const sub = MODEL_SUBTITLES[opt.value] || 'Open-Weights Model';
        const isAct = opt.value === curVal;
        const bInfo = getModelBundleReadiness(opt.value);
        const safeLbl = (opt.textContent || '').replace(/'/g, "\\'");
        const statusHtml = bInfo.ready
          ? `<span class="badge ready" style="font-size:10px; padding:2px 7px;">Ready</span>`
          : `<span class="badge" style="font-size:10px; padding:2px 7px; border-color:rgba(242,255,89,0.45); color:var(--accent); cursor:pointer;" onclick="openModelBundleSetup('${opt.value}', '${safeLbl}', event)" title="Click to setup required files">Setup</span>`;
        return `
          <div class="model-pop-item ${isAct ? 'active' : ''}" onclick="selectVisualModel('${opt.value}')">
            <div style="min-width:0; flex:1;">
              <div style="font-size:12.5px; font-weight:700; color:var(--text); display:flex; align-items:center; gap:6px;">
                <span>${opt.textContent}</span>
              </div>
              <div style="font-size:11px; color:var(--muted); margin-top:2px;">${sub}</div>
            </div>
            <div style="display:flex; align-items:center; gap:7px; flex-shrink:0;">
              ${statusHtml}
              <span style="color:${isAct ? 'var(--accent)' : 'var(--muted)'}; font-size:12px;">${isAct ? '●' : '○'}</span>
            </div>
          </div>
        `;
      }).join('');
    }

    function selectVisualModel(val) {
      const sel = document.getElementById('model-picker');
      sel.value = val;
      onModelSelectChange();
      document.getElementById('pop-model').classList.remove('open');
    }

    function renderVisualDurationPopover() {
      const box = document.getElementById('pop-duration-list');
      const info = getActiveDimensionsAndFrames();
      const durs = info.spec.durations || [5.0, 8.0, 13.0, 15.0];
      box.innerHTML = durs.map(sec => {
        const frames = info.spec.snapFrames(sec);
        const lblSec = Math.round(frames / 24);
        const isAct = Math.abs(sec - currentDurationSec) < 0.6 && !customFramesOverride;
        return `
          <div class="model-pop-item ${isAct ? 'active' : ''}" onclick="selectVisualDuration(${sec})">
            <div>
              <div style="font-size:12.5px; font-weight:700; color:var(--text);">${lblSec} Seconds</div>
              <div style="font-size:11px; color:var(--muted);">${frames} frames @ 24fps</div>
            </div>
            <span style="color:${isAct ? 'var(--accent)' : 'var(--muted)'}; font-size:12px;">${isAct ? '●' : '○'}</span>
          </div>
        `;
      }).join('');
    }

    function selectVisualDuration(sec) {
      customFramesOverride = null;
      currentDurationSec = sec;
      updateRatioAndDurationChips();
      document.getElementById('pop-duration').classList.remove('open');
    }

    let hasUserSlot1Ref = false;
    let pendingExtraRefRole = 'outfit';
    let extraShinjutsuRefs = []; // Up to 8 additional references (<Picture 2> .. <Picture 9>)
    let activeAssetModalSlot = 1;
    let activeAssetModalKind = 'image';
    let activeAssetLibTab = 'library';
    let activeAssetFolder = 'ALL';
    let cachedAssetFolders = ['general', 'characters', 'outfits', 'scenes', 'motions'];
    let cachedLibraryAssets = [];
    let cachedGeneratedAssets = [];

    const FOLDER_DISPLAY_LABELS = {
      ALL: 'All Folders',
      general: 'General',
      characters: 'Characters',
      outfits: 'Outfits & Props',
      scenes: 'Scenes & Rooms',
      motions: 'Motion Clips'
    };

    function openAssetLibraryModal(slotNum, ev) {
      if (ev) {
        if (ev.target && (ev.target.classList.contains('slot-clear') || ev.target.classList.contains('dz-clear') || ev.target.tagName === 'INPUT')) {
          return;
        }
        ev.stopPropagation();
      }
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      activeAssetModalSlot = slotNum || 1;
      const s2Lbl = (document.getElementById('slot-2-lbl') && document.getElementById('slot-2-lbl').textContent || '').toLowerCase();
      if (activeAssetModalSlot === 1 || s2Lbl.includes('img')) {
        activeAssetModalKind = 'image';
      } else if (s2Lbl.includes('audio')) {
        activeAssetModalKind = 'audio';
      } else {
        activeAssetModalKind = 'video';
      }
      const badge = document.getElementById('alib-kind-badge');
      if (badge) {
        badge.textContent = activeAssetModalKind === 'image'
          ? 'IMAGES ONLY (NO VIDEOS)'
          : (activeAssetModalKind === 'video' ? 'VIDEOS ONLY (NO IMAGES)' : 'AUDIO ONLY');
      }
      activeAssetFolder = 'ALL';
      switchAssetLibTab('library');
      document.getElementById('asset-library-modal').classList.add('open');
      loadAssetLibraryData();
    }

    function closeAssetLibraryModal() {
      const m = document.getElementById('asset-library-modal');
      if (m) m.classList.remove('open');
    }

    function switchAssetLibTab(tab) {
      activeAssetLibTab = tab;
      document.getElementById('alib-tab-library').classList.toggle('active', tab === 'library');
      document.getElementById('alib-tab-generated').classList.toggle('active', tab === 'generated');
      document.getElementById('alib-folder-bar').style.display = tab === 'library' ? 'flex' : 'none';
      const hint = document.getElementById('alib-hint-txt');
      if (hint) {
        hint.textContent = tab === 'library'
          ? 'Click any saved item to attach it as reference, or organize files across folders.'
          : (activeAssetModalKind === 'image'
              ? 'Showing ONLY generated images from previous jobs (videos/audio are hidden).'
              : 'Showing ONLY generated videos from previous jobs (still images are hidden).');
      }
      renderAssetLibraryGrid();
    }

    function selectAssetLibFolder(folderName) {
      activeAssetFolder = folderName;
      renderAssetFolderPills();
      renderAssetLibraryGrid();
    }

    function renderAssetFolderPills() {
      const box = document.getElementById('alib-folder-pills');
      if (!box) return;
      const filteredFolders = cachedAssetFolders.filter(f => {
        if (activeAssetModalKind === 'image' && f === 'motions') return false;
        if (activeAssetModalKind === 'video' && (f === 'characters' || f === 'outfits' || f === 'scenes')) return false;
        return true;
      });
      const allFolders = ['ALL', ...filteredFolders];
      box.innerHTML = allFolders.map(f => {
        const lbl = FOLDER_DISPLAY_LABELS[f] || f;
        const isAct = activeAssetFolder === f;
        return `<div class="filter-pill ${isAct ? 'active' : ''}" onclick="selectAssetLibFolder('${f}')">${lbl}</div>`;
      }).join('');
    }

    async function createNewAssetFolder() {
      const inp = document.getElementById('alib-new-folder-inp');
      const raw = (inp && inp.value || '').trim();
      if (!raw) return;
      try {
        const res = await fetch('/shinjutsu/api/assets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'create_folder', folder: raw })
        });
        const data = await res.json();
        if (data.ok && data.folder) {
          inp.value = '';
          activeAssetFolder = data.folder;
          await loadAssetLibraryData();
          showToast(`Created folder "${data.folder}"`);
        }
      } catch (e) {}
    }

    function probeAndSyncVideoDuration(videoUrl) {
      if (!videoUrl) return;
      const probe = document.createElement('video');
      probe.preload = 'metadata';
      probe.muted = true;
      probe.onloadedmetadata = () => {
        if (probe.duration && isFinite(probe.duration) && probe.duration >= 1.0) {
          currentDurationSec = Math.min(15.08, Math.max(2.0, probe.duration));
          customFramesOverride = null;
          updateRatioAndDurationChips();
        }
      };
      probe.src = videoUrl.split('#')[0];
    }

    function openExtraRefLibraryModal(role, ev) {
      if (ev) ev.stopPropagation();
      if (extraShinjutsuRefs.length >= 8) {
        showToast('Maximum 9 reference images (<Picture 1> to <Picture 9>) reached');
        return;
      }
      pendingExtraRefRole = role || 'outfit';
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      activeAssetModalSlot = 'extra_ref';
      activeAssetModalKind = 'image';
      const badge = document.getElementById('alib-kind-badge');
      const roleLabels = { outfit: 'OUTFIT / PROPS', scene: 'SCENE / ROOM (RAW 3D)', crew: 'SUPPORTING CREW' };
      if (badge) {
        badge.textContent = `ADD <Picture ${extraShinjutsuRefs.length + 2}> · ${roleLabels[pendingExtraRefRole] || 'IMAGE'}`;
      }
      activeAssetFolder = pendingExtraRefRole === 'scene' ? 'scenes' : (pendingExtraRefRole === 'outfit' ? 'outfits' : 'characters');
      switchAssetLibTab('library');
      document.getElementById('asset-library-modal').classList.add('open');
      loadAssetLibraryData();
    }

    function triggerDirectPcUploadFromModal() {
      if (activeAssetModalSlot === 'extra_ref') {
        const extraInp = document.getElementById('extra-ref-input');
        if (extraInp) extraInp.click();
        return;
      }
      const inpId = activeAssetModalSlot === 1 ? 'slot-1-input' : 'slot-2-input';
      const inp = document.getElementById(inpId);
      if (inp) inp.click();
    }

    async function loadAssetLibraryData() {
      try {
        const res = await fetch(`/shinjutsu/api/assets?kind=${encodeURIComponent(activeAssetModalKind)}`);
        const data = await res.json();
        if (data && data.ok) {
          cachedAssetFolders = data.folders || ['general', 'characters', 'outfits', 'scenes', 'motions'];
          cachedLibraryAssets = data.library || [];
          cachedGeneratedAssets = data.generated || [];
        }
      } catch (e) {}
      // Also merge any matching in-memory sessionHistory items into Generated Creations (strictly filtered by activeAssetModalKind!)
      sessionHistory.forEach(h => {
        if (h.type === activeAssetModalKind && h.url && !cachedGeneratedAssets.some(g => g.url === h.url)) {
          const fname = decodeURIComponent((h.url.split('filename=')[1] || h.url.split('/').pop() || 'creation').split('&')[0]);
          cachedGeneratedAssets.unshift({
            id: '',
            name: fname,
            folder: 'session',
            media_type: h.type,
            url: h.url,
            size_kb: 0
          });
        }
      });
      renderAssetFolderPills();
      renderAssetLibraryGrid();
    }

    function renderAssetLibraryGrid() {
      const grid = document.getElementById('alib-grid');
      const cntEl = document.getElementById('alib-count-txt');
      if (!grid) return;

      let items = activeAssetLibTab === 'library'
        ? cachedLibraryAssets.filter(it => activeAssetFolder === 'ALL' || it.folder === activeAssetFolder)
        : cachedGeneratedAssets;

      // Strict media-type guard: never allow videos when picking an image, or images when picking a video!
      items = items.filter(it => it.media_type === activeAssetModalKind);
      if (cntEl) cntEl.textContent = `${items.length} ${activeAssetModalKind}(s)`;

      const targetSaveFolder = (activeAssetFolder && activeAssetFolder !== 'ALL')
        ? activeAssetFolder
        : (activeAssetModalKind === 'video' ? 'motions' : 'characters');
      const uploadCardHtml = activeAssetLibTab === 'library'
        ? `
          <div class="alib-upload-card" onclick="triggerDirectPcUploadFromModal()" title="Upload ${activeAssetModalKind} from your computer">
            <div class="alib-plus-circle">+</div>
            <div style="font-size:12.5px; font-weight:700; color:var(--text);">Upload from PC</div>
            <div style="font-size:10.5px; color:var(--muted); line-height:1.35;">Save to ${FOLDER_DISPLAY_LABELS[targetSaveFolder] || targetSaveFolder}</div>
          </div>
        `
        : '';

      if (!items.length && activeAssetLibTab !== 'library') {
        grid.innerHTML = `
          <div style="grid-column:1/-1; padding:36px 16px; text-align:center; color:var(--muted); border:1px dashed var(--border-strong); border-radius:12px;">
            <div style="font-weight:700; color:var(--text); margin-bottom:4px;">No generated ${activeAssetModalKind}s yet</div>
            <div style="font-size:11.5px;">Creations you render in other studio tabs will automatically appear here.</div>
          </div>
        `;
        return;
      }

      const folderOptionsHtml = cachedAssetFolders
        .filter(f => activeAssetModalKind === 'video' ? f !== 'characters' : f !== 'motions')
        .map(f => `<option value="${f}">${FOLDER_DISPLAY_LABELS[f] || f}</option>`)
        .join('');

      const activeChosenName = activeAssetModalSlot === 1
        ? (hasUserSlot1Ref ? uploadedSlot1Name : '')
        : uploadedSlot2Name;

      const cardsHtml = items.map(it => {
        const safeId = (it.id || '').replace(/'/g, "\\'");
        const safeUrl = (it.url || '').replace(/'/g, "\\'");
        const safeName = (it.name || '').replace(/'/g, "\\'");
        const stemClean = it.name.replace(/\.[^.]+$/, '_clean_white_bg.png');
        const isSelected = Boolean(activeChosenName && (activeChosenName === it.name || activeChosenName === stemClean));

        const mediaThumb = it.media_type === 'video'
          ? `<video src="${it.url}#t=0.6" style="width:100%; height:100%; object-fit:cover; display:block;" muted loop playsinline preload="metadata" onmouseenter="this.play().catch(()=>{})" onmouseleave="this.pause()"></video>`
          : `<img src="${it.url}" loading="lazy" style="width:100%; height:100%; object-fit:cover; display:block;" />`;

        const manageRow = it.id
          ? `
            <div style="display:flex; align-items:center; justify-content:space-between; gap:4px; margin-top:2px;" onclick="event.stopPropagation()">
              <select class="tweak-select" style="font-size:10px; padding:2px 4px; flex:1;" onchange="moveAssetToFolder('${safeId}', this.value, event)" title="Move or Save to Folder">
                <option value="" selected disabled>${activeAssetLibTab === 'generated' ? 'Save to folder...' : it.folder}</option>
                ${folderOptionsHtml}
              </select>
              <button class="act-btn danger" style="padding:2px 6px; font-size:10px;" onclick="deleteAssetFromLibrary('${safeId}', event)" title="Delete file">Delete</button>
            </div>
          `
          : '';

        return `
          <div class="alib-card ${isSelected ? 'selected' : ''}" onclick="pickAssetFromLibrary('${safeId}', '${it.media_type}', '${safeUrl}', '${safeName}', '${it.folder || ''}')">
            <div class="alib-thumb-wrap">
              ${mediaThumb}
              ${isSelected ? '<span class="alib-sel-pill">Selected</span>' : '<div class="alib-hover-pill"><span class="badge ready" style="font-size:10.5px;">Use Reference</span></div>'}
            </div>
            <div style="font-size:11px; font-weight:600; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${safeName}">${it.name}</div>
            ${manageRow}
          </div>
        `;
      }).join('');

      grid.innerHTML = uploadCardHtml + cardsHtml;
    }

    function pickAssetFromLibrary(assetId, mediaType, previewUrl, rawName, folderName) {
      const targetSlot = activeAssetModalSlot;
      if (targetSlot === 'extra_ref') {
        if (extraShinjutsuRefs.length >= 8) {
          showToast('Maximum 9 reference images reached');
          closeAssetLibraryModal();
          return;
        }
        const role = pendingExtraRefRole || (folderName === 'scenes' ? 'scene' : (folderName === 'outfits' ? 'outfit' : 'crew'));
        const entry = {
          role,
          filename: rawName,
          comfy_filename: rawName,
          preview_url: previewUrl
        };
        extraShinjutsuRefs.push(entry);
        const picNum = extraShinjutsuRefs.length + 1;
        renderExtraRefsStrip();

        const curP = document.getElementById('left-prompt-input').value.trim();
        const tag = `<Picture ${picNum}>`;
        if (!curP.includes(tag)) {
          let clause = '';
          if (role === 'outfit') clause = ` wearing the outfit and accessories from ${tag}`;
          else if (role === 'scene') clause = ` inside the background environment of ${tag} (re-projected into 3D perspective)`;
          else if (role === 'crew') clause = ` while replacing the supporting dancers with the crew in ${tag}`;
          const nextP = curP.replace(/\.$/, '') + clause + '.';
          document.getElementById('left-prompt-input').value = nextP;
          syncPromptFromLeft(nextP);
        }

        closeAssetLibraryModal();
        showToast(`Added <Picture ${picNum}> (${role}): "${rawName}"`);

        if (assetId) {
          const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
          fetch('/shinjutsu/api/assets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'select', asset_id: assetId, mode: 'shinjutsu', role, comfy_url: comfyUrl })
          })
            .then(r => r.json())
            .then(out => {
              if (!out || !out.ok) return;
              if (out.comfy_filename) entry.comfy_filename = out.comfy_filename;
              if (out.cleaned_url) entry.preview_url = out.cleaned_url;
              renderExtraRefsStrip();
            })
            .catch(() => {});
        }
        return;
      }

      // 1. Instant 0ms UI update & close modal immediately (never block or freeze!)
      if (targetSlot === 1) {
        hasUserSlot1Ref = true;
        uploadedSlot1Name = rawName;
        const th = document.getElementById('char-thumb');
        if (th) { th.src = previewUrl; th.style.display = 'block'; }
        document.getElementById('slot-1-clear').style.display = 'inline-flex';
        const deckImg = document.getElementById('deck-img-preview');
        const dz2Clr = document.getElementById('left-dz-2-clear');
        if (deckImg) { deckImg.src = previewUrl; deckImg.style.display = 'block'; }
        if (dz2Clr) dz2Clr.style.display = 'inline-flex';
        const refCnt = document.getElementById('dir-ref-count');
        if (refCnt) refCnt.textContent = `${1 + extraShinjutsuRefs.length} / 9`;
        if (currentMode === 'video') {
          const deckVidImg = document.getElementById('deck-vid-img-preview');
          const dz1Clr = document.getElementById('left-dz-1-clear');
          if (deckVidImg) { deckVidImg.src = previewUrl; deckVidImg.style.display = 'block'; }
          if (dz1Clr) dz1Clr.style.display = 'inline-flex';
        }
      } else {
        uploadedSlot2Name = rawName;
        uploadedDepthName = rawName;
        probeAndSyncVideoDuration(previewUrl);
        const th = document.getElementById('vid-thumb');
        if (th) { th.src = previewUrl; th.style.display = 'block'; }
        document.getElementById('slot-2-clear').style.display = 'inline-flex';
        const deckVid = document.getElementById('deck-vid-preview');
        const dz1Clr = document.getElementById('left-dz-1-clear');
        if (deckVid) {
          deckVid.src = previewUrl;
          deckVid.style.display = 'block';
          deckVid.onloadedmetadata = () => {
            if (deckVid.duration && isFinite(deckVid.duration) && deckVid.duration >= 1.5) {
              currentDurationSec = Math.min(15.08, Math.max(2.0, deckVid.duration));
              customFramesOverride = null;
              updateRatioAndDurationChips();
            }
          };
          deckVid.play().catch(()=>{});
        }
        if (dz1Clr) dz1Clr.style.display = 'inline-flex';
      }

      closeAssetLibraryModal();
      showToast(`Attached "${rawName}"`);

      // 2. Non-blocking background staging (BiRefNet white-BG cutout & ComfyUI staging)
      if (assetId) {
        const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
        const role = folderName === 'scenes' ? 'scene' : (folderName === 'outfits' ? 'outfit' : 'character');
        fetch('/shinjutsu/api/assets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'select', asset_id: assetId, mode: currentMode, role, comfy_url: comfyUrl })
        })
          .then(r => r.json())
          .then(out => {
            if (!out || !out.ok) return;
            if (targetSlot === 1 && hasUserSlot1Ref) {
              if (out.comfy_filename) uploadedSlot1Name = out.comfy_filename;
              if (out.cleaned_url) {
                const th = document.getElementById('char-thumb');
                if (th) th.src = out.cleaned_url;
                const deckImg = document.getElementById('deck-img-preview');
                if (deckImg) deckImg.src = out.cleaned_url;
              }
            } else if (targetSlot === 2) {
              if (out.comfy_filename) uploadedSlot2Name = out.comfy_filename;
              if (out.depth_filename) uploadedDepthName = out.depth_filename;
              if (out.duration_sec && isFinite(out.duration_sec) && out.duration_sec >= 1.0) {
                currentDurationSec = Math.min(15.08, Math.max(2.0, Number(out.duration_sec)));
                customFramesOverride = null;
                updateRatioAndDurationChips();
              }
            }
          })
          .catch(() => {});
      }
    }

    async function moveAssetToFolder(assetId, targetFolder, ev) {
      if (ev) ev.stopPropagation();
      if (!assetId || !targetFolder) return;
      try {
        const res = await fetch('/shinjutsu/api/assets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'move', asset_id: assetId, target_folder: targetFolder })
        });
        const data = await res.json();
        if (data && data.ok) {
          showToast(`Moved to folder "${targetFolder}"`);
          await loadAssetLibraryData();
        }
      } catch (e) {}
    }

    async function deleteAssetFromLibrary(assetId, ev) {
      if (ev) ev.stopPropagation();
      if (!assetId) return;
      try {
        const res = await fetch('/shinjutsu/api/assets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'delete', asset_id: assetId })
        });
        const data = await res.json();
        if (data && data.ok) {
          showToast('Deleted file from library');
          await loadAssetLibraryData();
        }
      } catch (e) {}
    }

    function triggerDeckUpload(slotNum) {
      openAssetLibraryModal(slotNum);
    }

    function insertPromptTag(tagStr) {
      const inp = document.getElementById('prompt-input');
      const leftInp = document.getElementById('left-prompt-input');
      const nextVal = (inp.value.trim() + ' ' + tagStr).trim();
      inp.value = nextVal;
      if (leftInp) leftInp.value = nextVal;
    }

    function syncPromptFromLeft(val) {
      const inp = document.getElementById('prompt-input');
      if (inp) inp.value = val;
    }

    function syncPromptFromBottom(val) {
      const leftInp = document.getElementById('left-prompt-input');
      if (leftInp) leftInp.value = val;
    }

    function selectLeftSubMode(idx) {
      document.getElementById('seg-btn-1').classList.toggle('active', idx === 1);
      document.getElementById('seg-btn-2').classList.toggle('active', idx === 2);
      const mRefBox = document.getElementById('left-multi-ref-box');
      if (currentMode === 'shinjutsu') {
        if (idx === 1) {
          if (mRefBox) mRefBox.style.display = 'none';
          document.getElementById('left-dz-1-title').textContent = 'Add a reference video to extract motion';
          document.getElementById('left-dz-1-sub').textContent = 'Click to pick from Library or Upload (4–15s)';
          document.getElementById('left-dz-2-title').textContent = 'Add dancer / character photo (<Picture 1>)';
          document.getElementById('left-dz-2-sub').textContent = '1 Video + 1 Photo · Auto White-BG Cutout';
          syncPromptFromLeft('Replace the person in <Video 1> with the character in <Picture 1>.');
          document.getElementById('left-prompt-input').value = 'Replace the person in <Video 1> with the character in <Picture 1>.';
        } else {
          if (mRefBox) mRefBox.style.display = 'flex';
          document.getElementById('left-dz-1-title').textContent = 'Add target video (<Video 1>)';
          document.getElementById('left-dz-1-sub').textContent = 'Click to pick from Library or Upload (4–15s)';
          document.getElementById('left-dz-2-title').textContent = 'Add main character (<Picture 1>)';
          document.getElementById('left-dz-2-sub').textContent = 'Then add Outfit, 3D Scene, or Crew below (up to 9 images)';
          renderExtraRefsStrip();
        }
        renderDynamicPromptTagPills();
      } else if (currentMode === 'video') {
        if (mRefBox) mRefBox.style.display = 'none';
        renderDynamicPromptTagPills();
        if (idx === 1) {
          document.getElementById('left-dz-1-title').textContent = 'Add references';
          document.getElementById('left-dz-1-sub').textContent = 'Image, Video or Audio';
        } else {
          document.getElementById('left-dz-1-title').textContent = 'Add video clip to extend';
          document.getElementById('left-dz-1-sub').textContent = 'Seamless 39-frame temporal relay continuation';
        }
      }
    }

    function renderDynamicPromptTagPills() {
      const box = document.getElementById('left-dynamic-tag-pills');
      if (!box) return;
      const isMultiSubTab = document.getElementById('seg-btn-2') && document.getElementById('seg-btn-2').classList.contains('active');
      const pills = [`<span class="mini-tool-pill" style="white-space:nowrap;" onclick="insertPromptTag('<Picture 1>')">&lt;Picture 1&gt;</span>`];
      if (currentMode === 'shinjutsu' && isMultiSubTab && extraShinjutsuRefs.length > 0) {
        extraShinjutsuRefs.forEach((_, idx) => {
          const pNum = idx + 2;
          pills.push(`<span class="mini-tool-pill" style="white-space:nowrap;" onclick="insertPromptTag('<Picture ${pNum}>')">&lt;Picture ${pNum}&gt;</span>`);
        });
      }
      pills.push(`<span class="mini-tool-pill" style="white-space:nowrap;" onclick="insertPromptTag('<Video 1>')">&lt;Video 1&gt;</span>`);
      box.innerHTML = pills.join('');
    }

    function isStudioSoundEnabled() {
      const el = document.getElementById('left-sound-pill');
      return el ? el.classList.contains('active-sound') : true;
    }

    function isLeftPromptEnabled() {
      const t = document.getElementById('left-prompt-toggle');
      return t ? t.classList.contains('on') : true;
    }

    function buildAutoReferencePromptFromSlots() {
      let base = 'Replace the person in <Video 1> with the character in <Picture 1>';
      const isMultiSubTab = document.getElementById('seg-btn-2') && document.getElementById('seg-btn-2').classList.contains('active');
      if (currentMode === 'shinjutsu' && isMultiSubTab && extraShinjutsuRefs.length > 0) {
        extraShinjutsuRefs.forEach((item, idx) => {
          const tag = `<Picture ${idx + 2}>`;
          if (item.role === 'outfit') base += ` wearing the outfit and accessories from ${tag}`;
          else if (item.role === 'scene') base += ` inside the background environment of ${tag} (re-projected into 3D perspective)`;
          else if (item.role === 'crew') base += ` while replacing the supporting dancers with the crew in ${tag}`;
        });
      }
      return base + '.';
    }

    function getEffectiveStudioPrompt() {
      if ((currentMode === 'shinjutsu' || currentMode === 'video') && !isLeftPromptEnabled()) {
        return buildAutoReferencePromptFromSlots();
      }
      const rawPrompt = (document.getElementById('prompt-input').value || '').trim() || buildAutoReferencePromptFromSlots();
      if (currentMode === 'cinema') {
        const film = DIRECTOR_PRESETS.film[directorIdx.film] || '35mm IMAX';
        const cam = DIRECTOR_PRESETS.camera[directorIdx.camera] || 'Bullet Time 360°';
        const col = DIRECTOR_PRESETS.color[directorIdx.color] || 'Natural';
        const lgt = DIRECTOR_PRESETS.light[directorIdx.light] || 'Soft Key';
        const cleanScene = rawPrompt.replace(/^\[CAMERA:[^\]]+\]\s*/i, '').trim();
        return `Shot on ${film}, ${cam} camera motion, ${col} color grading, ${lgt} lighting. ${cleanScene}`;
      }
      if (currentMode === 'soul') {
        const angle = CHAR_ID_PRESETS.film[charIdIdx.film] || '85mm Close Portrait';
        const outfit = CHAR_ID_PRESETS.camera[charIdIdx.camera] || 'Keep Original Outfit';
        const world = CHAR_ID_PRESETS.color[charIdIdx.color] || 'Clean Studio Backdrop';
        const lockTier = CHAR_ID_PRESETS.light[charIdIdx.light] || 'Strict Lock (100%)';
        const outfitClause = outfit.includes('Original')
          ? 'preserving their signature wardrobe'
          : `wearing ${outfit}`;
        const lockClause = lockTier.includes('Strict')
          ? 'Keep the exact facial identity, eye shape, skin tone, and hairstyle of the person in <ref_image_0>'
          : (lockTier.includes('Balanced')
              ? 'Maintain the facial identity and features of <ref_image_0>'
              : 'Inspired by the character in <ref_image_0>');
        return `${lockClause}, ${outfitClause}, framed as a ${angle} in a ${world}. ${rawPrompt}`;
      }
      return rawPrompt;
    }

    function toggleLeftPromptBox() {
      const t = document.getElementById('left-prompt-toggle');
      const b = document.getElementById('left-prompt-body');
      const h = document.getElementById('left-prompt-auto-hint');
      const isOn = t.classList.toggle('on');
      if (b) b.style.display = isOn ? 'flex' : 'none';
      if (h) h.style.display = isOn ? 'none' : 'block';
      showToast(isOn ? 'Custom Prompt ON' : 'Auto Reference Mode ON (no custom prompt needed)');
    }

    function toggleSoundPill(el) {
      const isOn = el.classList.toggle('active-sound');
      el.textContent = isOn ? 'Audio: On' : 'Audio: Muted';
      showToast(isOn ? 'Output Audio: ON (Synced Soundtrack)' : 'Output Audio: Muted (Silent Video)');
    }

    function stepBatchCount(delta) {
      currentBatchCount = Math.max(1, Math.min(4, currentBatchCount + delta));
      const el = document.getElementById('chip-batch-txt');
      if (el) el.textContent = `${currentBatchCount}/4`;
    }

    function renderVisualQualityPopover() {
      const geom = getActiveDimensionsAndFrames();
      const qMap = (geom.spec && geom.spec.qualitySteps) || { High: 20, Ultra: 28, Fast: 8 };
      const tierLabels = ['High', 'Ultra', 'Fast'];
      const tierSuffixes = { High: 'Studio', Ultra: 'Max', Fast: 'Turbo' };
      tierLabels.forEach((lbl, idx) => {
        const dEl = document.getElementById(`pop-q-desc-${idx}`);
        if (dEl) dEl.textContent = `${qMap[lbl]} Steps · ${tierSuffixes[lbl]}`;
      });
      const defaultStep = qMap[tierLabels[qualityTierIdx]] || geom.spec.steps || 20;
      const activeSteps = customStepsOverride || defaultStep;
      const matchedName = tierLabels.find(nm => qMap[nm] === activeSteps);
      const readout = document.getElementById('pop-steps-readout');
      if (readout) readout.textContent = matchedName ? `${activeSteps} Steps · ${matchedName}` : `${activeSteps} Steps · Custom`;
      const cInp = document.getElementById('pop-custom-steps');
      if (cInp) cInp.value = activeSteps;
      document.querySelectorAll('#pop-quality .ratio-card').forEach(c => {
        c.classList.toggle('active', Boolean(matchedName && c.getAttribute('data-q') === matchedName));
      });
    }

    function selectVisualQuality(idx) {
      qualityTierIdx = idx;
      const geom = getActiveDimensionsAndFrames();
      const qMap = (geom.spec && geom.spec.qualitySteps) || { High: 20, Ultra: 28, Fast: 8 };
      const tierLabels = ['High', 'Ultra', 'Fast'];
      const chosenLabel = tierLabels[qualityTierIdx] || 'High';
      const chosenSteps = qMap[chosenLabel] || 20;
      customStepsOverride = chosenSteps;
      updateRatioAndDurationChips();
      renderVisualQualityPopover();
      if (tweakingWorkflowObj) syncSimpleValuesIntoTweakingWorkflow();
      document.getElementById('pop-quality').classList.remove('open');
      showToast(`Quality: ${chosenLabel} (${chosenSteps} Steps)`);
    }

    function applyPopoverCustomSteps() {
      const inp = document.getElementById('pop-custom-steps');
      const s = parseInt(inp && inp.value, 10);
      if (s >= 1 && s <= 50) {
        customStepsOverride = s;
        const geom = getActiveDimensionsAndFrames();
        const qMap = (geom.spec && geom.spec.qualitySteps) || { High: 20, Ultra: 28, Fast: 8 };
        const tierLabels = ['High', 'Ultra', 'Fast'];
        const matchIdx = tierLabels.findIndex(nm => qMap[nm] === s);
        if (matchIdx >= 0) qualityTierIdx = matchIdx;
        updateRatioAndDurationChips();
        renderVisualQualityPopover();
        if (tweakingWorkflowObj) syncSimpleValuesIntoTweakingWorkflow();
        document.getElementById('pop-quality').classList.remove('open');
        showToast(`Sampling Steps: ${s} Steps`);
      }
    }

    function renderVisualResTierPopover() {
      const geom = getActiveDimensionsAndFrames();
      const tiers = geom.resTiers || IMAGE_RES_TIERS;
      tiers.forEach((rt, idx) => {
        const wh = (rt.ratios && rt.ratios[currentRatio]) || geom.spec.ratios[currentRatio] || [896, 1152];
        const bEl = document.getElementById(`pop-rt-badge-${idx}`);
        const lEl = document.getElementById(`pop-rt-lbl-${idx}`);
        const dEl = document.getElementById(`pop-rt-dim-${idx}`);
        if (bEl) {
          bEl.textContent = rt.badge || '';
          bEl.style.color = (!geom.isCustomSize && idx === resTierIdx) ? 'var(--accent)' : 'var(--muted)';
        }
        if (lEl) lEl.textContent = rt.label;
        if (dEl) dEl.textContent = `${wh[0]} × ${wh[1]}`;
      });
      const readout = document.getElementById('pop-tier-res-readout');
      if (readout) readout.textContent = `${geom.width} × ${geom.height} px`;
      const rtw = document.getElementById('pop-rt-custom-w');
      const rth = document.getElementById('pop-rt-custom-h');
      if (rtw && rth) { rtw.value = geom.width; rth.value = geom.height; }
      document.querySelectorAll('#pop-res-tier .ratio-card').forEach(c => {
        const cIdx = parseInt(c.getAttribute('data-rt-idx'), 10);
        c.classList.toggle('active', !geom.isCustomSize && cIdx === resTierIdx);
      });
    }

    function selectVisualResTier(idx) {
      resTierIdx = idx;
      customWidthOverride = null;
      customHeightOverride = null;
      updateRatioAndDurationChips();
      renderVisualResTierPopover();
      if (tweakingWorkflowObj) syncSimpleValuesIntoTweakingWorkflow();
      document.getElementById('pop-res-tier').classList.remove('open');
      const geom = getActiveDimensionsAndFrames();
      const lbl = geom.activeResTier ? geom.activeResTier.label : '';
      showToast(`Resolution: ${lbl} (${geom.width}×${geom.height}px)`);
    }

    function cycleQualityPill() {
      selectVisualQuality((qualityTierIdx + 1) % QUALITY_TIERS.length);
    }

    function cycleResTierPill() {
      const tiers = getActiveDimensionsAndFrames().resTiers || IMAGE_RES_TIERS;
      selectVisualResTier((resTierIdx + 1) % tiers.length);
    }

    const DIRECTOR_PRESETS = {
      film: ['Auto (35mm IMAX)', 'Anamorphic 65mm', 'Kodak Vision3 500T', 'Super 16mm Grain'],
      camera: ['Bullet Time 360°', 'Crash Zoom', 'Vertigo Dolly', 'FPV Drone Dive', 'Slow Arc Orbit', 'Handheld Documentary'],
      color: ['Auto (Natural)', 'Teal & Amber Cinema', 'Bleach Bypass Noir', 'Warm Golden Hour'],
      light: ['Auto (Soft Key)', 'Volumetric Rim Light', 'Neon Cyberpunk Glow', 'Chiaroscuro Studio']
    };
    const DIRECTOR_TITLES = {
      film: 'Film Setup & Lens',
      camera: 'Camera Choreography',
      color: 'Cinema Color Palette',
      light: 'Studio Lighting'
    };
    const CHAR_ID_PRESETS = {
      film: ['85mm Close Portrait', '3/4 Cinematic Profile', 'Full-Body Fashion Shot', 'Low-Angle Hero Shot', 'Over-the-Shoulder', '3-Angle Turnaround Sheet'],
      camera: ['Keep Original Outfit', 'Cyberpunk Silver Techwear', 'Paris Haute Couture', 'Tactical Winter Armor', 'Streetwear Varsity', 'Tailored Noir Suit'],
      color: ['Clean Studio Backdrop', 'Rain-Lit Neon Alley', 'Paris Golden Hour', 'Alpine Snow Peak', 'Orbital Spacecraft', 'Tokyo Shibuya Night'],
      light: ['Strict Lock (100%)', 'Balanced (85%)', 'Stylized Restyle (70%)']
    };
    const CHAR_ID_TITLES = {
      film: 'Camera Angle & Framing',
      camera: 'Character Wardrobe',
      color: 'World & Environment',
      light: 'Identity Lock Strength'
    };
    const directorIdx = { film: 0, camera: 0, color: 0, light: 0 };
    const charIdIdx = { film: 0, camera: 0, color: 0, light: 0 };

    function renderDirectorStripForMode(mode) {
      const isSoul = mode === 'soul';
      const presets = isSoul ? CHAR_ID_PRESETS : DIRECTOR_PRESETS;
      const idxMap = isSoul ? charIdIdx : directorIdx;
      const labels = isSoul
        ? { ref: 'Face Lock', film: 'Camera Angle', camera: 'Wardrobe', color: 'World / Scene', light: 'Identity Lock' }
        : { ref: 'References', film: 'Film setup', camera: 'Camera', color: 'Color palette', light: 'Lighting' };
      const icons = isSoul
        ? { film: 'AN', camera: 'WD', color: 'SC', light: 'ID' }
        : { film: 'FL', camera: 'CM', color: 'CL', light: 'LT' };

      const refLbl = document.getElementById('dir-lbl-ref');
      if (refLbl) refLbl.textContent = labels.ref;
      const refCnt = document.getElementById('dir-ref-count');
      if (refCnt) refCnt.textContent = isSoul ? (hasUserSlot1Ref ? 'Locked ✓' : '1 Photo') : (hasUserSlot1Ref ? '1 / 9' : '0 / 9');

      ['film', 'camera', 'color', 'light'].forEach(k => {
        const lEl = document.getElementById(`dir-lbl-${k}`);
        const vEl = document.getElementById(`dir-val-${k}`);
        const iEl = document.getElementById(`dir-ico-${k}`);
        if (lEl) lEl.textContent = labels[k];
        if (vEl && presets[k]) vEl.textContent = presets[k][idxMap[k]] || presets[k][0];
        if (iEl) iEl.textContent = icons[k];
      });
    }

    function openDirectorPopover(key, ev) {
      const isSoul = currentMode === 'soul';
      const presets = isSoul ? CHAR_ID_PRESETS : DIRECTOR_PRESETS;
      const titles = isSoul ? CHAR_ID_TITLES : DIRECTOR_TITLES;
      const idxMap = isSoul ? charIdIdx : directorIdx;
      const arr = presets[key];
      if (!arr) return;
      const titleEl = document.getElementById('pop-director-title');
      const listEl = document.getElementById('pop-director-list');
      if (titleEl) titleEl.textContent = titles[key] || 'Preset';
      if (listEl) {
        listEl.innerHTML = arr.map((item, idx) => {
          const isAct = idxMap[key] === idx;
          return `
            <div class="model-pop-item ${isAct ? 'active' : ''}" onclick="selectDirectorPreset('${key}', ${idx})">
              <div style="font-size:12.5px; font-weight:700; color:var(--text);">${item}</div>
              <span style="color:${isAct ? 'var(--accent)' : 'var(--muted)'}; font-size:12px;">${isAct ? '●' : '○'}</span>
            </div>
          `;
        }).join('');
      }
      toggleDockPopover('pop-director', ev);
    }

    function selectDirectorPreset(key, idx) {
      const isSoul = currentMode === 'soul';
      const presets = isSoul ? CHAR_ID_PRESETS : DIRECTOR_PRESETS;
      const titles = isSoul ? CHAR_ID_TITLES : DIRECTOR_TITLES;
      const idxMap = isSoul ? charIdIdx : directorIdx;
      const arr = presets[key];
      if (!arr) return;
      idxMap[key] = idx;
      const val = arr[idx];
      const el = document.getElementById(`dir-val-${key}`);
      if (el) el.textContent = val;
      document.getElementById('pop-director').classList.remove('open');
      showToast(`${titles[key]}: ${val}`);
    }

    function cycleDirectorCard(key) {
      const arr = DIRECTOR_PRESETS[key];
      if (!arr) return;
      selectDirectorPreset(key, (directorIdx[key] + 1) % arr.length);
    }

    function getTemplateReadiness(t) {
      const n = ((t && t.name) || '').toLowerCase();
      const ti = ((t && t.title) || '').toLowerCase();
      let bundleKey = '';
      if (n.includes('minimax_h3_r2v') || n.includes('ref2v') || n.includes('ominiref')) bundleKey = 'shinjutsu_svd_33mb';
      else if (n.includes('minimax') || n.includes('h3')) bundleKey = 'minimax_h3_fl2va_int8';
      else if (n.includes('ltx')) bundleKey = 'ltx23_22b_fp8';
      else if (n.includes('wan')) bundleKey = 'wan22_animate_14b';
      else if (n.includes('music') || n.includes('audio')) bundleKey = 'minimax_music_3';
      else if (n.includes('krea')) bundleKey = 'krea2_turbo_fp8';
      else if (n.includes('flux3') || n.includes('klein') || n.includes('character_angles')) bundleKey = 'flux3_klein';
      else if (n.includes('flux')) bundleKey = 'flux1_dev_fp8';

      if (t && Array.isArray(t.requiredModels) && t.requiredModels.length > 0) {
        const missingCustom = t.requiredModels.filter(rm => {
          const base = (rm.name || '').split('/').pop();
          const entry = cachedModels.find(cm => cm.name.split('/').pop() === base);
          return !entry || !entry.installed;
        });
        return { ready: missingCustom.length === 0, missingCount: missingCustom.length, bundleKey };
      }
      if (bundleKey) {
        const b = getModelBundleReadiness(bundleKey);
        return { ready: b.ready, missingCount: b.missing.length, bundleKey };
      }
      // For other external templates (e.g. Z-Image, Bernini, Qwen), check if a matching model is installed in cachedModels
      const matchInstalled = cachedModels.some(cm => cm.installed && cm.folder === 'diffusion_models' && (n.includes(cm.id.split('_')[0]) || ti.includes(cm.title.toLowerCase())));
      return { ready: matchInstalled, missingCount: matchInstalled ? 0 : 1, bundleKey: '' };
    }

    function renderMotionLibraryGrid() {
      const grid = document.getElementById('motion-lib-grid');
      if (!grid) return;
      const q = ((document.getElementById('motion-lib-search') && document.getElementById('motion-lib-search').value) || '').toLowerCase().trim();
      let list = comfyOfficialTemplates.filter(t => {
        const c = (t.category || '').toLowerCase();
        const n = (t.name || '').toLowerCase();
        const ti = (t.title || '').toLowerCase();
        if (ti.includes('text to image') || ti.includes('image edit') || n.includes('t2i') || c.includes('audio')) return false;
        if (currentMode === 'video' && (n.includes('r2v') || n.includes('replace') || ti.includes('replacement'))) return false;
        return c.includes('video') || n.includes('video') || n.includes('animate') || n.includes('r2v') || n.includes('i2v') || n.includes('fl2va') || ti.includes('video');
      });
      if (!list.length) list = comfyOfficialTemplates.slice(0, 12);
      if (q) {
        list = list.filter(t => (t.title || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q));
      }
      grid.innerHTML = list.slice(0, 18).map(t => {
        const thumbUrl = `${COMFY_TPL_CDN}/${t.name}-1.webp`;
        const safeTitle = (t.title || '').replace(/'/g, "\\'");
        const safeDesc = (t.description || '').replace(/'/g, "\\'");
        const rInfo = getTemplateReadiness(t);
        const btnLabel = rInfo.ready ? (activeTemplateSlug === t.name ? 'Active' : 'Recreate') : 'Setup';
        const btnStyle = rInfo.ready
          ? (activeTemplateSlug === t.name ? 'background:var(--accent);color:#09090b;border-color:var(--accent);' : '')
          : 'border-color:rgba(242,255,89,0.45);color:var(--accent);background:rgba(10,10,12,0.85);';
        return `
          <div class="motion-card" onclick="openComfyOfficialTemplate('${t.name}', '${safeTitle}', '${safeDesc}', '${t.category}', true)">
            <img class="motion-card-thumb" src="${thumbUrl}" loading="lazy" onerror="this.src='https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/video_minimax_h3_r2v-1.webp'" alt="${safeTitle}" />
            <div class="motion-card-over">
              <div class="motion-card-title">${t.title}</div>
              <span class="motion-use-btn" style="${btnStyle}">${btnLabel}</span>
            </div>
          </div>
        `;
      }).join('');
    }

    function switchRightStageTab(tab) {
      document.getElementById('rtab-library').classList.toggle('active', tab === 'library');
      document.getElementById('rtab-history').classList.toggle('active', tab === 'history');
      if (tab === 'history') {
        const grid = document.getElementById('motion-lib-grid');
        if (!sessionHistory.length) {
          showToast('No session history yet — generate or click a preset!');
          return;
        }
        grid.innerHTML = sessionHistory.map(h => {
          const mediaHtml = h.type === 'video'
            ? `<video class="motion-card-thumb" src="${h.url}" muted loop playsinline preload="metadata" onmouseenter="this.play().catch(()=>{})" onmouseleave="this.pause()"></video>`
            : (h.type === 'audio'
                ? `<div class="motion-card-thumb" style="display:flex;align-items:center;justify-content:center;background:#141418;font-size:13px;font-weight:800;color:var(--accent);">AUDIO</div>`
                : `<img class="motion-card-thumb" src="${h.url}" />`);
          return `
            <div class="motion-card" onclick="loadDemoMedia('${h.type}', '${h.url}', '${h.caption || ''}')">
              ${mediaHtml}
              <div class="motion-card-over">
                <div class="motion-card-title">${h.caption || 'Creation'}</div>
                <span class="motion-use-btn">View</span>
              </div>
            </div>
          `;
        }).join('');
      } else {
        renderMotionLibraryGrid();
      }
    }

    function closeRightActivePlayer() {
      const rv = document.getElementById('right-stage-video');
      if (rv) rv.pause();
      document.getElementById('right-active-player').style.display = 'none';
      document.getElementById('right-hero-banner').style.display = 'flex';
    }

    let cachedModels = [
      { id: 'shinjutsu_svd_33mb', name: 'shinjutsu_h3_control_lora_v1_flash.safetensors', title: 'SHINJUTSU Motion Engine', folder: 'model_patches', size_mb: 33.34, actual_size_mb: 33.34, installed: true, source: 'local_disk', description: 'Built-in 10-block motion adapter (33.3 MB)' },
      { id: 'birefnet_lite_84mb', name: 'birefnet_lite_fp16.safetensors', title: 'SHINJUTSU Background Cleaner', folder: 'bg_removers', size_mb: 84.84, actual_size_mb: 84.84, installed: true, source: 'local_disk', description: 'Built-in automatic subject cutout (84.8 MB)' },
      { id: 'minimax_h3_ref2va_int8', name: 'minimax_h3_ref2va_pruned_int8_convrot.safetensors', title: 'MiniMax H3 Ref2VA', folder: 'diffusion_models', size_mb: 26500, installed: false, description: 'Full-reference audio + video generation model' },
      { id: 'minimax_h3_fl2va_int8', name: 'minimax_h3_fl2va_pruned_int8_convrot.safetensors', title: 'MiniMax H3 I2V', folder: 'diffusion_models', size_mb: 26500, installed: false, description: 'Official MiniMax H3 Image-to-Video + 8-Step Turbo model' },
      { id: 'ltx23_22b_fp8', name: 'ltx-2.3-22b-dev-fp8.safetensors', title: 'LTX-2.3 22B', folder: 'checkpoints', size_mb: 23500, installed: false, description: 'Fast audio-video & Cinema Studio model' },
      { id: 'krea2_turbo_fp8', name: 'krea2_stock_turbo_fp8_scaled.safetensors', title: 'Krea 2', folder: 'diffusion_models', size_mb: 12800, installed: false, description: 'Photorealistic portrait & Character ID model' },
      { id: 'flux1_dev_fp8', name: 'flux1-dev-fp8.safetensors', title: 'FLUX.1 Dev', folder: 'diffusion_models', size_mb: 11900, installed: false, description: 'High-detail image generation model' },
      { id: 'wan22_animate_14b', name: 'wan2.2_animate_14B_fp8_e4m3fn.safetensors', title: 'Wan 2.2 Animate', folder: 'diffusion_models', size_mb: 14200, installed: false, description: 'Character animation & video model' }
    ];

    const CURATED_STUDIO_TEMPLATES = [
      { name: 'video_minimax_h3_r2v', title: 'Character & Motion Replacement', category: 'Video', description: 'Match character identity, outfit, choreography, and stereo audio in a single pass.' },
      { name: 'template_ltx2_3_ic_lora_ingredients', title: 'Cinema Camera & Reference Control', category: 'Character & Fashion', description: 'Direct multi-element character consistency and camera motion with LTX-2.3.' },
      { name: 'template_purz_wan22_animate_auto_character_replace', title: 'Automatic Character Replacement', category: 'Character & Fashion', description: 'Replace the performer in any video while keeping pose and lighting.' },
      { name: 'video_ltx2_3_i2v', title: 'Image to Video with Sound', category: 'Video', description: 'Turn any still frame into a fluid video clip with synchronized audio.' },
      { name: 'video_ltx2_3_ia2v', title: 'Audio-Driven Lip Sync Video', category: 'Video', description: 'Animate a character portrait directly from a voice or song track.' },
      { name: 'video_minimax_h3_i2v', title: 'MiniMax H3 Image to Video', category: 'Video', description: 'Develop a cinematic scene starting from a single keyframe.' },
      { name: 'video_wan2_2_14B_i2v', title: 'Wan 2.2 Image to Video', category: 'Video', description: 'Natural motion synthesis from a reference image.' },
      { name: 'templates-1_click_multiple_character_angles-v1.0', title: 'Multi-Angle Character Sheet', category: 'Character & Fashion', description: 'Generate multiple camera angles from a single portrait photo.' },
      { name: 'flux1_krea_dev', title: '4K Studio Portrait', category: 'Image', description: 'Ultra-detailed natural skin texture and studio lighting.' },
      { name: 'flux1_dev_uso_reference_image_gen', title: 'Consistent Character Scene', category: 'Image', description: 'Preserve subject identity across new outfits and environments.' },
      { name: 'audio_minimax_music_3', title: 'Text to Music & Vocals', category: 'Audio', description: 'Generate full-band music and vocals from a text description.' }
    ];
    let comfyOfficialTemplates = [...CURATED_STUDIO_TEMPLATES];

    const MODE_CONFIG = {
      images: {
        title: 'IMAGE',
        sub: 'Create photorealistic portraits and scenes.',
        slot1: 'Ref',
        slot2: null,
        showDuration: false,
        prompt: 'A raw 4K DSLR portrait in natural studio lighting, authentic skin texture.',
        models: [
          { id: 'flux3_klein', label: 'FLUX 3 Klein' },
          { id: 'flux2_klein_4b', label: 'FLUX 3 Klein (Fast · 4-Step)' },
          { id: 'krea2_turbo_fp8', label: 'Krea 2' },
          { id: 'qwen_img21', label: 'Qwen Image 2.1' }
        ]
      },
      video: {
        title: 'VIDEO',
        sub: 'Generate fluid video clips with synchronized sound.',
        slot1: 'Start',
        slot2: 'End',
        showDuration: true,
        prompt: 'Natural fluid motion, realistic camera movement, synchronized ambient sound.',
        models: [
          { id: 'minimax_h3_fl2va_int8', label: 'MiniMax H3' },
          { id: 'ltx23_22b_fp8', label: 'LTX-2.3' },
          { id: 'wan22_animate_14b', label: 'Wan 2.2' }
        ]
      },
      cinema: {
        title: 'CINEMA STUDIO',
        sub: 'Pick a camera move and direct cinematic shots.',
        slot1: 'Frame',
        slot2: null,
        showDuration: true,
        prompt: 'A lone futuristic rider drifting through rain-slicked Neo-Tokyo streets at night.',
        models: [
          { id: 'ltx23_22b_fp8', label: 'LTX-2.3 Cinema' },
          { id: 'flux2_klein_4b', label: 'FLUX 3 Klein (16GB Keyframe)' },
          { id: 'minimax_h3_ref2va_int8', label: 'MiniMax H3 Director' },
          { id: 'wan22_animate_14b', label: 'Wan 2.2 Camera' }
        ]
      },
      soul: {
        title: 'CHARACTER ID (BETA)',
        sub: 'Attach 1 photo to lock character identity across any outfit or scene.',
        slot1: 'Face',
        slot2: null,
        showDuration: false,
        prompt: 'Natural editorial lighting, sharp focus on eyes and authentic skin texture.',
        models: [
          { id: 'flux3_klein', label: 'FLUX 3 Klein Character ID' },
          { id: 'flux2_klein_4b', label: 'FLUX 3 Klein (Fast · 4-Step)' },
          { id: 'krea2_turbo_fp8', label: 'Krea 2 Character ID' },
          { id: 'qwen_img21', label: 'Qwen Character' }
        ]
      },
      shinjutsu: {
        title: 'SHINJUTSU',
        sub: 'Attach a character photo and a motion video below to replace the performer.',
        slot1: 'Char',
        slot2: 'Video',
        showDuration: true,
        prompt: 'Replace the person in <Video 1> with the character in <Picture 1>.',
        models: [
          { id: 'shinjutsu_pro_pod', label: 'Shinjutsu (High)' },
          { id: 'shinjutsu_svd_33mb', label: 'Shinjutsu (Medium)' },
          { id: 'shinjutsu_16gb_turbo', label: 'Shinjutsu (Turbo)' }
        ]
      },
      audio: {
        title: 'AUDIO',
        sub: 'Generate full-band music, vocals, and soundscapes from text.',
        slot1: null,
        slot2: null,
        showDuration: true,
        prompt: 'Upbeat electronic pop track with clear female vocals, warm synth bass, and crisp drums.',
        models: [
          { id: 'minimax_music_3', label: 'MiniMax Music 3' },
          { id: 'acestep_15', label: 'ACE-Step 1.5' },
          { id: 'yue2_music', label: 'YuE2 Music' }
        ]
      }
    };

    function openExplore(catFilter) {
      closeSettingsModal();
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      document.getElementById('explore-view').classList.remove('hidden');
      document.getElementById('studio-view').classList.remove('active');
      document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.getAttribute('data-nav') === 'explore');
      });
      if (catFilter) {
        const pill = Array.from(document.querySelectorAll('.filter-pill')).find(p => p.textContent.includes(catFilter));
        filterComfyGrid(catFilter, pill);
      }
    }

    function setMode(mode, preservePreview) {
      if (!MODE_CONFIG[mode]) mode = 'shinjutsu';
      closeSettingsModal();
      currentMode = mode;
      activeExternalWorkflow = null;
      customWidthOverride = null;
      customHeightOverride = null;
      customFramesOverride = null;
      customStepsOverride = null;

      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      document.getElementById('explore-view').classList.add('hidden');
      document.getElementById('studio-view').classList.add('active');

      document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.getAttribute('data-nav') === mode);
      });

      const isSidebarLayout = (mode === 'shinjutsu' || mode === 'video');
      document.getElementById('sidebar-workspace').classList.toggle('active', isSidebarLayout);
      document.getElementById('bottom-workspace').classList.toggle('active', !isSidebarLayout);

      // Keep Left Sidebar top subtabs & prompt toggle in sync
      const stVid = document.getElementById('left-subtab-video');
      const stMot = document.getElementById('left-subtab-motion');
      if (stVid) stVid.classList.toggle('active', mode === 'video');
      if (stMot) stMot.classList.toggle('active', mode === 'shinjutsu');
      const pToggle = document.getElementById('left-prompt-toggle');
      const pBody = document.getElementById('left-prompt-body');
      const pHint = document.getElementById('left-prompt-auto-hint');
      if (pToggle && pBody) {
        pToggle.classList.add('on');
        pBody.style.display = 'flex';
      }
      if (pHint) pHint.style.display = 'none';

      // Reset stale preview players when switching modes cleanly (unless preservePreview is true)
      if (!preservePreview) {
        closeRightActivePlayer();
        resetStage();
      }

      const cfg = MODE_CONFIG[mode];
      document.getElementById('stage-title').textContent = `START CREATING WITH ${cfg.title.replace(/\s+/g, ' ')}`;
      document.getElementById('stage-sub').textContent = cfg.sub;

      const s1 = document.getElementById('slot-1');
      if (cfg.slot1) {
        s1.style.display = 'flex';
        document.getElementById('slot-1-lbl').textContent = cfg.slot1;
      } else {
        s1.style.display = 'none';
      }

      const s2 = document.getElementById('slot-2');
      if (cfg.slot2) {
        s2.style.display = 'flex';
        document.getElementById('slot-2-lbl').textContent = cfg.slot2;
      } else {
        s2.style.display = 'none';
      }

      document.getElementById('chip-ratio').style.display = mode === 'audio' ? 'none' : 'inline-flex';
      const rtChip = document.getElementById('chip-res-tier');
      if (rtChip) rtChip.style.display = mode === 'audio' ? 'none' : 'inline-flex';
      const spRef = document.getElementById('chip-split-ref');
      if (spRef) spRef.style.display = mode === 'audio' ? 'none' : 'inline-flex';
      document.getElementById('chip-duration').style.display = cfg.showDuration ? 'inline-flex' : 'none';
      if (mode === 'audio') currentDurationSec = 30.0;
      else if (mode === 'cinema' && currentDurationSec > 10.7) currentDurationSec = 5.0;
      else if (mode === 'shinjutsu') currentDurationSec = 13.0;
      document.getElementById('prompt-input').value = cfg.prompt;
      const leftPrompt = document.getElementById('left-prompt-input');
      if (leftPrompt) leftPrompt.value = cfg.prompt;

      // Configure Left Sidebar when in SHINJUTSU or Video mode
      const mRefBox = document.getElementById('left-multi-ref-box');
      if (mRefBox) mRefBox.style.display = 'none';
      if (mode === 'shinjutsu') {
        const lBox1 = document.getElementById('left-dz-video-box');
        const lBox2 = document.getElementById('left-dz-char-box');
        if (lBox1) lBox1.style.display = 'flex';
        if (lBox2) lBox2.style.display = 'flex';
        document.getElementById('left-preset-title').textContent = 'SHINJUTSU Motion';
        document.getElementById('left-preset-img').src = '/shinjutsu/web/img/hero/shinjutsu_result.webp';
        document.getElementById('seg-lbl-1').textContent = 'Motion transfer';
        document.getElementById('seg-lbl-2').textContent = 'Multi-Ref Swap';
        selectLeftSubMode(1);
        document.getElementById('right-hero-badge').textContent = 'SHINJUTSU 1.0';
        document.getElementById('right-hero-title').textContent = 'TRANSFER ANY MOTION TO YOUR CHARACTER';
        document.getElementById('right-hero-desc').textContent = 'Upload any dance clip + 1 character photo in Motion Transfer, or switch to Multi-Ref Swap to attach up to 9 images (Character, Outfit, 3D Scene, or Supporting Crew).';
        const hcImg1 = document.getElementById('hero-card-img-1');
        const hcImg2 = document.getElementById('hero-card-img-2');
        const hcImg3 = document.getElementById('hero-card-img-3');
        const hcLbl1 = document.getElementById('hero-card-lbl-1');
        const hcLbl2 = document.getElementById('hero-card-lbl-2');
        const hcLbl3 = document.getElementById('hero-card-lbl-3');
        const hcOp1 = document.getElementById('hero-card-op-1');
        const hcOp2 = document.getElementById('hero-card-op-2');
        if (hcImg1) hcImg1.src = '/shinjutsu/web/img/hero/shinjutsu_motion_src.webp';
        if (hcImg2) hcImg2.src = '/shinjutsu/web/img/hero/shinjutsu_char_ref.webp';
        if (hcImg3) hcImg3.src = '/shinjutsu/web/img/hero/shinjutsu_result.webp';
        if (hcLbl1) hcLbl1.textContent = '1. Motion Video';
        if (hcLbl2) hcLbl2.textContent = '2. Your Character';
        if (hcLbl3) hcLbl3.textContent = 'Result';
        if (hcOp1) hcOp1.textContent = '+';
        if (hcOp2) hcOp2.textContent = '→';
        renderExtraRefsStrip();
      } else if (mode === 'video') {
        const lBox1 = document.getElementById('left-dz-video-box');
        const lBox2 = document.getElementById('left-dz-char-box');
        if (lBox1) lBox1.style.display = 'flex';
        if (lBox2) lBox2.style.display = 'none';
        const deckVid = document.getElementById('deck-vid-preview');
        const dz1Clr = document.getElementById('left-dz-1-clear');
        if (deckVid && !preservePreview) {
          deckVid.pause();
          deckVid.style.display = 'none';
        }
        if (dz1Clr && !preservePreview) dz1Clr.style.display = 'none';
        document.getElementById('left-preset-title').textContent = 'Create Video';
        document.getElementById('left-preset-img').src = `${COMFY_TPL_CDN}/video_ltx2_3_i2v-1.webp`;
        document.getElementById('seg-lbl-1').textContent = 'References';
        document.getElementById('seg-lbl-2').textContent = 'Extend Video';
        selectLeftSubMode(1);
        document.getElementById('right-hero-badge').textContent = 'OPEN VIDEO STUDIO';
        document.getElementById('right-hero-title').textContent = 'CINEMATIC AUDIO-VIDEO SYNTHESIS';
        document.getElementById('right-hero-desc').textContent = 'Generate high-coherence video clips with synchronized sound using MiniMax H3, LTX-2.3, or Wan 2.2.';
        const hcImg1 = document.getElementById('hero-card-img-1');
        const hcImg2 = document.getElementById('hero-card-img-2');
        const hcImg3 = document.getElementById('hero-card-img-3');
        const hcLbl1 = document.getElementById('hero-card-lbl-1');
        const hcLbl2 = document.getElementById('hero-card-lbl-2');
        const hcLbl3 = document.getElementById('hero-card-lbl-3');
        const hcOp1 = document.getElementById('hero-card-op-1');
        const hcOp2 = document.getElementById('hero-card-op-2');
        if (hcImg1) hcImg1.src = `${COMFY_TPL_CDN}/video_ltx2_3_i2v-1.webp`;
        if (hcImg2) hcImg2.src = `${COMFY_TPL_CDN}/video_minimax_h3_i2v-1.webp`;
        if (hcImg3) hcImg3.src = `${COMFY_TPL_CDN}/video_wan2_2_14B_i2v-1.webp`;
        if (hcLbl1) hcLbl1.textContent = 'LTX-2.3 Audio-Video';
        if (hcLbl2) hcLbl2.textContent = 'MiniMax H3 I2V';
        if (hcLbl3) hcLbl3.textContent = 'Wan 2.2 Video';
        if (hcOp1) hcOp1.textContent = '·';
        if (hcOp2) hcOp2.textContent = '·';
      }

      // Show 5-Card Director Strip above bottom composer when in Cinema Studio or Character ID mode
      const dirStrip = document.getElementById('cinema-director-strip');
      if (dirStrip) {
        dirStrip.classList.toggle('show', mode === 'cinema' || mode === 'soul');
        if (mode === 'cinema' || mode === 'soul') renderDirectorStripForMode(mode);
      }

      populateModelDropdown();
      onModelSelectChange();
      renderMotionLibraryGrid();
    }

    async function loadLiveComfyOfficialIndex() {
      renderComfyExploreGrid('ALL');
      renderMotionLibraryGrid();
      try {
        const res = await fetch(`${COMFY_TPL_CDN}/index.json`);
        if (!res.ok) return;
        const categories = await res.json();
        const pulled = [];
        categories.forEach(cat => {
          const catTitle = cat.title || 'General';
          (cat.templates || []).forEach(t => {
            if (t.openSource === false || (t.name && t.name.startsWith('api_'))) return;
            pulled.push({
              name: t.name,
              title: t.title || t.name,
              category: catTitle,
              description: t.description || ''
            });
          });
        });
        if (pulled.length > 0) {
          const curatedNames = new Set(CURATED_STUDIO_TEMPLATES.map(c => c.name));
          comfyOfficialTemplates = [
            ...CURATED_STUDIO_TEMPLATES,
            ...pulled.filter(p => !curatedNames.has(p.name))
          ];
          renderComfyExploreGrid('ALL');
          renderMotionLibraryGrid();
        }
      } catch (e) {}
    }

    function filterComfyGrid(category, pillEl) {
      activeExploreCategory = category;
      if (pillEl) {
        document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
        pillEl.classList.add('active');
      }
      renderComfyExploreGrid(category);
    }

    function renderComfyExploreGrid(category) {
      const grid = document.getElementById('comfy-explore-grid');
      const q = ((document.getElementById('explore-search') && document.getElementById('explore-search').value) || '').toLowerCase().trim();
      let list = category === 'ALL'
        ? comfyOfficialTemplates
        : comfyOfficialTemplates.filter(t => t.category.toLowerCase().includes(category.toLowerCase()));
      if (q) {
        list = list.filter(t => (t.title || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q) || (t.name || '').toLowerCase().includes(q));
      }
      list = list.slice(0, 48);

      grid.innerHTML = list.map(t => {
        const thumbUrl = `${COMFY_TPL_CDN}/${t.name}-1.webp`;
        const safeTitle = (t.title || '').replace(/'/g, "\\'");
        const safeDesc = (t.description || '').replace(/'/g, "\\'");
        const rInfo = getTemplateReadiness(t);
        const statusPill = rInfo.ready
          ? '<span class="badge ready" style="font-size:10px;">Ready · Recreate</span>'
          : '<span class="badge" style="font-size:10px; border-color:rgba(242,255,89,0.45); color:var(--accent);">Setup</span>';
        return `
          <div class="tpl-card" onclick="openComfyOfficialTemplate('${t.name}', '${safeTitle}', '${safeDesc}', '${t.category}')">
            <div class="tpl-thumb-wrap">
              <img src="${thumbUrl}" loading="lazy" onerror="this.src='https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/video_minimax_h3_r2v-1.webp'" alt="${safeTitle}" />
            </div>
            <div class="tpl-body">
              <div class="tpl-title">${t.title}</div>
              <div class="tpl-desc">${t.description || ''}</div>
              <div style="margin-top:6px; display:flex; align-items:center; justify-content:space-between;">
                ${statusPill}
                <span style="font-size:10px; opacity:.55;">${t.category || 'Workflow'}</span>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    /* Extract embedded `properties.models` from both top-level `nodes` and nested `definitions.subgraphs` */
    function extractModelsFromWorkflowJson(wf) {
      const found = [];
      const seen = new Set();
      function scanNodes(nodesArr) {
        if (!Array.isArray(nodesArr)) return;
        nodesArr.forEach(n => {
          const models = (n && n.properties && n.properties.models) || [];
          models.forEach(m => {
            if (m && m.name && !seen.has(m.name)) {
              seen.add(m.name);
              found.push({
                name: m.name,
                directory: m.directory || 'diffusion_models',
                url: m.url || ''
              });
            }
          });
        });
      }
      if (wf && typeof wf === 'object') {
        scanNodes(wf.nodes);
        if (wf.definitions && Array.isArray(wf.definitions.subgraphs)) {
          wf.definitions.subgraphs.forEach(sg => scanNodes(sg.nodes));
        }
      }
      return found;
    }

    function registerTemplateModelsIntoMenu(tplModels, targetMode, tplTitle) {
      const missing = [];
      tplModels.forEach(tm => {
        const baseName = tm.name.split('/').pop();
        let entry = cachedModels.find(cm => cm.name.split('/').pop() === baseName);
        if (!entry) {
          const cleanId = 'tpl_' + baseName.replace(/[^a-zA-Z0-9]/g, '_');
          const cleanLabel = baseName.replace(/\.(safetensors|ckpt|gguf|pth|onnx)$/i, '').replace(/[_-]/g, ' ');
          entry = {
            id: cleanId,
            name: tm.name,
            title: cleanLabel,
            category: targetMode,
            folder: tm.directory || 'diffusion_models',
            size_mb: 1500,
            installed: false,
            url: tm.url || '',
            description: `Required by "${tplTitle}" (models/${tm.directory || 'diffusion_models'})`
          };
          cachedModels.unshift(entry);
        }
        // Only add primary diffusion/checkpoint model to the active mode's dropdown menu if ALREADY installed!
        if ((entry.folder === 'diffusion_models' || entry.folder === 'checkpoints') && entry.installed) {
          const modeList = MODE_CONFIG[targetMode].models;
          if (!modeList.some(x => x.id === entry.id || x.label === entry.title)) {
            modeList.unshift({ id: entry.id, label: entry.title });
          }
        }
        if (!entry.installed) {
          missing.push(entry);
        }
      });
      populateModelDropdown();
      return missing;
    }

    /* Auto-detect the exact studio mode & required input slots from the template's nodes & subgraphs */
    function detectTemplateModeAndSlots(wf, tplName, tplCategory) {
      const catLow = (tplCategory || '').toLowerCase();
      const allTypes = [];
      let loadImageCount = 0;
      let hasLoadVideo = false;
      let hasLoadAudio = false;

      function collect(nodesArr) {
        if (!Array.isArray(nodesArr)) return;
        nodesArr.forEach(n => {
          const t = (n && n.type) || '';
          allTypes.push(t);
          if (t === 'LoadImage') loadImageCount++;
          if (t === 'LoadVideo') hasLoadVideo = true;
          if (t === 'LoadAudio') hasLoadAudio = true;
        });
      }
      if (wf && typeof wf === 'object') {
        collect(wf.nodes);
        if (wf.definitions && Array.isArray(wf.definitions.subgraphs)) {
          wf.definitions.subgraphs.forEach(sg => collect(sg.nodes));
        }
      }
      const joined = allTypes.join(' ').toLowerCase();
      let mode = 'images';
      if (catLow.includes('audio') || joined.includes('saveaudio') || joined.includes('music')) mode = 'audio';
      else if (tplName.includes('minimax_h3_r2v') || tplName.includes('animate') || joined.includes('wananimate') || (loadImageCount > 0 && hasLoadVideo)) mode = 'shinjutsu';
      else if (tplName.includes('ic_lora') || tplName.includes('camera')) mode = 'cinema';
      else if (catLow.includes('video') || joined.includes('savevideo') || joined.includes('savewebm') || joined.includes('createvideo')) mode = 'video';
      else if (catLow.includes('character') || loadImageCount > 0 || joined.includes('imageedit') || joined.includes('kontext')) mode = 'soul';

      return { mode, loadImageCount, hasLoadVideo, hasLoadAudio };
    }

    async function openComfyOfficialTemplate(tplName, tplTitle, tplDesc, tplCategory, stayInCurrentMode) {
      const reqId = ++activeTemplateRequestId;
      customWidthOverride = null;
      customHeightOverride = null;
      customFramesOverride = null;
      customStepsOverride = null;

      const catLow = (tplCategory || '').toLowerCase();
      let targetMode = stayInCurrentMode ? currentMode : 'images';
      if (!stayInCurrentMode) {
        if (catLow.includes('audio')) targetMode = 'audio';
        else if (tplName.includes('minimax_h3_r2v') || tplName.includes('animate')) targetMode = 'shinjutsu';
        else if (tplName.includes('ltx') && tplName.includes('ic_lora')) targetMode = 'cinema';
        else if (catLow.includes('video') || tplName.includes('video') || tplName.includes('i2v')) targetMode = 'video';
        else if (catLow.includes('character')) targetMode = 'soul';
      }

      try {
        let wfJson = null;
        if (customizedTemplatesMap[tplName] && customizedTemplatesMap[tplName].workflow) {
          wfJson = JSON.parse(JSON.stringify(customizedTemplatesMap[tplName].workflow));
        } else {
          const r = await fetch(`${COMFY_TPL_CDN}/${tplName}.json`);
          if (r.ok) wfJson = await r.json();
        }
        if (reqId !== activeTemplateRequestId) return;

        if (wfJson) {
          activeTemplateSlug = tplName;
          const detected = detectTemplateModeAndSlots(wfJson, tplName, tplCategory);
          if (!stayInCurrentMode) {
            targetMode = detected.mode;
          }
          setMode(targetMode, true);
          activeExternalWorkflow = wfJson;

          if (customizedTemplatesMap[tplName]) {
            if (customizedTemplatesMap[tplName].customW && customizedTemplatesMap[tplName].customH) {
              customWidthOverride = customizedTemplatesMap[tplName].customW;
              customHeightOverride = customizedTemplatesMap[tplName].customH;
            }
            if (customizedTemplatesMap[tplName].customFrames) {
              customFramesOverride = customizedTemplatesMap[tplName].customFrames;
            }
            if (customizedTemplatesMap[tplName].customSteps) {
              customStepsOverride = customizedTemplatesMap[tplName].customSteps;
            }
          }

          const finalPrompt = (customizedTemplatesMap[tplName] && customizedTemplatesMap[tplName].prompt) || tplDesc || MODE_CONFIG[targetMode].prompt;
          document.getElementById('prompt-input').value = finalPrompt;
          syncPromptFromBottom(finalPrompt);
          loadDemoMedia('image', `${COMFY_TPL_CDN}/${tplName}-1.webp`, tplTitle);

          // Adapt input slots dynamically (both Bottom Composer AND Left Sidebar!) to match this template's requirements
          const s1 = document.getElementById('slot-1');
          const s2 = document.getElementById('slot-2');
          const lBox1 = document.getElementById('left-dz-video-box');
          const lBox2 = document.getElementById('left-dz-char-box');
          const lTitle1 = document.getElementById('left-dz-1-title');
          const lSub1 = document.getElementById('left-dz-1-sub');
          const lTitle2 = document.getElementById('left-dz-2-title');
          const lSub2 = document.getElementById('left-dz-2-sub');

          if (detected.loadImageCount === 0 && !detected.hasLoadVideo && !detected.hasLoadAudio) {
            s1.style.display = 'none';
            s2.style.display = 'none';
            if (lBox1) lBox1.style.display = 'none';
            if (lBox2) lBox2.style.display = 'none';
          } else {
            s1.style.display = detected.loadImageCount > 0 ? 'flex' : 'none';
            if (detected.hasLoadAudio) {
              s2.style.display = 'flex';
              document.getElementById('slot-2-lbl').textContent = 'Audio';
              s2.querySelector('input').setAttribute('accept', 'audio/*,video/*');
              if (lBox1) lBox1.style.display = 'flex';
              if (lBox2) lBox2.style.display = 'flex';
              if (lTitle1) lTitle1.textContent = 'Add driving audio or voice track';
              if (lSub1) lSub1.textContent = 'Click to pick Audio (.mp3 / .wav)';
              if (lTitle2) lTitle2.textContent = 'Add character portrait';
              if (lSub2) lSub2.textContent = 'Click to pick Reference Image';
            } else if (detected.hasLoadVideo) {
              s2.style.display = 'flex';
              document.getElementById('slot-2-lbl').textContent = 'Video';
              s2.querySelector('input').setAttribute('accept', 'video/*,image/*');
              if (lBox1) lBox1.style.display = 'flex';
              if (lBox2) lBox2.style.display = detected.loadImageCount > 0 ? 'flex' : 'none';
              if (lTitle1) lTitle1.textContent = 'Add a reference video to extract motion';
              if (lSub1) lSub1.textContent = 'Click to pick from Library or Upload (4–15s)';
              if (lTitle2) lTitle2.textContent = 'Add your characters, products, or clothes';
              if (lSub2) lSub2.textContent = 'Click to pick from Saved Folders, Creations, or Upload';
            } else if (detected.loadImageCount >= 2) {
              s2.style.display = 'flex';
              document.getElementById('slot-2-lbl').textContent = 'Img 2';
              s2.querySelector('input').setAttribute('accept', 'image/*');
              if (lBox1) lBox1.style.display = 'flex';
              if (lBox2) lBox2.style.display = 'flex';
              if (lTitle1) lTitle1.textContent = '1. Add opening frame (First Image)';
              if (lSub1) lSub1.textContent = 'Click to pick First Frame Image';
              if (lTitle2) lTitle2.textContent = '2. Add closing frame (Second Image)';
              if (lSub2) lSub2.textContent = 'Click to pick Second Frame Image';
            } else {
              s2.style.display = 'none';
              if (lBox1) lBox1.style.display = 'flex';
              if (lBox2) lBox2.style.display = 'none';
              if (lTitle1) lTitle1.textContent = 'Add starting keyframe image';
              if (lSub1) lSub1.textContent = 'Click to pick from Library, Creations, or Upload';
            }
          }

          const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
          fetch('/shinjutsu/api/template/inspect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workflow: wfJson, mode: targetMode, comfy_url: comfyUrl })
          }).catch(() => {});

          const tplModels = extractModelsFromWorkflowJson(wfJson);
          const missing = registerTemplateModelsIntoMenu(tplModels, targetMode, tplTitle);

          if (tplModels.length > 0) {
            const primaryMod = tplModels.find(m => m.directory === 'diffusion_models' || m.directory === 'checkpoints') || tplModels[0];
            const firstBase = primaryMod.name.split('/').pop();
            const matchMod = cachedModels.find(m => m.name.split('/').pop() === firstBase);
            if (matchMod) {
              const sel = document.getElementById('model-picker');
              if (Array.from(sel.options).some(o => o.value === matchMod.id)) {
                sel.value = matchMod.id;
                onModelSelectChange();
              }
            }
          }

          updateRatioAndDurationChips();

          if (missing.length > 0) {
            pendingTemplateMissingModels = missing;
            activeSetupBundleIds = tplModels.map(tm => {
              const baseName = tm.name.split('/').pop();
              const found = cachedModels.find(cm => cm.name.split('/').pop() === baseName);
              return found ? found.id : tm.name;
            });
            activeSetupBundleTitle = tplTitle;
            openSettingsModal('models');
            renderActiveSetupBanner();
            setTimeout(scrollSettingsModalToTop, 20);
          } else {
            document.getElementById('tpl-install-banner').style.display = 'none';
          }
        } else {
          setMode(targetMode, true);
          if (tplDesc) {
            document.getElementById('prompt-input').value = tplDesc;
            syncPromptFromBottom(tplDesc);
          }
          loadDemoMedia('image', `${COMFY_TPL_CDN}/${tplName}-1.webp`, tplTitle);
        }
      } catch (e) {
        if (reqId === activeTemplateRequestId) {
          setMode(targetMode, true);
          loadDemoMedia('image', `${COMFY_TPL_CDN}/${tplName}-1.webp`, tplTitle);
        }
      }
    }

    async function installAllMissingForActiveTemplate() {
      if (!pendingTemplateMissingModels.length) return;
      showToast(`Started downloading ${pendingTemplateMissingModels.length} model(s)...`);
      try {
        await fetch('/shinjutsu/api/models/download-batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode: currentMode,
            models: pendingTemplateMissingModels.map(m => ({
              id: m.id,
              name: m.name,
              directory: m.folder,
              url: m.url
            }))
          })
        });
      } catch (e) {}

      await refreshComfySync();
      renderActiveSetupBanner();
      renderModelsList();
      if (!pollTimer) pollTimer = setInterval(refreshComfySync, 2000);
    }

    function populateModelDropdown() {
      const cfg = MODE_CONFIG[currentMode];
      const sel = document.getElementById('model-picker');
      const prevVal = sel.value;
      sel.innerHTML = '';

      cfg.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.label;
        sel.appendChild(opt);
      });

      if (currentMode !== 'shinjutsu' && currentMode !== 'audio') {
        cachedModels.filter(m => m.category === 'dynamic_comfy').forEach(dm => {
          const opt = document.createElement('option');
          opt.value = dm.id;
          opt.textContent = dm.name.split('/').pop().replace('.safetensors', '');
          sel.appendChild(opt);
        });
      }

      if (prevVal && Array.from(sel.options).some(o => o.value === prevVal)) {
        sel.value = prevVal;
      } else if (currentMode === 'shinjutsu') {
        sel.value = 'shinjutsu_svd_33mb';
      }
    }

    function onModelSelectChange() {
      const modelId = document.getElementById('model-picker').value || '';
      const fam = detectModelFamily(modelId);
      const spec = MODEL_FAMILY_SPECS[fam] || MODEL_FAMILY_SPECS.krea2;
      if (!spec.ratios[currentRatio]) {
        currentRatio = spec.defaultRatio || '9:16';
      }
      // If an external workflow is active, update its primary model loader to match the selected model!
      const selMod = cachedModels.find(m => m.id === modelId);
      if (activeExternalWorkflow && selMod && selMod.name) {
        updateModelInWorkflowObj(activeExternalWorkflow, selMod.name);
      }
      updateRatioAndDurationChips();
    }

    function updateModelInWorkflowObj(wf, modelFileName) {
      if (!wf || typeof wf !== 'object') return;
      function patchNodes(arr) {
        if (!Array.isArray(arr)) return;
        arr.forEach(n => {
          if ((n.type === 'UNETLoader' || n.type === 'CheckpointLoaderSimple') && Array.isArray(n.widgets_values) && n.widgets_values.length) {
            n.widgets_values[0] = modelFileName;
          }
        });
      }
      if (Array.isArray(wf.nodes)) {
        patchNodes(wf.nodes);
        if (wf.definitions && Array.isArray(wf.definitions.subgraphs)) {
          wf.definitions.subgraphs.forEach(sg => patchNodes(sg.nodes));
        }
      } else {
        Object.keys(wf).forEach(k => {
          const n = wf[k];
          if (n && n.inputs) {
            if (n.class_type === 'UNETLoader' && 'unet_name' in n.inputs) n.inputs.unet_name = modelFileName;
            if (n.class_type === 'CheckpointLoaderSimple' && 'ckpt_name' in n.inputs) n.inputs.ckpt_name = modelFileName;
          }
        });
      }
    }

    function pickCamera(el, moveName) {
      document.querySelectorAll('.preset-pill').forEach(p => p.classList.remove('active'));
      el.classList.add('active');
      document.getElementById('prompt-input').value = `[CAMERA: ${moveName}] Dynamic cinematic camera movement around the subject with natural lighting.`;
    }

    function cycleRatio(el) {
      customWidthOverride = null;
      customHeightOverride = null;
      const info = getActiveDimensionsAndFrames();
      const ratios = Object.keys(info.spec.ratios);
      const next = ratios[(ratios.indexOf(currentRatio) + 1) % ratios.length];
      currentRatio = next;
      updateRatioAndDurationChips();
      const updated = getActiveDimensionsAndFrames();
      showToast(`${currentRatio} (${updated.width}×${updated.height})`);
    }

    function cycleDuration(el) {
      customFramesOverride = null;
      const info = getActiveDimensionsAndFrames();
      const durs = info.spec.durations || [13.0, 8.0, 5.0];
      const curIdx = durs.findIndex(d => Math.abs(d - currentDurationSec) < 0.5);
      currentDurationSec = durs[(curIdx + 1) % durs.length];
      updateRatioAndDurationChips();
      const updated = getActiveDimensionsAndFrames();
      showToast(`${Math.round(updated.frames / 24)}s (${updated.frames} frames)`);
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      clearTimeout(window._toastTimer);
      window._toastTimer = setTimeout(() => { t.style.display = 'none'; }, 2800);
    }

    const WIDGET_NAMES_BY_NODE = {
      UNETLoader: ['unet_name', 'weight_dtype'],
      CheckpointLoaderSimple: ['ckpt_name'],
      CLIPLoader: ['clip_name', 'type', 'device'],
      DualCLIPLoader: ['clip_name1', 'clip_name2', 'type', 'device'],
      VAELoader: ['vae_name'],
      LoraLoader: ['lora_name', 'strength_model', 'strength_clip'],
      LoraLoaderModelOnly: ['lora_name', 'strength_model'],
      KSampler: ['seed', 'control_after_generate', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'],
      KSamplerSelect: ['sampler_name'],
      BasicScheduler: ['scheduler', 'steps', 'denoise'],
      RandomNoise: ['noise_seed', 'control_after_generate'],
      EmptySD3LatentImage: ['width', 'height', 'batch_size'],
      EmptyLatentImage: ['width', 'height', 'batch_size'],
      EmptyFlux2LatentImage: ['width', 'height', 'batch_size'],
      EmptyLTXVLatentVideo: ['width', 'height', 'length', 'batch_size'],
      LTXVImgToVideo: ['width', 'height', 'length', 'batch_size'],
      LTXVConditioning: ['frame_rate'],
      WanImageToVideo: ['width', 'height', 'length', 'batch_size'],
      MiniMaxH3ReferenceToVideo: ['prompt', 'width', 'height', 'length', 'ref_image_size'],
      MiniMaxH3FunControlNetApply: ['strength', 'start_percent', 'end_percent'],
      MiniMaxH3SigmaShift: ['shift_video', 'shift_audio'],
      FluxGuidance: ['guidance'],
      CFGGuider: ['cfg'],
      ModelSamplingSD3: ['shift'],
      ModelSamplingAuraFlow: ['shift'],
      CreateVideo: ['fps', 'crf']
    };

    function syncSimpleValuesIntoTweakingWorkflow() {
      if (!tweakingWorkflowObj) return;
      const stepsVal = parseInt(document.getElementById('tweak-quality').value, 10) || 20;
      const lockVal = parseInt(document.getElementById('tweak-lock').value, 10) / 100.0;
      const ratioVal = document.getElementById('tweak-ratio').value;
      const promptVal = document.getElementById('tweak-prompt').value;
      const info = getActiveDimensionsAndFrames();
      const tierRatios = (info.activeResTier && info.activeResTier.ratios) || info.spec.ratios;
      const wh = tierRatios[ratioVal] || info.spec.ratios[ratioVal] || [896, 1152];
      const w = (ratioVal === 'CUSTOM' && customWidthOverride) ? customWidthOverride : wh[0];
      const h = (ratioVal === 'CUSTOM' && customHeightOverride) ? customHeightOverride : wh[1];

      function patchNodeArr(arr) {
        if (!Array.isArray(arr)) return;
        arr.forEach(n => {
          const names = WIDGET_NAMES_BY_NODE[n.type] || [];
          if (!Array.isArray(n.widgets_values)) return;
          names.forEach((nm, idx) => {
            if (idx >= n.widgets_values.length) return;
            if (nm === 'steps') n.widgets_values[idx] = stepsVal;
            if (nm === 'strength' && n.type === 'MiniMaxH3FunControlNetApply') n.widgets_values[idx] = lockVal;
            if (nm === 'width') n.widgets_values[idx] = w;
            if (nm === 'height') n.widgets_values[idx] = h;
            if (nm === 'prompt' || (nm === 'text' && n.type === 'CLIPTextEncode')) n.widgets_values[idx] = promptVal;
          });
        });
      }

      if (Array.isArray(tweakingWorkflowObj.nodes)) {
        patchNodeArr(tweakingWorkflowObj.nodes);
        if (tweakingWorkflowObj.definitions && Array.isArray(tweakingWorkflowObj.definitions.subgraphs)) {
          tweakingWorkflowObj.definitions.subgraphs.forEach(sg => patchNodeArr(sg.nodes));
        }
      } else {
        Object.keys(tweakingWorkflowObj).forEach(k => {
          const n = tweakingWorkflowObj[k];
          if (!n || !n.inputs) return;
          if ('steps' in n.inputs && !Array.isArray(n.inputs.steps)) n.inputs.steps = stepsVal;
          if (n.class_type === 'MiniMaxH3FunControlNetApply' && 'strength' in n.inputs) n.inputs.strength = lockVal;
          if ('width' in n.inputs && !Array.isArray(n.inputs.width)) n.inputs.width = w;
          if ('height' in n.inputs && !Array.isArray(n.inputs.height)) n.inputs.height = h;
          if ('prompt' in n.inputs && !Array.isArray(n.inputs.prompt)) n.inputs.prompt = promptVal;
          if (n.class_type === 'CLIPTextEncode' && 'text' in n.inputs && !String(n.inputs.text).includes('blurry')) n.inputs.text = promptVal;
        });
      }
    }

    function setTweakerMode(m) {
      const isAdv = m === 'advanced';
      if (isAdv) {
        syncSimpleValuesIntoTweakingWorkflow();
      } else {
        applyAdvancedVariableEdits(true);
        if (customStepsOverride) {
          document.getElementById('tweak-steps-val').textContent = `${customStepsOverride} Steps`;
        }
        if (customWidthOverride && customHeightOverride) {
          const rSel = document.getElementById('tweak-ratio');
          let custOpt = rSel.querySelector('option[value="CUSTOM"]');
          if (!custOpt) {
            custOpt = document.createElement('option');
            custOpt.value = 'CUSTOM';
            rSel.prepend(custOpt);
          }
          custOpt.textContent = `Custom (${customWidthOverride}×${customHeightOverride}px)`;
          rSel.value = 'CUSTOM';
        }
      }
      document.getElementById('mode-btn-simple').classList.toggle('active', !isAdv);
      document.getElementById('mode-btn-adv').classList.toggle('active', isAdv);
      document.getElementById('tweak-simple-pane').style.display = isAdv ? 'none' : 'grid';
      document.getElementById('tweak-adv-pane').style.display = isAdv ? 'flex' : 'none';
      if (isAdv) renderAdvancedVariablesForm();
    }

    async function openTemplateTweaker(idx) {
      tweakingTemplateIndex = idx;
      const t = comfyOfficialTemplates[idx];
      if (!t) return;
      document.getElementById('tweak-title').textContent = `Customize: ${t.title}`;
      document.getElementById('tweak-prompt').value = t.description || 'Replace the person in <Video 1> with the character in <Picture 1>.';
      document.getElementById('tpl-tweaker').classList.add('open');

      tweakingWorkflowObj = null;
      if (customizedTemplatesMap[t.name] && customizedTemplatesMap[t.name].workflow) {
        tweakingWorkflowObj = JSON.parse(JSON.stringify(customizedTemplatesMap[t.name].workflow));
      } else {
        try {
          const r = await fetch(`${COMFY_TPL_CDN}/${t.name}.json`);
          if (r.ok) {
            tweakingWorkflowObj = await r.json();
          }
        } catch (e) {}
      }
      if (!tweakingWorkflowObj) {
        tweakingWorkflowObj = buildComfyWorkflow();
      }
      if (document.getElementById('mode-btn-adv').classList.contains('active')) {
        renderAdvancedVariablesForm();
      }
    }

    function renderAdvancedVariablesForm() {
      const pane = document.getElementById('tweak-adv-pane');
      const wf = tweakingWorkflowObj || buildComfyWorkflow();
      const rows = [];

      // Case 1: UI Graph Format (`nodes` + `definitions.subgraphs`)
      if (wf && Array.isArray(wf.nodes)) {
        const allNodes = [];
        wf.nodes.forEach((n, i) => allNodes.push({ scope: 'root', idx: i, node: n }));
        if (wf.definitions && Array.isArray(wf.definitions.subgraphs)) {
          wf.definitions.subgraphs.forEach((sg, sgi) => {
            (sg.nodes || []).forEach((sn, sni) => allNodes.push({ scope: `sg_${sgi}`, idx: sni, node: sn }));
          });
        }
        allNodes.forEach(item => {
          const n = item.node;
          if (!n || !Array.isArray(n.widgets_values) || !n.widgets_values.length) return;
          if (n.type === 'MarkdownNote' || n.type === 'Note') return;
          const names = WIDGET_NAMES_BY_NODE[n.type] || [];
          const fieldsHtml = n.widgets_values.map((val, wIdx) => {
            const pName = names[wIdx] || `param_${wIdx + 1}`;
            const isNum = typeof val === 'number';
            const safeVal = String(val ?? '').replace(/"/g, '&quot;');
            return `
              <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                <span style="font-size:11px; color:var(--muted);">${pName}</span>
                <input class="tweak-select adv-var-input" data-pname="${pName}" data-scope="${item.scope}" data-nidx="${item.idx}" data-widx="${wIdx}" data-dtype="${isNum ? 'number' : 'string'}" type="${isNum ? 'number' : 'text'}" step="any" value="${safeVal}" style="width:190px; padding:4px 8px; font-size:11.5px;" />
              </div>
            `;
          }).join('');
          rows.push(`
            <div class="tweak-field">
              <div class="tweak-label">
                <span>${n.title || n.type}</span>
                <span style="font-size:10px; color:var(--muted);">#${n.id} · ${n.type}</span>
              </div>
              <div style="display:flex; flex-direction:column; gap:6px; margin-top:4px;">${fieldsHtml}</div>
            </div>
          `);
        });
      } else if (wf && typeof wf === 'object') {
        // Case 2: Flat API Format (`{"1": {"class_type": "...", "inputs": {...}}}`)
        Object.keys(wf).forEach(nid => {
          const n = wf[nid];
          if (!n || !n.inputs || typeof n.inputs !== 'object') return;
          const scalarKeys = Object.keys(n.inputs).filter(k => !Array.isArray(n.inputs[k]));
          if (!scalarKeys.length) return;
          const fieldsHtml = scalarKeys.map(k => {
            const val = n.inputs[k];
            const isNum = typeof val === 'number';
            const safeVal = String(val ?? '').replace(/"/g, '&quot;');
            return `
              <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                <span style="font-size:11px; color:var(--muted);">${k}</span>
                <input class="tweak-select adv-api-input" data-nid="${nid}" data-key="${k}" data-dtype="${isNum ? 'number' : 'string'}" type="${isNum ? 'number' : 'text'}" step="any" value="${safeVal}" style="width:190px; padding:4px 8px; font-size:11.5px;" />
              </div>
            `;
          }).join('');
          rows.push(`
            <div class="tweak-field">
              <div class="tweak-label">
                <span>${n.class_type}</span>
                <span style="font-size:10px; color:var(--muted);">Node #${nid}</span>
              </div>
              <div style="display:flex; flex-direction:column; gap:6px; margin-top:4px;">${fieldsHtml}</div>
            </div>
          `);
        });
      }

      pane.innerHTML = rows.length
        ? `<div class="tweak-grid">${rows.join('')}</div>`
        : '<div style="font-size:12px; color:var(--muted);">No editable parameters found.</div>';
    }

    function applyAdvancedVariableEdits(forceRead) {
      if (!tweakingWorkflowObj) return;
      const isAdvActive = forceRead || document.getElementById('mode-btn-adv').classList.contains('active');
      let advW = null;
      let advH = null;
      let advLen = null;
      let advSteps = null;

      document.querySelectorAll('.adv-var-input').forEach(inp => {
        const scope = inp.getAttribute('data-scope');
        const pName = inp.getAttribute('data-pname') || '';
        const nIdx = parseInt(inp.getAttribute('data-nidx'), 10);
        const wIdx = parseInt(inp.getAttribute('data-widx'), 10);
        const dtype = inp.getAttribute('data-dtype');
        let parsedVal = dtype === 'number' ? parseFloat(inp.value) : inp.value;

        if (isAdvActive && dtype === 'number' && !isNaN(parsedVal)) {
          if (pName === 'width') {
            parsedVal = Math.max(256, Math.round(parsedVal / 32) * 32);
            inp.value = parsedVal;
            advW = parsedVal;
          } else if (pName === 'height') {
            parsedVal = Math.max(256, Math.round(parsedVal / 32) * 32);
            inp.value = parsedVal;
            advH = parsedVal;
          } else if (pName === 'length') {
            advLen = Math.max(1, Math.round(parsedVal));
          } else if (pName === 'steps') {
            advSteps = Math.max(1, Math.round(parsedVal));
          }
        }

        if (scope === 'root' && tweakingWorkflowObj.nodes && tweakingWorkflowObj.nodes[nIdx]) {
          tweakingWorkflowObj.nodes[nIdx].widgets_values[wIdx] = parsedVal;
        } else if (scope.startsWith('sg_')) {
          const sgi = parseInt(scope.split('_')[1], 10);
          const sg = tweakingWorkflowObj.definitions.subgraphs[sgi];
          if (sg && sg.nodes && sg.nodes[nIdx]) {
            sg.nodes[nIdx].widgets_values[wIdx] = parsedVal;
          }
        }
      });

      document.querySelectorAll('.adv-api-input').forEach(inp => {
        const nid = inp.getAttribute('data-nid');
        const key = inp.getAttribute('data-key');
        const dtype = inp.getAttribute('data-dtype');
        let parsedVal = dtype === 'number' ? parseFloat(inp.value) : inp.value;

        if (isAdvActive && dtype === 'number' && !isNaN(parsedVal)) {
          if (key === 'width') {
            parsedVal = Math.max(256, Math.round(parsedVal / 32) * 32);
            inp.value = parsedVal;
            advW = parsedVal;
          } else if (key === 'height') {
            parsedVal = Math.max(256, Math.round(parsedVal / 32) * 32);
            inp.value = parsedVal;
            advH = parsedVal;
          } else if (key === 'length') {
            advLen = Math.max(1, Math.round(parsedVal));
          } else if (key === 'steps') {
            advSteps = Math.max(1, Math.round(parsedVal));
          }
        }

        if (tweakingWorkflowObj[nid] && tweakingWorkflowObj[nid].inputs) {
          tweakingWorkflowObj[nid].inputs[key] = parsedVal;
        }
      });

      if (isAdvActive) {
        if (advW && advH) {
          customWidthOverride = advW;
          customHeightOverride = advH;
        }
        if (advLen) customFramesOverride = advLen;
        if (advSteps) customStepsOverride = advSteps;
      }
    }

    let activeSettingsTplCat = 'ALL';

    function detectTemplateStudioCategory(t) {
      if (t.studioMode) return t.studioMode;
      const c = (t.category || '').toLowerCase();
      const n = (t.name || '').toLowerCase();
      const ti = (t.title || '').toLowerCase();
      if (c.includes('audio') || n.includes('music') || n.includes('audio')) return 'audio';
      if (n.includes('minimax_h3_r2v') || n.includes('ref2v') || n.includes('animate') || ti.includes('replacement')) return 'shinjutsu';
      if (n.includes('ic_lora') || ti.includes('cinema') || ti.includes('camera')) return 'cinema';
      if (c.includes('video') || n.includes('video') || n.includes('i2v') || n.includes('t2v') || n.includes('fl2va')) return 'video';
      return 'images';
    }

    function filterSettingsTemplatesByCat(catKey) {
      activeSettingsTplCat = catKey || 'ALL';
      document.querySelectorAll('#settings-tpl-cat-pills .filter-pill').forEach(p => {
        p.classList.toggle('active', p.getAttribute('data-stcat') === activeSettingsTplCat);
      });
      renderSettingsTemplatesList();
    }

    function switchSettingsTab(tabName) {
      document.querySelectorAll('#settings-modal .modal-header .settings-tab').forEach(t => {
        t.classList.toggle('active', t.getAttribute('data-stab') === tabName);
      });
      document.querySelectorAll('.tab-pane').forEach(p => {
        p.classList.toggle('active', p.id === `stab-${tabName}`);
      });
      const mb = document.querySelector('#settings-modal .modal-body');
      if (mb) mb.scrollTop = 0;
      if (tabName === 'templates') renderSettingsTemplatesList();
      if (tabName === 'models') {
        renderActiveSetupBanner();
        renderModelsList();
      }
      if (tabName === 'system') loadStudioSystemConfig();
    }

    function openSettingsModal(defaultTab) {
      document.querySelectorAll('.dock-popover, .vert-ratio-popup').forEach(p => p.classList.remove('open'));
      document.getElementById('settings-modal').classList.add('open');
      switchSettingsTab(defaultTab || 'templates');
      renderActiveSetupBanner();
      renderModelsList();
      renderSettingsTemplatesList();
      loadStudioSystemConfig();
      refreshComfySync();
      if (!pollTimer) pollTimer = setInterval(refreshComfySync, 2000);
    }

    function renderSettingsTemplatesList() {
      const box = document.getElementById('settings-templates-list');
      if (!box) return;
      const q = ((document.getElementById('settings-tpl-search') && document.getElementById('settings-tpl-search').value) || '').toLowerCase().trim();
      const filtered = comfyOfficialTemplates
        .map((t, idx) => ({ t, idx, sCat: detectTemplateStudioCategory(t) }))
        .filter(({ t, sCat }) => {
          if (activeSettingsTplCat !== 'ALL' && sCat !== activeSettingsTplCat) return false;
          if (!q) return true;
          return (t.title || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q) || (t.category || '').toLowerCase().includes(q);
        })
        .slice(0, 40);

      const CAT_BADGE_LABELS = {
        shinjutsu: 'SHINJUTSU',
        video: 'Video',
        cinema: 'Cinema',
        images: 'Image / Soul',
        audio: 'Audio'
      };

      box.innerHTML = filtered.map(({ t, idx, sCat }) => {
        const thumbUrl = `${COMFY_TPL_CDN}/${t.name}-1.webp`;
        const safeTitle = (t.title || '').replace(/'/g, "\\'");
        const safeDesc = (t.description || '').replace(/'/g, "\\'");
        const isCustomized = Boolean(customizedTemplatesMap[t.name]);
        const rInfo = getTemplateReadiness(t);
        const actionBtn = rInfo.ready
          ? `<button class="act-btn primary" onclick="closeSettingsModal(); openComfyOfficialTemplate('${t.name}', '${safeTitle}', '${safeDesc}', '${t.category}')">Recreate</button>`
          : `<button class="act-btn" style="border-color:rgba(242,255,89,0.45); color:var(--accent);" onclick="openComfyOfficialTemplate('${t.name}', '${safeTitle}', '${safeDesc}', '${t.category}')">Setup</button>`;
        return `
          <div class="item-card">
            <img class="item-thumb" src="${thumbUrl}" loading="lazy" onerror="this.src='https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/video_minimax_h3_r2v-1.webp'" />
            <div class="item-info">
              <div class="item-title">
                <span>${t.title}</span>
                <span class="badge">${CAT_BADGE_LABELS[sCat] || t.category || 'Workflow'}</span>
                ${rInfo.ready ? '<span class="badge ready">Ready</span>' : '<span class="badge">Needs Setup</span>'}
                ${isCustomized ? '<span class="badge ready">Customized</span>' : ''}
              </div>
              <div class="item-sub">${t.description || 'Official open-weights workflow template'}</div>
            </div>
            <div style="display:flex; gap:6px; align-items:center;">
              <button class="act-btn" onclick="openTemplateTweaker(${idx})">Customize</button>
              ${actionBtn}
            </div>
          </div>
        `;
      }).join('');
    }

    function onChangeQualityPreset(val) {
      const s = parseInt(val, 10) || 20;
      document.getElementById('tweak-steps-val').textContent = `${s} Steps`;
      customStepsOverride = s;
      const mIdx = QUALITY_TIERS.findIndex(t => t.steps === s);
      if (mIdx >= 0) qualityTierIdx = mIdx;
      updateRatioAndDurationChips();
    }

    function saveAndApplyTweakedTemplate() {
      const isAdvActive = document.getElementById('mode-btn-adv').classList.contains('active');
      const ratioVal = document.getElementById('tweak-ratio').value;
      if (!isAdvActive) {
        if (ratioVal !== 'CUSTOM') {
          customWidthOverride = null;
          customHeightOverride = null;
          currentRatio = ratioVal;
        }
        customFramesOverride = null;
        customStepsOverride = parseInt(document.getElementById('tweak-quality').value, 10) || 20;
        customLockStrength = parseInt(document.getElementById('tweak-lock').value, 10) / 100.0;
        syncSimpleValuesIntoTweakingWorkflow();
      } else {
        applyAdvancedVariableEdits(true);
      }

      const t = comfyOfficialTemplates[tweakingTemplateIndex];
      const promptVal = document.getElementById('tweak-prompt').value;
      if (tweakingWorkflowObj) {
        activeExternalWorkflow = tweakingWorkflowObj;
      }
      if (t) {
        t.description = promptVal;
        customizedTemplatesMap[t.name] = {
          workflow: tweakingWorkflowObj,
          customW: customWidthOverride,
          customH: customHeightOverride,
          customFrames: customFramesOverride,
          customSteps: customStepsOverride,
          customLock: customLockStrength,
          prompt: promptVal
        };
        try {
          localStorage.setItem('shinjutsu_custom_presets', JSON.stringify(customizedTemplatesMap));
        } catch (e) {}
      }
      document.getElementById('prompt-input').value = promptVal;
      updateRatioAndDurationChips();
      closeSettingsModal();
      const geom = getActiveDimensionsAndFrames();
      showToast(`Saved (${geom.width}×${geom.height}px · ${geom.frames}f)`);
    }

    function importCustomTemplateJson(e) {
      const f = e.target.files[0];
      if (!f) return;
      const reader = new FileReader();
      reader.onload = async (ev) => {
        try {
          const wf = JSON.parse(ev.target.result);
          const cleanName = f.name.replace(/\.json$/i, '');
          const chosenCatSel = document.getElementById('import-tpl-category');
          const explicitCat = (chosenCatSel && chosenCatSel.value) || 'AUTO';
          const detected = detectTemplateModeAndSlots(wf, cleanName, '');
          const targetStudioMode = explicitCat === 'AUTO' ? detected.mode : explicitCat;
          const tplModels = extractModelsFromWorkflowJson(wf);

          customizedTemplatesMap[cleanName] = {
            workflow: wf,
            studioMode: targetStudioMode,
            prompt: 'Imported custom workflow preset'
          };
          try {
            localStorage.setItem('shinjutsu_custom_presets', JSON.stringify(customizedTemplatesMap));
          } catch (err) {}

          const newTplEntry = {
            name: cleanName,
            title: cleanName.replace(/[_-]/g, ' '),
            category: targetStudioMode.toUpperCase(),
            studioMode: targetStudioMode,
            requiredModels: tplModels,
            description: `Imported into ${targetStudioMode.toUpperCase()} studio`
          };
          comfyOfficialTemplates.unshift(newTplEntry);
          activeExternalWorkflow = wf;
          const missing = registerTemplateModelsIntoMenu(tplModels, targetStudioMode, newTplEntry.title);
          filterSettingsTemplatesByCat(targetStudioMode === 'soul' ? 'images' : targetStudioMode);

          if (missing.length > 0) {
            pendingTemplateMissingModels = missing;
            switchSettingsTab('models');
            const banner = document.getElementById('tpl-install-banner');
            document.getElementById('tpl-banner-title').textContent = `Imported "${newTplEntry.title}" needs ${missing.length} model(s)`;
            document.getElementById('tpl-banner-sub').textContent = missing.map(m => m.name.split('/').pop()).join(' · ');
            banner.style.display = 'flex';
            showToast(`Imported "${f.name}" into ${targetStudioMode.toUpperCase()} — setup ${missing.length} missing model(s)`);
          } else {
            openTemplateTweaker(0);
            showToast(`Imported "${f.name}" into ${targetStudioMode.toUpperCase()} — Ready to use!`);
          }
        } catch (err) {
          showToast('Invalid JSON file');
        }
      };
      reader.readAsText(f);
    }

    function closeSettingsModal() {
      document.getElementById('settings-modal').classList.remove('open');
      const anyDownloading = cachedModels.some(m => m.download_state && m.download_state.status === 'downloading');
      if (!anyDownloading && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    function loadDemoMedia(type, url, caption) {
      activeMediaType = type;
      activeMediaUrl = url;
      const sendBtn = document.getElementById('btn-send-shinjutsu');
      if (sendBtn) sendBtn.style.display = type === 'image' ? 'inline-flex' : 'none';
      document.getElementById('empty-state').style.display = 'none';
      const wrap = document.getElementById('media-wrap');
      wrap.classList.add('active');

      const stImg = document.getElementById('stage-img');
      const stVid = document.getElementById('stage-video');
      const stAud = document.getElementById('stage-audio');
      stImg.style.display = 'none';
      stVid.style.display = 'none';
      stAud.style.display = 'none';

      if (type === 'image') {
        stVid.pause();
        stAud.pause();
        stImg.src = url;
        stImg.style.display = 'block';
      } else if (type === 'audio') {
        stVid.pause();
        stAud.src = url;
        stAud.style.display = 'block';
        stAud.play().catch(() => {});
      } else {
        stAud.pause();
        stVid.src = url;
        stVid.style.display = 'block';
        stVid.play().catch(() => {});
      }

      // Also update Right Stage Player & Left Preset Card when in SHINJUTSU or Video mode
      const rPlayer = document.getElementById('right-active-player');
      const rBanner = document.getElementById('right-hero-banner');
      const rImg = document.getElementById('right-stage-img');
      const rVid = document.getElementById('right-stage-video');
      if (rPlayer && rBanner && rImg && rVid) {
        rBanner.style.display = 'none';
        rPlayer.style.display = 'flex';
        rImg.style.display = 'none';
        rVid.style.display = 'none';
        if (type === 'image') {
          rVid.pause();
          rImg.src = url;
          rImg.style.display = 'block';
          const lpImg = document.getElementById('left-preset-img');
          if (lpImg) lpImg.src = url;
        } else if (type === 'video') {
          rVid.src = url;
          rVid.style.display = 'block';
          rVid.play().catch(() => {});
        }
        if (caption) {
          const lpTitle = document.getElementById('left-preset-title');
          if (lpTitle) lpTitle.textContent = caption;
        }
      }

      if (caption) showToast(caption);

      // Push to session history strip if not already there
      if (url && !sessionHistory.some(h => h.url === url)) {
        sessionHistory.unshift({ type, url, caption: caption || currentMode });
        if (sessionHistory.length > 8) sessionHistory.pop();
        renderHistoryStrip();
      }
    }

    function renderHistoryStrip() {
      const strip = document.getElementById('history-strip');
      if (sessionHistory.length <= 1) {
        strip.style.display = 'none';
        return;
      }
      strip.style.display = 'flex';
      strip.innerHTML = sessionHistory.map((h, i) => `
        <div onclick="loadDemoMedia('${h.type}', '${h.url}')" style="width:36px; height:36px; border-radius:8px; overflow:hidden; border:1px solid ${h.url === activeMediaUrl ? 'var(--accent)' : 'var(--border-strong)'}; cursor:pointer; flex-shrink:0; background:#18181b;">
          ${h.type === 'image' ? `<img src="${h.url}" style="width:100%; height:100%; object-fit:cover;" />` : `<div style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; font-size:11px; color:var(--accent);">▶</div>`}
        </div>
      `).join('');
    }

    function resetStage() {
      const stVid = document.getElementById('stage-video');
      stVid.pause();
      document.getElementById('media-wrap').classList.remove('active');
      document.getElementById('empty-state').style.display = 'flex';
    }

    async function sendActiveImageToShinjutsu() {
      if (!activeMediaUrl || activeMediaType !== 'image') {
        showToast('Generate or select a character image first');
        return;
      }
      const srcUrl = activeMediaUrl;
      const cleanName = decodeURIComponent((srcUrl.split('filename=')[1] || srcUrl.split('/').pop() || 'character_id.png').split('&')[0]);
      uploadedSlot1Name = cleanName;
      hasUserSlot1Ref = true;
      setMode('shinjutsu');
      const charPrev = document.getElementById('deck-img-preview');
      const charClear = document.getElementById('left-dz-2-clear');
      if (charPrev) {
        charPrev.src = srcUrl;
        charPrev.style.display = 'block';
        charPrev.classList.add('show');
      }
      if (charClear) {
        charClear.style.display = 'inline-flex';
        charClear.classList.add('show');
      }
      const charThumb = document.getElementById('char-thumb');
      const s1Clear = document.getElementById('slot-1-clear');
      if (charThumb) {
        charThumb.src = srcUrl;
        charThumb.style.display = 'block';
        charThumb.classList.add('show');
      }
      if (s1Clear) {
        s1Clear.style.display = 'inline-flex';
        s1Clear.classList.add('show');
      }
      showToast('Character loaded into SHINJUTSU <Picture 1>');

      let resolveHandoff;
      window._slot1UploadPromise = new Promise(r => { resolveHandoff = r; });
      try {
        let dataUrl = srcUrl;
        if (!srcUrl.startsWith('data:')) {
          const resp = await fetch(srcUrl);
          const blob = await resp.blob();
          dataUrl = await new Promise((res, rej) => {
            const fr = new FileReader();
            fr.onload = () => res(fr.result);
            fr.onerror = rej;
            fr.readAsDataURL(blob);
          });
        }
        const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
        const safeFileName = (cleanName.endsWith('.png') || cleanName.endsWith('.webp')) ? cleanName : (cleanName + '.png');
        const upRes = await fetch('/shinjutsu/api/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_data: dataUrl,
            filename: safeFileName,
            kind: 'image',
            folder: 'characters',
            mode: 'shinjutsu',
            comfy_url: comfyUrl
          })
        });
        const out = await upRes.json();
        if (out && out.ok) {
          if (out.comfy_filename) uploadedSlot1Name = out.comfy_filename;
          if (out.cleaned_url) {
            if (charPrev) charPrev.src = out.cleaned_url;
            if (charThumb) charThumb.src = out.cleaned_url;
          }
        }
      } catch (e) {
      } finally {
        if (resolveHandoff) resolveHandoff();
        window._slot1UploadPromise = null;
      }
    }

    function downloadActiveMedia() {
      if (!activeMediaUrl) {
        showToast('No media to download yet');
        return;
      }
      const a = document.createElement('a');
      a.href = activeMediaUrl;
      const ext = activeMediaType === 'video' ? '.mp4' : (activeMediaType === 'audio' ? '.mp3' : '.png');
      const cleanPart = (activeMediaUrl.split('filename=')[1] || activeMediaUrl.split('/').pop() || ('shinjutsu_output' + ext)).split('&')[0];
      a.download = decodeURIComponent(cleanPart);
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }

    function handoffToMode(targetMode) {
      if (activeMediaUrl && activeMediaType === 'image') {
        hasUserSlot1Ref = true;
        const th = document.getElementById('char-thumb');
        th.src = activeMediaUrl;
        th.style.display = 'block';
        document.getElementById('slot-1-clear').style.display = 'inline-flex';
        const deckImg = document.getElementById('deck-img-preview');
        const dz2Clr = document.getElementById('left-dz-2-clear');
        if (deckImg) { deckImg.src = activeMediaUrl; deckImg.style.display = 'block'; }
        if (dz2Clr) dz2Clr.style.display = 'inline-flex';
        const urlParts = activeMediaUrl.split('?')[0].split('/');
        const lastPart = urlParts[urlParts.length - 1];
        if (lastPart && !activeMediaUrl.startsWith('data:')) {
          uploadedSlot1Name = lastPart;
        }
      }
      setMode(targetMode);
    }

    function clearSlot(slotNum, ev) {
      if (ev) ev.stopPropagation();
      if (slotNum === 1) {
        hasUserSlot1Ref = false;
        document.getElementById('char-thumb').style.display = 'none';
        document.getElementById('char-thumb').src = '';
        document.getElementById('slot-1-clear').style.display = 'none';
        document.getElementById('slot-1-input').value = '';
        const lIn2 = document.getElementById('left-dz-2-input');
        if (lIn2) lIn2.value = '';
        const deckImg = document.getElementById('deck-img-preview');
        const dz2Clr = document.getElementById('left-dz-2-clear');
        if (deckImg) { deckImg.style.display = 'none'; deckImg.src = ''; }
        if (dz2Clr) dz2Clr.style.display = 'none';
        const refCnt = document.getElementById('dir-ref-count');
        if (refCnt) refCnt.textContent = '0 / 9';
        uploadedSlot1Name = '';
      } else {
        document.getElementById('vid-thumb').style.display = 'none';
        document.getElementById('vid-thumb').src = '';
        document.getElementById('slot-2-clear').style.display = 'none';
        document.getElementById('slot-2-input').value = '';
        const lIn1 = document.getElementById('left-dz-1-input');
        if (lIn1) lIn1.value = '';
        const deckVid = document.getElementById('deck-vid-preview');
        const deckVidImg = document.getElementById('deck-vid-img-preview');
        const dz1Clr = document.getElementById('left-dz-1-clear');
        if (deckVid) { deckVid.pause(); deckVid.style.display = 'none'; deckVid.src = ''; }
        if (deckVidImg) { deckVidImg.style.display = 'none'; deckVidImg.src = ''; }
        if (dz1Clr) dz1Clr.style.display = 'none';
        uploadedSlot2Name = '';
        uploadedDepthName = '';
      }
    }

    /* Silent automatic background preparation & real ComfyUI upload under the hood */
    function onPickImage(e) {
      const f = e.target.files[0];
      if (!f) return;
      hasUserSlot1Ref = true;
      uploadedSlot1Name = f.name;
      closeAssetLibraryModal();
      const targetFolder = (activeAssetFolder && activeAssetFolder !== 'ALL') ? activeAssetFolder : 'characters';
      document.getElementById('slot-1-clear').style.display = 'inline-flex';
      const dz2Clr = document.getElementById('left-dz-2-clear');
      if (dz2Clr) dz2Clr.style.display = 'inline-flex';
      const refCnt = document.getElementById('dir-ref-count');
      if (refCnt) refCnt.textContent = currentMode === 'soul' ? 'Locked ✓' : '1 / 9';
      let resolveUpload;
      window._slot1UploadPromise = new Promise(r => { resolveUpload = r; });
      const reader = new FileReader();
      reader.onload = async (ev) => {
        try {
          const dataUrl = ev.target.result;
          const th = document.getElementById('char-thumb');
          th.src = dataUrl;
          th.style.display = 'block';
          const deckImg = document.getElementById('deck-img-preview');
          if (deckImg) { deckImg.src = dataUrl; deckImg.style.display = 'block'; }
          if (currentMode === 'video') {
            const deckVidImg = document.getElementById('deck-vid-img-preview');
            const dz1Clr = document.getElementById('left-dz-1-clear');
            if (deckVidImg) { deckVidImg.src = dataUrl; deckVidImg.style.display = 'block'; }
            if (dz1Clr) dz1Clr.style.display = 'inline-flex';
          }
          if (currentMode !== 'shinjutsu' && currentMode !== 'video') {
            loadDemoMedia('image', dataUrl);
          }

          const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
          try {
            const res = await fetch('/shinjutsu/api/upload', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ file_data: dataUrl, filename: f.name, kind: 'image', folder: targetFolder, mode: currentMode, comfy_url: comfyUrl })
            });
            const out = await res.json();
            if (out.ok) {
              if (out.comfy_filename) uploadedSlot1Name = out.comfy_filename;
              if (out.cleaned_url) {
                th.src = out.cleaned_url;
                if (deckImg) deckImg.src = out.cleaned_url;
                if (currentMode !== 'shinjutsu' && currentMode !== 'video') {
                  loadDemoMedia('image', out.cleaned_url);
                }
              }
              return;
            }
          } catch (err) {}

          // Direct fallback to ComfyUI /upload/image when running inside ComfyUI route
          try {
            const fd = new FormData();
            fd.append('image', f);
            fd.append('overwrite', 'true');
            const r = await fetch(`${comfyUrl}/upload/image`, { method: 'POST', body: fd });
            const d = await r.json();
            if (d.name) uploadedSlot1Name = d.name;
          } catch (e2) {}
        } finally {
          if (resolveUpload) resolveUpload();
          window._slot1UploadPromise = null;
        }
      };
      reader.readAsDataURL(f);
    }

    function onPickVideo(e) {
      const f = e.target.files[0];
      if (!f) return;
      // If user drops an image into "Add references" in Video mode, route it to Slot 1 (Keyframe Image) and preview it!
      if (f.type && f.type.startsWith('image/') && currentMode === 'video') {
        onPickImage(e);
        return;
      }
      uploadedSlot2Name = f.name;
      uploadedDepthName = f.name;
      closeAssetLibraryModal();
      const targetVidFolder = (activeAssetFolder && activeAssetFolder !== 'ALL') ? activeAssetFolder : 'motions';
      document.getElementById('slot-2-clear').style.display = 'inline-flex';
      const dz1Clr = document.getElementById('left-dz-1-clear');
      if (dz1Clr) dz1Clr.style.display = 'inline-flex';
      const deckVidImg = document.getElementById('deck-vid-img-preview');
      if (deckVidImg) deckVidImg.style.display = 'none';
      const url = URL.createObjectURL(f);
      probeAndSyncVideoDuration(url);
      const th = document.getElementById('vid-thumb');
      th.src = url;
      th.style.display = 'block';
      const deckVid = document.getElementById('deck-vid-preview');
      if (deckVid) {
        deckVid.src = url;
        deckVid.style.display = 'block';
        deckVid.onloadedmetadata = () => {
          if (deckVid.duration && isFinite(deckVid.duration) && deckVid.duration >= 1.5) {
            currentDurationSec = Math.min(15.08, Math.max(2.0, deckVid.duration));
            customFramesOverride = null;
            updateRatioAndDurationChips();
          }
        };
        deckVid.play().catch(() => {});
      }
      if (currentMode !== 'shinjutsu' && currentMode !== 'video') {
        loadDemoMedia('video', url);
      }

      const reader = new FileReader();
      reader.onload = async (ev) => {
        const dataUrl = ev.target.result;
        const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
        try {
          const res = await fetch('/shinjutsu/api/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_data: dataUrl, filename: f.name, kind: 'video', folder: targetVidFolder, mode: currentMode, comfy_url: comfyUrl })
          });
          const out = await res.json();
          if (out.ok) {
            if (out.comfy_filename) uploadedSlot2Name = out.comfy_filename;
            if (out.depth_filename) uploadedDepthName = out.depth_filename;
            if (out.duration_sec && isFinite(out.duration_sec) && out.duration_sec >= 1.0) {
              currentDurationSec = Math.min(15.08, Math.max(2.0, Number(out.duration_sec)));
              customFramesOverride = null;
              updateRatioAndDurationChips();
            }
            return;
          }
        } catch (err) {}

        try {
          const fd = new FormData();
          fd.append('image', f);
          fd.append('overwrite', 'true');
          const r = await fetch(`${comfyUrl}/upload/image`, { method: 'POST', body: fd });
          const d = await r.json();
          if (d.name) {
            uploadedSlot2Name = d.name;
            uploadedDepthName = d.name;
          }
        } catch (e2) {}
      };
      reader.readAsDataURL(f);
    }

    function triggerExtraRefUpload(role) {
      if (extraShinjutsuRefs.length >= 8) {
        showToast('Maximum 9 reference images (<Picture 1> to <Picture 9>) reached');
        return;
      }
      pendingExtraRefRole = role || 'outfit';
      const inp = document.getElementById('extra-ref-input');
      if (inp) inp.click();
    }

    function removeExtraRefSlot(idx) {
      extraShinjutsuRefs.splice(idx, 1);
      renderExtraRefsStrip();
    }

    function renderExtraRefsStrip() {
      const box = document.getElementById('extra-refs-list');
      const cntEl = document.getElementById('left-ref-counter');
      const totalImgs = 1 + extraShinjutsuRefs.length;
      if (cntEl) cntEl.textContent = `${totalImgs} / 9 Images`;
      const dirCnt = document.getElementById('dir-ref-count');
      if (dirCnt) dirCnt.textContent = `${totalImgs} / 9`;
      if (!box) return;
      renderDynamicPromptTagPills();
      if (!extraShinjutsuRefs.length) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
      }
      const ROLE_META = {
        outfit: { badge: 'Outfit (Auto White-BG)', col: '#22c55e' },
        scene: { badge: 'Scene (Raw 3D Angle)', col: '#38bdf8' },
        crew: { badge: 'Crew (Auto White-BG)', col: '#a855f7' }
      };
      box.style.display = 'flex';
      box.innerHTML = extraShinjutsuRefs.map((item, idx) => {
        const picNum = idx + 2;
        const meta = ROLE_META[item.role] || ROLE_META.outfit;
        return `
          <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; padding:4px 7px; border-radius:8px; background:#141419; border:1px solid var(--border);">
            <div style="display:flex; align-items:center; gap:7px; min-width:0;">
              <img src="${item.preview_url}" style="width:28px; height:28px; border-radius:5px; object-fit:cover; flex-shrink:0;" />
              <div style="min-width:0;">
                <div style="font-size:11px; font-weight:700; color:#fff;">&lt;Picture ${picNum}&gt; · <span style="color:${meta.col};">${meta.badge}</span></div>
                <div style="font-size:10px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.filename}</div>
              </div>
            </div>
            <button type="button" class="close-btn" style="font-size:11px; padding:2px 5px;" onclick="removeExtraRefSlot(${idx})" title="Remove">✕</button>
          </div>
        `;
      }).join('');
    }

    function onPickExtraRefImage(e) {
      const f = e.target.files[0];
      if (!f) return;
      if (extraShinjutsuRefs.length >= 8) {
        showToast('Maximum 9 reference images reached');
        return;
      }
      const role = pendingExtraRefRole || 'outfit';
      const targetFolder = role === 'scene' ? 'scenes' : (role === 'outfit' ? 'outfits' : 'characters');
      const reader = new FileReader();
      reader.onload = async (ev) => {
        const dataUrl = ev.target.result;
        const entry = {
          role,
          filename: f.name,
          comfy_filename: f.name,
          preview_url: dataUrl
        };
        extraShinjutsuRefs.push(entry);
        const picNum = extraShinjutsuRefs.length + 1;
        renderExtraRefsStrip();

        // Auto-append helpful reference tag hint into prompt if not already mentioned
        const curP = document.getElementById('left-prompt-input').value.trim();
        const tag = `<Picture ${picNum}>`;
        if (!curP.includes(tag)) {
          let clause = '';
          if (role === 'outfit') clause = ` wearing the outfit and accessories from ${tag}`;
          else if (role === 'scene') clause = ` inside the background environment of ${tag} (re-projected into 3D perspective)`;
          else if (role === 'crew') clause = ` while replacing the supporting dancers with the crew in ${tag}`;
          const nextP = curP.replace(/\.$/, '') + clause + '.';
          document.getElementById('left-prompt-input').value = nextP;
          syncPromptFromLeft(nextP);
        }

        const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
        try {
          const res = await fetch('/shinjutsu/api/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_data: dataUrl, filename: f.name, kind: 'image', role, folder: targetFolder, mode: 'shinjutsu', comfy_url: comfyUrl })
          });
          const out = await res.json();
          if (out.ok) {
            if (out.comfy_filename) entry.comfy_filename = out.comfy_filename;
            if (out.cleaned_url) entry.preview_url = out.cleaned_url;
            renderExtraRefsStrip();
          }
        } catch (err) {}
      };
      reader.readAsDataURL(f);
    }

    async function refreshComfySync() {
      const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
      try {
        const [stRes, modRes] = await Promise.all([
          fetch(`/shinjutsu/api/status?comfy_url=${encodeURIComponent(comfyUrl)}`),
          fetch(`/shinjutsu/api/models?comfy_url=${encodeURIComponent(comfyUrl)}`)
        ]);
        const st = await stRes.json();
        const modData = await modRes.json();
        if (modData.models && modData.models.length) cachedModels = modData.models;

        document.getElementById('mgr-gpu').textContent = st.comfy_online
          ? `Connected · ${st.gpu_name} (${st.vram_free_gb} GB Free VRAM)`
          : 'Local Mode (Start ComfyUI for live rendering)';
        document.getElementById('mgr-disk').textContent = `Free Disk Space: ${st.disk_free_gb} GB`;

        populateModelDropdown();
        updateRatioAndDurationChips();
        renderMotionLibraryGrid();
        renderComfyExploreGrid(activeExploreCategory);
        if (document.getElementById('settings-modal').classList.contains('open')) {
          renderActiveSetupBanner();
          renderModelsList();
          renderSettingsTemplatesList();
        }
      } catch (err) {}
    }

    function renderModelsList() {
      const box = document.getElementById('models-list');
      box.innerHTML = cachedModels.map(m => {
        const dl = m.download_state || {};
        const isDownloading = dl.status === 'downloading';
        const sizeLabel = m.actual_size_mb
          ? (m.actual_size_mb >= 1000 ? `${(m.actual_size_mb / 1024).toFixed(1)} GB` : `${m.actual_size_mb} MB`)
          : (m.size_mb >= 1000 ? `${(m.size_mb / 1024).toFixed(1)} GB` : `${m.size_mb} MB`);

        let actionHtml = '';
        if (isDownloading) {
          actionHtml = `<span class="badge">${dl.percent || 0}%</span>`;
        } else if (m.installed) {
          actionHtml = `
            <span class="badge ready">Installed (${sizeLabel})</span>
            ${m.source === 'local_disk' ? `<button class="act-btn danger" onclick="deleteModel('${m.id}')">Remove</button>` : ''}
          `;
        } else {
          actionHtml = `
            <span class="badge">${sizeLabel}</span>
            <button class="act-btn primary" onclick="downloadModel('${m.id}')">Setup</button>
          `;
        }

        return `
          <div class="item-card">
            <div class="item-info">
              <div class="item-title">${m.title}</div>
              <div class="item-sub">${m.description || m.name}</div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              ${actionHtml}
            </div>
          </div>
        `;
      }).join('');
    }

    async function downloadModel(modelId) {
      const item = cachedModels.find(m => m.id === modelId);
      showToast('Downloading model...');
      try {
        await fetch('/shinjutsu/api/models/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model_id: modelId,
            name: item ? item.name : '',
            folder: item ? item.folder : 'diffusion_models',
            url: item ? item.url : '',
            mode: currentMode
          })
        });
        refreshComfySync();
      } catch (e) {
        showToast('Could not start download — check server connection');
      }
    }

    async function deleteModel(modelId) {
      try {
        const res = await fetch('/shinjutsu/api/models/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_id: modelId })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(`Removed model (${data.freed_mb} MB freed)`);
          refreshComfySync();
        }
      } catch (e) {}
    }

    async function freeVramNow() {
      const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
      try {
        await fetch('/shinjutsu/api/free-vram', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ comfy_url: comfyUrl })
        });
      } catch (e) {}
      showToast('Cleared GPU memory (VRAM)');
    }

    async function interruptComfyRender() {
      const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
      try {
        await fetch('/shinjutsu/api/interrupt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ comfy_url: comfyUrl })
        });
      } catch (e) {}
      setGenButtonsLabel('Generate');
      showToast('Interrupted active ComfyUI render');
    }

    async function clearComfyQueue() {
      const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
      try {
        await fetch('/shinjutsu/api/clear-queue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ comfy_url: comfyUrl })
        });
      } catch (e) {}
      showToast('Cleared ComfyUI pending queue');
    }

    async function loadStudioSystemConfig() {
      try {
        const res = await fetch('/shinjutsu/api/config');
        const data = await res.json();
        if (data && data.ok && data.config) {
          const c = data.config;
          const hfEl = document.getElementById('cfg-hf-token');
          const civEl = document.getElementById('cfg-civitai-token');
          const keyEl = document.getElementById('cfg-comfy-key');
          const trEl = document.getElementById('cfg-transport');
          const mdEl = document.getElementById('cfg-models-dir');
          const owEl = document.getElementById('cfg-open-weights-strict');
          if (hfEl && c.hf_token) hfEl.value = c.hf_token;
          if (civEl && c.civitai_token) civEl.value = c.civitai_token;
          if (keyEl && c.comfy_api_key) keyEl.value = c.comfy_api_key;
          if (trEl && c.transport) trEl.value = c.transport;
          if (mdEl && c.models_dir !== undefined) mdEl.value = c.models_dir;
          if (owEl && c.open_weights_strict !== undefined) owEl.checked = Boolean(c.open_weights_strict);
        }
      } catch (e) {}
    }

    async function saveStudioSystemConfig() {
      const comfyUrl = (document.getElementById('comfy-url') && document.getElementById('comfy-url').value || 'http://127.0.0.1:8188').trim();
      const hfToken = (document.getElementById('cfg-hf-token') && document.getElementById('cfg-hf-token').value || '').trim();
      const civitaiToken = (document.getElementById('cfg-civitai-token') && document.getElementById('cfg-civitai-token').value || '').trim();
      const comfyKey = (document.getElementById('cfg-comfy-key') && document.getElementById('cfg-comfy-key').value || '').trim();
      const transport = (document.getElementById('cfg-transport') && document.getElementById('cfg-transport').value || 'auto').trim();
      const modelsDir = (document.getElementById('cfg-models-dir') && document.getElementById('cfg-models-dir').value || '').trim();
      const owStrict = document.getElementById('cfg-open-weights-strict') ? document.getElementById('cfg-open-weights-strict').checked : true;
      try {
        await fetch('/shinjutsu/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            comfy_url: comfyUrl,
            hf_token: hfToken,
            civitai_token: civitaiToken,
            comfy_api_key: comfyKey,
            transport,
            models_dir: modelsDir,
            open_weights_strict: owStrict
          })
        });
        await refreshComfySync();
        showToast('Saved tokens & studio configuration');
      } catch (e) {
        showToast('Could not save studio configuration');
      }
    }

    function buildComfyWorkflow() {
      const promptText = getEffectiveStudioPrompt();
      const soundOn = isStudioSoundEnabled();
      const modelId = document.getElementById('model-picker').value || '';
      const selMod = cachedModels.find(m => m.id === modelId);
      const selectedModelFile = selMod ? selMod.name : '';
      const geom = getActiveDimensionsAndFrames();
      const w = geom.width;
      const h = geom.height;
      const frames = geom.frames;
      const steps = customStepsOverride || geom.spec.steps || 20;

      if (activeExternalWorkflow) {
        const wfCopy = JSON.parse(JSON.stringify(activeExternalWorkflow));
        if (selectedModelFile) updateModelInWorkflowObj(wfCopy, selectedModelFile);
        return wfCopy;
      }

      if (currentMode === 'audio') {
        // Flattened from the official ComfyUI template `audio_minimax_music_3` (open weights):
        // text encode -> (positive, zero-out negative, duration) -> KSampler -> VAEDecodeAudio -> SaveAudioAdvanced (mp3)
        const secs = Math.max(5, Math.round(currentDurationSec));
        const musicSeed = Math.floor(Math.random() * 1e15);
        const musicUnet = (selectedModelFile && /music_?3/i.test(selectedModelFile)) ? selectedModelFile : "minimax_music3_dit_fp16.safetensors";
        return {
          "1": { "class_type": "UNETLoader", "inputs": { "unet_name": musicUnet, "weight_dtype": "default" } },
          "2": { "class_type": "CLIPLoader", "inputs": { "clip_name": "minimax_music3_text_encoder_pruned_int8_convrot.safetensors", "type": "minimax", "device": "default" } },
          "3": { "class_type": "VAELoader", "inputs": { "vae_name": "minimax_music3_dav.safetensors" } },
          "4": { "class_type": "MiniMaxMusic3TextEncode", "inputs": { "clip": ["2", 0], "caption": promptText, "lyrics": "", "seed": musicSeed, "max_duration": secs, "cfg_scale": 1.7, "top_k": 50 } },
          "5": { "class_type": "ConditioningZeroOut", "inputs": { "conditioning": ["4", 0] } },
          "6": { "class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": { "seconds": ["4", 1], "batch_size": 1 } },
          "7": { "class_type": "KSampler", "inputs": { "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "seed": musicSeed, "steps": customStepsOverride || 30, "cfg": 1.7, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0 } },
          "8": { "class_type": "VAEDecodeAudio", "inputs": { "samples": ["7", 0], "vae": ["3", 0] } },
          "9": { "class_type": "SaveAudioAdvanced", "inputs": { "audio": ["8", 0], "filename_prefix": "SHINJUTSU_Studio/Audio", "format": "mp3", "format.quality": "V0" } }
        };
      }
      // FLUX 3 Image Klein (open weights) — flattened from the official ComfyUI templates
      const isKlein = (currentMode === 'images' || currentMode === 'soul' || currentMode === 'cinema') && (modelId.startsWith('flux3') || modelId.startsWith('flux2_klein') || /flux3|flux-2-klein|klein/i.test(selectedModelFile));
      if (isKlein) {
        const isFlux2Klein4B = modelId.startsWith('flux2_klein') || /flux-2-klein/i.test(selectedModelFile);
        const kleinUnet = isFlux2Klein4B
          ? "flux-2-klein-4b-fp8.safetensors"
          : (/flux3|klein/i.test(selectedModelFile) ? selectedModelFile : "flux3-image-klein-int8-convrot.safetensors");
        const kleinClip = isFlux2Klein4B ? "qwen_3_4b_fp8_mixed.safetensors" : "qwen3vl_4b_int8_convrot.safetensors";
        const kleinClipType = isFlux2Klein4B ? "flux2" : "flux3";
        const kleinDefaultSteps = isFlux2Klein4B ? 8 : 16;
        const kleinSeed = Math.floor(Math.random() * 1e15);
        const g = {
          "1": { "class_type": "UNETLoader", "inputs": { "unet_name": kleinUnet, "weight_dtype": "default" } },
          "2": { "class_type": "CLIPLoader", "inputs": { "clip_name": kleinClip, "type": kleinClipType, "device": "default" } },
          "3": { "class_type": "VAELoader", "inputs": { "vae_name": "flux2-vae.safetensors" } },
          "4": { "class_type": "CLIPTextEncode", "inputs": { "clip": ["2", 0], "text": promptText } },
          "5": { "class_type": "CLIPTextEncode", "inputs": { "clip": ["2", 0], "text": "" } },
          "6": { "class_type": "EmptyFlux2LatentImage", "inputs": { "width": w, "height": h, "batch_size": currentBatchCount || 1 } },
          "8": { "class_type": "KSampler", "inputs": { "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "seed": kleinSeed, "steps": customStepsOverride || kleinDefaultSteps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0 } },
          "9": { "class_type": "VAEDecode", "inputs": { "samples": ["8", 0], "vae": ["3", 0] } },
          "10": { "class_type": "SaveImage", "inputs": { "images": ["9", 0], "filename_prefix": currentMode === 'soul' ? "SHINJUTSU_Studio/Character_ID_FLUX" : (currentMode === 'cinema' ? "SHINJUTSU_Studio/Cinema_Keyframe_FLUX" : "SHINJUTSU_Studio/Image_FLUX") } }
        };
        // Character ID, Image, or Cinema mode with a user-attached `+ Ref` image: wire ReferenceMultiLatent (<ref_image_0>)
        if ((currentMode === 'soul' || ((currentMode === 'images' || currentMode === 'cinema') && hasUserSlot1Ref)) && uploadedSlot1Name) {
          g["11"] = { "class_type": "LoadImage", "inputs": { "image": uploadedSlot1Name } };
          g["7"] = { "class_type": "ReferenceMultiLatent", "inputs": { "positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0], "resolution": "resize", "resolution.megapixels": 1.0, "images.image0": ["11", 0] } };
          g["8"].inputs.positive = ["7", 0];
          g["8"].inputs.negative = ["7", 1];
        }
        return g;
      }
      if (currentMode === 'images') {
        const unetFile = selectedModelFile || (modelId.includes('flux') ? "flux1-dev-fp8.safetensors" : "krea2_stock_turbo_fp8_scaled.safetensors");
        return {
          "1": { "class_type": "UNETLoader", "inputs": { "unet_name": unetFile, "weight_dtype": "fp8_e4m3fn" } },
          "2": { "class_type": "CLIPLoader", "inputs": { "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image" } },
          "3": { "class_type": "VAELoader", "inputs": { "vae_name": "texture_fix_vae_for_qwen_image_1_and_krea_2_bf16.safetensors" } },
          "4": { "class_type": "CLIPTextEncode", "inputs": { "clip": ["2", 0], "text": promptText } },
          "5": { "class_type": "ConditioningZeroOut", "inputs": { "conditioning": ["4", 0] } },
          "6": { "class_type": "EmptySD3LatentImage", "inputs": { "width": w, "height": h, "batch_size": currentBatchCount || 1 } },
          "8": { "class_type": "KSampler", "inputs": { "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "seed": 20272026, "steps": customStepsOverride || geom.spec.steps || 8, "cfg": 1.0, "sampler_name": geom.spec.sampler || "euler", "scheduler": geom.spec.scheduler || "simple", "denoise": 1.0 } },
          "9": { "class_type": "VAEDecode", "inputs": { "samples": ["8", 0], "vae": ["3", 0] } },
          "10": { "class_type": "SaveImage", "inputs": { "images": ["9", 0], "filename_prefix": "SHINJUTSU_Studio/Image" } }
        };
      }

      const buildLtx23OfficialGraph = (outPrefix) => {
        const ckptFile = (selectedModelFile && selectedModelFile.includes('ltx'))
          ? selectedModelFile
          : "ltx-2.3-22b-dev-fp8.safetensors";
        const halfW = Math.max(64, Math.floor((w / 2) / 32) * 32);
        const halfH = Math.max(64, Math.floor((h / 2) / 32) * 32);
        const hasRefImg = Boolean(hasUserSlot1Ref && uploadedSlot1Name && !String(uploadedSlot1Name).startsWith('source_motion'));
        const gLtx = {
          "1": { "class_type": "CheckpointLoaderSimple", "inputs": { "ckpt_name": ckptFile } },
          "2": { "class_type": "LoraLoaderModelOnly", "inputs": { "model": ["1", 0], "lora_name": "ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors", "strength_model": 0.5 } },
          "3": { "class_type": "LTXAVTextEncoderLoader", "inputs": { "text_encoder": "gemma_3_12B_it_fp4_mixed.safetensors", "ckpt_name": ckptFile, "device": "default" } },
          "4": { "class_type": "LTXVAudioVAELoader", "inputs": { "ckpt_name": ckptFile } },
          "5": { "class_type": "LatentUpscaleModelLoader", "inputs": { "model_name": "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" } },
          "8": { "class_type": "CLIPTextEncode", "inputs": { "clip": ["3", 0], "text": promptText } },
          "9": { "class_type": "CLIPTextEncode", "inputs": { "clip": ["3", 0], "text": "pc game, console game, video game, cartoon, childish, ugly, blurry, static, low quality" } },
          "10": { "class_type": "LTXVConditioning", "inputs": { "positive": ["8", 0], "negative": ["9", 0], "frame_rate": 25.0 } },
          "11": { "class_type": "EmptyLTXVLatentVideo", "inputs": { "width": halfW, "height": halfH, "length": frames, "batch_size": 1 } },
          "13": { "class_type": "LTXVEmptyLatentAudio", "inputs": { "frames_number": frames, "frame_rate": 25, "batch_size": 1, "audio_vae": ["4", 0] } },
          "14": { "class_type": "LTXVConcatAVLatent", "inputs": { "video_latent": ["11", 0], "audio_latent": ["13", 0] } },
          "15": { "class_type": "RandomNoise", "inputs": { "noise_seed": 20272026 } },
          "16": { "class_type": "KSamplerSelect", "inputs": { "sampler_name": "euler" } },
          "17": { "class_type": "ManualSigmas", "inputs": { "sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0" } },
          "18": { "class_type": "CFGGuider", "inputs": { "model": ["2", 0], "positive": ["10", 0], "negative": ["10", 1], "cfg": 1.0 } },
          "19": { "class_type": "SamplerCustomAdvanced", "inputs": { "noise": ["15", 0], "guider": ["18", 0], "sampler": ["16", 0], "sigmas": ["17", 0], "latent_image": ["14", 0] } },
          "20": { "class_type": "LTXVSeparateAVLatent", "inputs": { "av_latent": ["19", 0] } },
          "21": { "class_type": "LTXVCropGuides", "inputs": { "positive": ["10", 0], "negative": ["10", 1], "latent": ["20", 0] } },
          "22": { "class_type": "LTXVLatentUpsampler", "inputs": { "samples": ["20", 0], "upscale_model": ["5", 0], "vae": ["1", 2] } },
          "24": { "class_type": "LTXVConcatAVLatent", "inputs": { "video_latent": ["22", 0], "audio_latent": ["20", 1] } },
          "25": { "class_type": "RandomNoise", "inputs": { "noise_seed": 42 } },
          "26": { "class_type": "KSamplerSelect", "inputs": { "sampler_name": "euler" } },
          "27": { "class_type": "ManualSigmas", "inputs": { "sigmas": "0.85, 0.7250, 0.4219, 0.0" } },
          "28": { "class_type": "CFGGuider", "inputs": { "model": ["2", 0], "positive": ["21", 0], "negative": ["21", 1], "cfg": 1.0 } },
          "29": { "class_type": "SamplerCustomAdvanced", "inputs": { "noise": ["25", 0], "guider": ["28", 0], "sampler": ["26", 0], "sigmas": ["27", 0], "latent_image": ["24", 0] } },
          "30": { "class_type": "LTXVSeparateAVLatent", "inputs": { "av_latent": ["29", 0] } },
          "31": { "class_type": "VAEDecodeTiled", "inputs": { "samples": ["30", 0], "vae": ["1", 2], "tile_size": 768, "overlap": 64, "temporal_size": 4096, "temporal_overlap": 4 } },
          "32": { "class_type": "LTXVAudioVAEDecode", "inputs": { "samples": ["30", 1], "audio_vae": ["4", 0] } },
          "33": { "class_type": "CreateVideo", "inputs": soundOn ? { "images": ["31", 0], "audio": ["32", 0], "fps": 25 } : { "images": ["31", 0], "fps": 25 } },
          "34": { "class_type": "SaveVideo", "inputs": { "video": ["33", 0], "filename_prefix": outPrefix, "format": "mp4", "codec": "h264" } }
        };
        if (hasRefImg) {
          gLtx["6"] = { "class_type": "LoadImage", "inputs": { "image": uploadedSlot1Name } };
          gLtx["7"] = { "class_type": "LTXVPreprocess", "inputs": { "image": ["6", 0], "img_compression": 18 } };
          gLtx["12"] = { "class_type": "LTXVImgToVideoInplace", "inputs": { "vae": ["1", 2], "image": ["7", 0], "latent": ["11", 0], "strength": 0.7, "bypass": false } };
          gLtx["23"] = { "class_type": "LTXVImgToVideoInplace", "inputs": { "vae": ["1", 2], "image": ["7", 0], "latent": ["22", 0], "strength": 1.0, "bypass": false } };
          gLtx["14"].inputs.video_latent = ["12", 0];
          gLtx["24"].inputs.video_latent = ["23", 0];
        }
        return gLtx;
      };

      if (currentMode === 'video' || currentMode === 'cinema') {
        if (geom.family === 'minimax_h3') {
          const h3I2vUnet = (selectedModelFile && selectedModelFile.includes('fl2va'))
            ? selectedModelFile
            : "minimax_h3_fl2va_pruned_int8_convrot.safetensors";
          const gI2v = {
            "1": { "class_type": "UNETLoader", "inputs": { "unet_name": h3I2vUnet, "weight_dtype": "default" } },
            "2": { "class_type": "LoraLoaderModelOnly", "inputs": { "model": ["1", 0], "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "strength_model": 1.0 } },
            "3": { "class_type": "CLIPLoader", "inputs": { "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default" } },
            "4": { "class_type": "VAELoader", "inputs": { "vae_name": "minimax_h3_video_vae_int8_convrot.safetensors" } },
            "5": { "class_type": "VAELoader", "inputs": { "vae_name": "minimax_h3_audio_vae_fp32.safetensors" } },
            "6": { "class_type": "LoadImage", "inputs": { "image": uploadedSlot1Name } },
            "7": { "class_type": "MiniMaxH3ImageToVideo", "inputs": { "clip": ["3", 0], "vae": ["4", 0], "first_frame": ["6", 0], "prompt": promptText, "width": w, "height": h, "length": frames } },
            "8": { "class_type": "RandomNoise", "inputs": { "noise_seed": 20272026 } },
            "9": { "class_type": "KSamplerSelect", "inputs": { "sampler_name": "res_multistep" } },
            "10": { "class_type": "BasicScheduler", "inputs": { "model": ["2", 0], "scheduler": "simple", "steps": customStepsOverride || 8, "denoise": 1.0 } },
            "11": { "class_type": "BasicGuider", "inputs": { "model": ["2", 0], "conditioning": ["7", 0] } },
            "12": { "class_type": "SamplerCustomAdvanced", "inputs": { "noise": ["8", 0], "guider": ["11", 0], "sampler": ["9", 0], "sigmas": ["10", 0], "latent_image": ["7", 1] } },
            "13": { "class_type": "VAEDecode", "inputs": { "samples": ["12", 0], "vae": ["4", 0] } },
            "14": { "class_type": "VAEDecodeAudio", "inputs": { "samples": ["12", 0], "vae": ["5", 0] } },
            "15": { "class_type": "CreateVideo", "inputs": { "images": ["13", 0], "audio": ["14", 0], "fps": 24 } },
            "16": { "class_type": "SaveVideo", "inputs": { "video": ["15", 0], "filename_prefix": "SHINJUTSU_Studio/H3_Video", "format": "mp4", "codec": "h264" } }
          };
          if (!soundOn) {
            delete gI2v["14"];
            delete gI2v["15"].inputs.audio;
          }
          return gI2v;
        }
        if (geom.family === 'wan') {
          return {
            "1": { "class_type": "UNETLoader", "inputs": { "unet_name": selectedModelFile || "wan2.2_animate_14B_fp8_e4m3fn.safetensors", "weight_dtype": "fp8_e4m3fn" } },
            "2": { "class_type": "CLIPLoader", "inputs": { "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan" } },
            "3": { "class_type": "VAELoader", "inputs": { "vae_name": "wan_2.1_vae.safetensors" } },
            "4": { "class_type": "LoadImage", "inputs": { "image": uploadedSlot1Name } },
            "5": { "class_type": "CLIPTextEncode", "inputs": { "clip": ["2", 0], "text": promptText } },
            "6": { "class_type": "ConditioningZeroOut", "inputs": { "conditioning": ["5", 0] } },
            "7": { "class_type": "WanImageToVideo", "inputs": { "positive": ["5", 0], "negative": ["6", 0], "vae": ["3", 0], "start_image": ["4", 0], "width": w, "height": h, "length": frames, "batch_size": 1 } },
            "8": { "class_type": "KSampler", "inputs": { "model": ["1", 0], "positive": ["7", 0], "negative": ["7", 1], "latent_image": ["7", 2], "seed": 20272026, "steps": customStepsOverride || 20, "cfg": 6.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0 } },
            "9": { "class_type": "VAEDecode", "inputs": { "samples": ["8", 0], "vae": ["3", 0] } },
            "10": { "class_type": "CreateVideo", "inputs": { "images": ["9", 0], "fps": 24 } },
            "11": { "class_type": "SaveVideo", "inputs": { "video": ["10", 0], "filename_prefix": "SHINJUTSU_Studio/Wan22", "format": "mp4", "codec": "h264" } }
          };
        }
        return buildLtx23OfficialGraph("SHINJUTSU_Studio/Cinema_LTX23");
      }

      if (currentMode === 'soul') {
        const unetFile = selectedModelFile || "krea2_stock_turbo_fp8_scaled.safetensors";
        return {
          "1": { "class_type": "UNETLoader", "inputs": { "unet_name": unetFile, "weight_dtype": "fp8_e4m3fn" } },
          "2": { "class_type": "LoraLoaderModelOnly", "inputs": { "model": ["1", 0], "lora_name": "krea2_identity_edit_v2_r128.safetensors", "strength_model": 1.0 } },
          "3": { "class_type": "CLIPLoader", "inputs": { "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image" } },
          "4": { "class_type": "VAELoader", "inputs": { "vae_name": "texture_fix_vae_for_qwen_image_1_and_krea_2_bf16.safetensors" } },
          "5": { "class_type": "LoadImage", "inputs": { "image": uploadedSlot1Name } },
          "6": { "class_type": "EmptySD3LatentImage", "inputs": { "width": w, "height": h, "batch_size": currentBatchCount || 1 } },
          "7": { "class_type": "Krea2EditModelPatch", "inputs": { "model": ["2", 0], "ref_position": "beside (right of target)" } },
          "8": { "class_type": "Krea2EditGroundedEncode", "inputs": { "clip": ["3", 0], "vae": ["4", 0], "target_latent": ["6", 0], "ref_image_a": ["5", 0], "prompt": promptText, "fit_mode": "fit", "grounding_px": 1024, "ref_boost_a": (charIdIdx.light === 0 ? 3.2 : (charIdIdx.light === 1 ? 2.6 : 1.9)) } },
          "9": { "class_type": "ConditioningZeroOut", "inputs": { "conditioning": ["8", 0] } },
          "11": { "class_type": "KSampler", "inputs": { "model": ["7", 0], "positive": ["8", 0], "negative": ["9", 0], "latent_image": ["8", 1], "seed": 20272026, "steps": customStepsOverride || 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0 } },
          "12": { "class_type": "VAEDecode", "inputs": { "samples": ["11", 0], "vae": ["4", 0] } },
          "13": { "class_type": "SaveImage", "inputs": { "images": ["12", 0], "filename_prefix": "SHINJUTSU_Studio/Soul_ID" } }
        };
      }

      if (geom.family === 'wan') {
        return {
          "1": { "class_type": "UNETLoader", "inputs": { "unet_name": selectedModelFile || "wan2.2_animate_14B_fp8_e4m3fn.safetensors", "weight_dtype": "fp8_e4m3fn" } },
          "2": { "class_type": "CLIPLoader", "inputs": { "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan" } },
          "3": { "class_type": "VAELoader", "inputs": { "vae_name": "wan_2.1_vae.safetensors" } },
          "4": { "class_type": "LoadImage", "inputs": { "image": uploadedSlot1Name } },
          "5": { "class_type": "LoadVideo", "inputs": { "file": uploadedSlot2Name } },
          "6": { "class_type": "CLIPTextEncode", "inputs": { "clip": ["2", 0], "text": promptText } },
          "7": { "class_type": "WanAnimateToVideo", "inputs": { "positive": ["6", 0], "vae": ["3", 0], "reference_image": ["4", 0], "pose_video": ["5", 0], "width": w, "height": h, "length": frames, "batch_size": 1 } },
          "8": { "class_type": "KSampler", "inputs": { "model": ["1", 0], "positive": ["7", 0], "negative": ["7", 1], "latent_image": ["7", 2], "seed": 20272026, "steps": customStepsOverride || 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0 } },
          "9": { "class_type": "VAEDecode", "inputs": { "samples": ["8", 0], "vae": ["3", 0] } },
          "10": { "class_type": "CreateVideo", "inputs": { "images": ["9", 0], "fps": 24 } },
          "11": { "class_type": "SaveVideo", "inputs": { "video": ["10", 0], "filename_prefix": "SHINJUTSU_Studio/WanAnimate", "format": "mp4", "codec": "h264" } }
        };
      }

      if (geom.family === 'ltx') {
        return buildLtx23OfficialGraph("SHINJUTSU_Studio/LTX_Swap");
      }

      const is16gbTurbo = (modelId === 'shinjutsu_16gb_turbo' || (selectedModelFile && selectedModelFile.includes('w6a8')));
      const isProPod = (modelId === 'shinjutsu_pro_pod' || (selectedModelFile && selectedModelFile === 'minimax_h3_ref2va_int8_convrot.safetensors'));
      const h3Unet = is16gbTurbo
        ? "minimax_h3_ref2va_pruned_w6a8.safetensors"
        : (isProPod ? "minimax_h3_ref2va_int8_convrot.safetensors" : "minimax_h3_ref2va_pruned_int8_convrot.safetensors");
      const h3Clip = isProPod
        ? "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
        : "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors";
      const h3VideoVae = isProPod
        ? "minimax_h3_video_vae_fp16.safetensors"
        : "minimax_h3_video_vae_int8_convrot.safetensors";

      const gH3 = {
        "1": { "class_type": "UNETLoader", "inputs": { "unet_name": h3Unet, "weight_dtype": "default" } },
        "12": { "class_type": "MiniMaxH3SigmaShift", "inputs": { "model": ["1", 0], "shift_video": 12.0, "shift_audio": 3.0 } },
        "85": { "class_type": "ModelAttentionBackend", "inputs": { "model": ["12", 0], "attention": "comfy kitchen attention" } },
        "2": { "class_type": "CLIPLoader", "inputs": { "clip_name": h3Clip, "type": "minimax", "device": "default" } },
        "3": { "class_type": "VAELoader", "inputs": { "vae_name": h3VideoVae } },
        "4": { "class_type": "VAELoader", "inputs": { "vae_name": "minimax_h3_audio_vae_fp32.safetensors" } },
        "173": { "class_type": "ModelPatchLoader", "inputs": { "name": "shinjutsu_h3_control_patch_v1_flash.safetensors" } },
        "174": { "class_type": "LoadVideo", "inputs": { "file": uploadedDepthName } },
        "175": { "class_type": "GetVideoComponents", "inputs": { "video": ["174", 0] } },
        "172": {
          "class_type": "MiniMaxH3FunControlNetApply",
          "inputs": { "model": ["85", 0], "model_patch": ["173", 0], "vae": ["3", 0], "strength": customLockStrength || 0.68, "start_percent": 0.0, "end_percent": 0.50, "control_video": ["175", 0] }
        },
        "200": { "class_type": "LoadImage", "inputs": { "image": uploadedSlot1Name } },
        "201": { "class_type": "ImageScaleToMaxDimension", "inputs": { "image": ["200", 0], "upscale_method": "lanczos", "largest_size": 1024 } },
        "300": { "class_type": "LoadVideo", "inputs": { "file": uploadedSlot2Name } },
        "301": { "class_type": "GetVideoComponents", "inputs": { "video": ["300", 0] } },
        "106": {
          "class_type": "MiniMaxH3ReferenceToVideo",
          "inputs": {
            "clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0], "prompt": promptText,
            "width": w, "height": h, "length": frames, "ref_image_size": "match",
            "ref_images.ref_image_0": ["201", 0], "ref_videos.ref_video_0": ["301", 0], "ref_video_audios.ref_video_audio_0": ["301", 1]
          }
        },
        "108": { "class_type": "MiniMaxH3AddGuide", "inputs": { "positive": ["106", 0], "latent": ["106", 1], "audio_vae": ["4", 0], "audio": ["301", 1], "frame_idx": 0 } },
        "6": { "class_type": "RandomNoise", "inputs": { "noise_seed": 20272026 } },
        "9": { "class_type": "KSamplerSelect", "inputs": { "sampler_name": is16gbTurbo ? "res_multistep" : "er_sde" } },
        "48": { "class_type": "BasicScheduler", "inputs": { "model": ["172", 0], "scheduler": is16gbTurbo ? "simple" : "beta", "steps": is16gbTurbo ? (customStepsOverride || 8) : steps, "denoise": 1.0 } },
        "49": { "class_type": "BasicGuider", "inputs": { "model": ["172", 0], "conditioning": ["108", 0] } },
        "47": { "class_type": "SamplerCustomAdvanced", "inputs": { "noise": ["6", 0], "guider": ["49", 0], "sampler": ["9", 0], "sigmas": ["48", 0], "latent_image": ["106", 1] } },
        "45": { "class_type": "VAEDecode", "inputs": { "samples": ["47", 0], "vae": ["3", 0] } },
        "46": { "class_type": "VAEDecodeAudio", "inputs": { "samples": ["47", 0], "vae": ["4", 0] } },
        "80": { "class_type": "CreateVideo", "inputs": { "images": ["45", 0], "audio": ["46", 0], "fps": 24 } },
        "81": { "class_type": "SaveVideo", "inputs": { "video": ["80", 0], "filename_prefix": "SHINJUTSU_H3/SHINJUTSU_Studio", "format": "mp4", "codec": "h264" } }
      };
      if (is16gbTurbo) {
        gH3["500"] = {
          "class_type": "LoraLoaderModelOnly",
          "inputs": { "model": ["1", 0], "lora_name": "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors", "strength_model": 1.0 }
        };
        gH3["12"].inputs.model = ["500", 0];
      }
      const isMultiSubTab = document.getElementById('seg-btn-2') && document.getElementById('seg-btn-2').classList.contains('active');
      if (isMultiSubTab) {
        extraShinjutsuRefs.slice(0, 8).forEach((refItem, idxExtra) => {
          const refSlotIdx = idxExtra + 1;
          const loadNid = String(210 + refSlotIdx * 2);
          const scaleNid = String(211 + refSlotIdx * 2);
          gH3[loadNid] = { "class_type": "LoadImage", "inputs": { "image": refItem.comfy_filename || refItem.filename } };
          gH3[scaleNid] = { "class_type": "ImageScaleToMaxDimension", "inputs": { "image": [loadNid, 0], "upscale_method": "lanczos", "largest_size": 1024 } };
          gH3["106"].inputs[`ref_images.ref_image_${refSlotIdx}`] = [scaleNid, 0];
        });
      }
      if (!soundOn) {
        delete gH3["46"];
        delete gH3["80"].inputs.audio;
      }
      return gH3;
    }

    function setGenButtonsLabel(txt) {
      const b1 = document.getElementById('gen-btn-lbl');
      const b2 = document.getElementById('left-gen-btn-lbl');
      if (b1) b1.textContent = txt === 'Generate' ? 'GENERATE' : txt;
      if (b2) b2.textContent = txt;
    }

    function connectComfyWebSocket(comfyUrl, jobId, transport) {
      // Live % progress comes from ComfyUI's own WebSocket (direct transport only).
      // Job state is always decided by polling /shinjutsu/api/job-status, which works for both
      // the direct /prompt transport and the Comfy SDK (API v2 / Comfy Cloud) transport.
      if (transport !== 'sdk') {
        try {
          if (comfyWs) comfyWs.close();
          const wsProto = comfyUrl.startsWith('https') ? 'wss://' : 'ws://';
          const hostPart = comfyUrl.replace(/^https?:\/\//, '');
          comfyWs = new WebSocket(`${wsProto}${hostPart}/ws?clientId=${CLIENT_ID}`);
          comfyWs.onmessage = (ev) => {
            if (typeof ev.data !== 'string') return;
            try {
              const msg = JSON.parse(ev.data);
              if (msg.type === 'progress' && msg.data) {
                const pct = Math.round((msg.data.value / Math.max(1, msg.data.max)) * 100);
                setGenButtonsLabel(`Generating ${pct}%`);
              }
            } catch (e) {}
          };
        } catch (err) {}
      } else {
        setGenButtonsLabel('Rendering (Comfy API)...');
      }

      // Poll job state until output is ready, then auto-display on Center Stage
      let failures = 0;
      const checkTimer = setInterval(async () => {
        try {
          const qs = new URLSearchParams({ job_id: jobId, comfy_url: comfyUrl, transport: transport || '' });
          const r = await fetch(`/shinjutsu/api/job-status?${qs.toString()}`);
          const d = await r.json();
          failures = 0;
          if (d.status === 'error') {
            clearInterval(checkTimer);
            setGenButtonsLabel('Generate');
            showToast(d.error ? `Render failed: ${d.error}` : 'ComfyUI execution error — check model or VRAM');
            return;
          }
          if (d.status === 'completed' && d.view_url) {
            clearInterval(checkTimer);
            setGenButtonsLabel('Generate');
            loadDemoMedia(d.media_type || 'image', d.view_url, 'Completed');
          }
        } catch (e) {
          // Tolerate brief network hiccups; give up after ~20 s of consecutive failures
          if (++failures >= 10) {
            clearInterval(checkTimer);
            setGenButtonsLabel('Generate');
            showToast('Lost connection while waiting for the render');
          }
        }
      }, 2000);
    }

    async function queueToComfyUI() {
      if (window._slot1UploadPromise) {
        setGenButtonsLabel('Preparing ref...');
        try { await window._slot1UploadPromise; } catch (e) {}
      }
      const modelId = document.getElementById('model-picker').value || '';
      const selEl = document.getElementById('model-picker');
      const selLbl = (selEl && selEl.selectedOptions.length) ? selEl.selectedOptions[0].textContent : modelId;
      const bInfo = getModelBundleReadiness(modelId);
      if (!bInfo.ready && !activeExternalWorkflow) {
        openModelBundleSetup(modelId, selLbl);
        showToast(`Please setup ${bInfo.missing.length} required model file(s) first`);
        return;
      }
      const comfyUrl = document.getElementById('comfy-url').value.replace(/\/$/, '');
      const wf = buildComfyWorkflow();
      const promptText = getEffectiveStudioPrompt();
      const geom = getActiveDimensionsAndFrames();
      const selMod = cachedModels.find(m => m.id === modelId);
      setGenButtonsLabel('Checking workflow...');
      try {
        const res = await fetch('/shinjutsu/api/queue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            comfy_url: comfyUrl,
            mode: currentMode,
            workflow: wf,
            prompt: promptText,
            slot1_file: uploadedSlot1Name,
            slot2_file: uploadedSlot2Name,
            width: geom.width,
            height: geom.height,
            frames: geom.frames,
            fps: geom.fps,
            steps: customStepsOverride || geom.spec.steps || 20,
            control_strength: customLockStrength,
            selected_model_name: selMod ? selMod.name : '',
            client_id: CLIENT_ID
          })
        });
        const data = await res.json();
        const jobId = data.job_id || data.prompt_id;
        if (data.queued && jobId) {
          const warn = data.validation && data.validation.partner_nodes && data.validation.partner_nodes.length
            ? ' (note: uses partner/API nodes)' : '';
          showToast('Rendering in progress...' + warn);
          connectComfyWebSocket(comfyUrl, jobId, data.transport);
        } else if (data.ok === false) {
          // Pre-flight validation (/object_info) or ComfyUI rejected the graph: tell the user exactly why
          setGenButtonsLabel('Generate');
          showToast(data.error || 'Workflow check failed');
          if (data.validation) console.warn('[SHINJUTSU] Workflow validation report:', data.validation);
        } else {
          setGenButtonsLabel('Generate');
          showToast(data.message || 'Compiled & saved ready-to-run workflow');
        }
      } catch (err) {
        setGenButtonsLabel('Generate');
        downloadWorkflowJSON();
      }
    }
    function downloadWorkflowJSON() {
      if (document.getElementById('tpl-tweaker') && document.getElementById('tpl-tweaker').classList.contains('open')) {
        const isAdvActive = document.getElementById('mode-btn-adv').classList.contains('active');
        if (isAdvActive) applyAdvancedVariableEdits(true);
        else syncSimpleValuesIntoTweakingWorkflow();
        if (tweakingWorkflowObj) activeExternalWorkflow = tweakingWorkflowObj;
      }
      const wf = buildComfyWorkflow();
      const blob = new Blob([JSON.stringify(wf, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `shinjutsu_${currentMode}_workflow.json`;
      a.click();
    }

    // When the studio is served BY ComfyUI (custom-node mode: /shinjutsu on ComfyUI's own port), the browser
    // must talk to the same origin it loaded from — not 127.0.0.1 — so remote GPUs (RunPod/Vast proxies, LAN,
    // tunnels) get working progress (WebSocket), uploads and result previews. Standalone mode (port 7865) keeps
    // the configurable ComfyUI URL. The backend confirms with `embedded: true` in /shinjutsu/api/status.
    (function useSameOriginWhenEmbedded() {
      try {
        const inp = document.getElementById('comfy-url');
        const looksEmbedded = /^https?:$/.test(location.protocol) && location.pathname.startsWith('/shinjutsu') && location.port !== '7865';
        if (inp && looksEmbedded) inp.value = location.origin;
        fetch('/shinjutsu/api/status').then(r => r.json()).then(st => {
          if (!inp) return;
          if (st && st.embedded) inp.value = location.origin;
          else if (looksEmbedded && inp.value === location.origin) inp.value = 'http://127.0.0.1:8188';
        }).catch(() => {});
      } catch (e) {}
    })();
    populateModelDropdown();
    loadLiveComfyOfficialIndex();
    refreshComfySync();
