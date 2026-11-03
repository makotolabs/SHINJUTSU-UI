const COMFY_TPL_CDN = 'https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates';
    const CLIENT_ID = 'shinjutsu_' + Math.random().toString(36).slice(2, 10);
    let currentMode = 'shinjutsu';
    let currentRatio = '9:16';
    let currentDurationSec = 13.0;
    let activeMediaUrl = '';
    let activeMediaType = '';
    let activeExternalWorkflow = null;
    let activeTemplateSlug = '';
    let activeExploreCategory = 'ALL';
    let uploadedSlot1Name = 'character_reference_clean_white_bg.png';
    let uploadedSlot2Name = 'source_motion.mp4';
    let uploadedDepthName = 'source_motion_crisp_depth.mp4';
    let pendingTemplateMissingModels = [];
    let sessionHistory = [];
    let customizedTemplatesMap = {};
    try {
      customizedTemplatesMap = JSON.parse(localStorage.getItem('shinjutsu_custom_presets') || '{}');
    } catch (e) { customizedTemplatesMap = {}; }
    let pollTimer = null;
    let comfyWs = null;
    let tweakingTemplateIndex = 0;
    let customStepsOverride = null;
    let customLockStrength = 0.68;
    let customWidthOverride = null;
    let customHeightOverride = null;
    let customFramesOverride = null;
    let tweakingWorkflowObj = null;
    let activeTemplateRequestId = 0;
    let currentBatchCount = 1;
    const QUALITY_TIERS = [
      { label: 'High', steps: 20 },
      { label: 'Ultra', steps: 28 },
      { label: 'Fast', steps: 8 }
    ];
    let qualityTierIdx = 0;

    /* Per-Model Family Native Resolution Tiers:
       - Image models (`krea2`, `flux3`, `flux`, `qwen_image`, `z_image`):
           Tier 0 = `0.5K` (Fast Draft: 640×832 / 576×1024)
           Tier 1 = `1K`   (Native Standard 1MP: 896×1152 / 768×1344 / 1024×1024 — Default!)
           Tier 2 = `2K`   (Ultra HD 2MP: 1344×1728 / 1152×2048 / 1536×1536)
       - Video models (`minimax_h3`, `ltx`, `wan`):
           Tier 0 = `540p` (or `480p` on Wan — Fast / 16GB VRAM)
           Tier 1 = `720p` (Native HD — Default!)
           Tier 2 = `1080p` (Full HD — High VRAM / LTX-2.3 2x Spatial Upscaler)
    */
    const IMAGE_RES_TIERS = [
      {
        badge: 'DRAFT',
        label: '0.5K',
        ratios: { '9:16': [576, 1024], '3:4': [640, 832], '1:1': [768, 768], '4:3': [832, 640], '16:9': [1024, 576] }
      },
      {
        badge: 'NATIVE',
        label: '1K',
        ratios: { '9:16': [768, 1344], '3:4': [896, 1152], '1:1': [1024, 1024], '4:3': [1152, 896], '16:9': [1344, 768] }
      },
      {
        badge: 'ULTRA',
        label: '2K',
        ratios: { '9:16': [1152, 2048], '3:4': [1344, 1728], '1:1': [1536, 1536], '4:3': [1728, 1344], '16:9': [2048, 1152] }
      }
    ];

    const H3_VIDEO_RES_TIERS = [
      {
        badge: 'FAST',
        label: '540p',
        ratios: { '9:16': [544, 960], '3:4': [576, 768], '1:1': [768, 768], '4:3': [768, 576], '16:9': [960, 544] }
      },
      {
        badge: 'HD',
        label: '720p',
        ratios: { '9:16': [640, 864], '3:4': [768, 1024], '1:1': [960, 960], '4:3': [1024, 768], '16:9': [1280, 720] }
      },
      {
        badge: 'FHD',
        label: '1080p',
        ratios: { '9:16': [768, 1344], '3:4': [864, 1152], '1:1': [1024, 1024], '4:3': [1152, 864], '16:9': [1344, 768] }
      }
    ];

    const LTX_VIDEO_RES_TIERS = [
      {
        badge: 'FAST',
        label: '540p',
        ratios: { '9:16': [576, 1024], '3:4': [768, 1024], '1:1': [768, 768], '4:3': [1024, 768], '16:9': [1024, 576] }
      },
      {
        badge: 'HD',
        label: '720p',
        ratios: { '9:16': [704, 1280], '3:4': [896, 1152], '1:1': [1024, 1024], '4:3': [1152, 896], '16:9': [1280, 704] }
      },
      {
        badge: '2× UPSCALE',
        label: '1080p',
        ratios: { '9:16': [1088, 1920], '3:4': [1152, 1536], '1:1': [1408, 1408], '4:3': [1536, 1152], '16:9': [1920, 1088] }
      }
    ];

    const WAN_VIDEO_RES_TIERS = [
      {
        badge: '16GB FAST',
        label: '480p',
        ratios: { '9:16': [480, 832], '3:4': [544, 736], '1:1': [640, 640], '4:3': [736, 544], '16:9': [832, 480] }
      },
      {
        badge: 'HD',
        label: '720p',
        ratios: { '9:16': [704, 1280], '3:4': [768, 1024], '1:1': [960, 960], '4:3': [1024, 768], '16:9': [1280, 704] }
      },
      {
        badge: 'HIGH',
        label: '1080p',
        ratios: { '9:16': [832, 1472], '3:4': [896, 1152], '1:1': [1024, 1024], '4:3': [1152, 896], '16:9': [1472, 832] }
      }
    ];

    let resTierIdx = 1; // Default to Tier 1 (`1K` for Image models, `720p` for Video models)

    /* Per-Model Family Native Resolution Buckets & Temporal Frame Grid Rules */
    const MODEL_FAMILY_SPECS = {
      krea2: {
        ratios: IMAGE_RES_TIERS[1].ratios,
        resTiers: IMAGE_RES_TIERS,
        qualitySteps: { High: 8, Ultra: 12, Fast: 6 },
        defaultRatio: '3:4',
        steps: 8,
        sampler: 'euler',
        scheduler: 'simple',
        snapFrames: () => 1
      },
      flux3: {
        // FLUX 3 Image Klein (distilled): official templates use 16 steps, cfg 1.0, euler / simple
        ratios: IMAGE_RES_TIERS[1].ratios,
        resTiers: IMAGE_RES_TIERS,
        qualitySteps: { High: 16, Ultra: 24, Fast: 8 },
        defaultRatio: '3:4',
        steps: 16,
        sampler: 'euler',
        scheduler: 'simple',
        snapFrames: () => 1
      },
      flux: {
        ratios: IMAGE_RES_TIERS[1].ratios,
        resTiers: IMAGE_RES_TIERS,
        qualitySteps: { High: 20, Ultra: 28, Fast: 12 },
        defaultRatio: '3:4',
        steps: 20,
        sampler: 'euler',
        scheduler: 'simple',
        snapFrames: () => 1
      },
      qwen_image: {
        ratios: IMAGE_RES_TIERS[1].ratios,
        resTiers: IMAGE_RES_TIERS,
        qualitySteps: { High: 20, Ultra: 28, Fast: 12 },
        defaultRatio: '3:4',
        steps: 20,
        sampler: 'euler',
        scheduler: 'simple',
        snapFrames: () => 1
      },
      z_image: {
        ratios: IMAGE_RES_TIERS[1].ratios,
        resTiers: IMAGE_RES_TIERS,
        qualitySteps: { High: 8, Ultra: 12, Fast: 6 },
        defaultRatio: '3:4',
        steps: 8,
        sampler: 'res_multistep',
        scheduler: 'simple',
        snapFrames: () => 1
      },
      minimax_h3: {
        ratios: H3_VIDEO_RES_TIERS[1].ratios,
        resTiers: H3_VIDEO_RES_TIERS,
        qualitySteps: { High: 20, Ultra: 28, Fast: 8 },
        defaultRatio: '9:16',
        steps: 20,
        durations: [5.17, 8.0, 13.0, 15.08],
        snapFrames: (sec) => {
          const raw = Math.max(22, Math.min(362, Math.round(sec * 24)));
          const n = Math.max(1, Math.round((raw - 5) / 17));
          return Math.min(362, 17 * n + 5);
        }
      },
      ltx: {
        ratios: LTX_VIDEO_RES_TIERS[1].ratios,
        resTiers: LTX_VIDEO_RES_TIERS,
        qualitySteps: { High: 12, Ultra: 20, Fast: 8 },
        defaultRatio: '16:9',
        steps: 12,
        durations: [4.0, 5.0, 8.0, 10.7],
        snapFrames: (sec) => {
          const raw = Math.max(25, Math.min(257, Math.round(sec * 24)));
          const n = Math.max(3, Math.round((raw - 1) / 8));
          return 8 * n + 1;
        }
      },
      wan: {
        ratios: WAN_VIDEO_RES_TIERS[0].ratios,
        resTiers: WAN_VIDEO_RES_TIERS,
        qualitySteps: { High: 20, Ultra: 28, Fast: 8 },
        defaultRatio: '9:16',
        steps: 20,
        durations: [3.2, 3.4, 5.0],
        snapFrames: (sec) => {
          const raw = Math.max(17, Math.min(121, Math.round(sec * 24)));
          const n = Math.max(4, Math.round((raw - 1) / 4));
          return 4 * n + 1;
        }
      },
      audio_music: {
        ratios: IMAGE_RES_TIERS[1].ratios,
        resTiers: IMAGE_RES_TIERS,
        qualitySteps: { High: 30, Ultra: 40, Fast: 16 },
        defaultRatio: '1:1',
        steps: 30,
        durations: [15.0, 30.0, 45.0, 60.0],
        snapFrames: (sec) => Math.max(5, Math.round(sec)) * 24
      }
    };

    function detectModelFamily(modelIdOrName) {
      if (currentMode === 'audio') return 'audio_music';
      const s = (modelIdOrName || '').toLowerCase();
      if (s.includes('music') || s.includes('acestep') || s.includes('yue')) return 'audio_music';
      if (s.includes('shinjutsu') || s.includes('minimax') || s.includes('h3')) return 'minimax_h3';
      if (s.includes('ltx')) return 'ltx';
      if (s.includes('wan')) return 'wan';
      if (s.includes('z_image') || s.includes('z-image')) return 'z_image';
      if (s.includes('qwen')) return 'qwen_image';
      if (s.includes('flux3') || s.includes('flux_3') || s.includes('klein')) return 'flux3';
      if (s.includes('flux')) return 'flux';
      return 'krea2';
    }

    function getActiveDimensionsAndFrames() {
      const modelId = document.getElementById('model-picker').value || '';
      const fam = detectModelFamily(modelId);
      const spec = MODEL_FAMILY_SPECS[fam] || MODEL_FAMILY_SPECS.krea2;
      const tiers = spec.resTiers || IMAGE_RES_TIERS;
      const clampedTierIdx = Math.max(0, Math.min(tiers.length - 1, resTierIdx));
      const activeTier = tiers[clampedTierIdx] || tiers[1];
      const wh = (activeTier.ratios && activeTier.ratios[currentRatio])
        || spec.ratios[currentRatio]
        || spec.ratios[spec.defaultRatio]
        || [896, 1152];
      const finalW = customWidthOverride || wh[0];
      const finalH = customHeightOverride || wh[1];
      const frames = customFramesOverride || spec.snapFrames(currentDurationSec);
      return {
        family: fam,
        spec,
        resTiers: tiers,
        activeResTier: activeTier,
        width: finalW,
        height: finalH,
        frames,
        fps: 24,
        isCustomSize: Boolean(customWidthOverride && customHeightOverride)
      };
    }

    const RATIO_ICON_SIZES = {
      '9:16': [8, 13],
      '3:4': [9, 12],
      '1:1': [11, 11],
      '4:3': [12, 9],
      '16:9': [14, 8]
    };
