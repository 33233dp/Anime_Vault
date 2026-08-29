const searchInput = document.getElementById("searchInput");
const posterGrid = document.getElementById("posterGrid");
const visibleCount = document.getElementById("visibleCount");
const emptyState = document.getElementById("emptyState");

document.querySelectorAll("[data-copy-subscription]").forEach((button) => {
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }

  const originalLabel = button.textContent;
  let resetTimer;

  const copyText = async (value) => {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) {
      throw new Error("Clipboard copy failed");
    }
  };

  button.addEventListener("click", async () => {
    const value = button.dataset.copyValue || "";
    if (!value) {
      return;
    }

    window.clearTimeout(resetTimer);
    try {
      await copyText(value);
      button.textContent = "已复制 Animeko 订阅";
      resetTimer = window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 1800);
    } catch {
      button.textContent = "复制失败，请手动复制";
      resetTimer = window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 2400);
    }
  });
});

document.querySelectorAll("[data-delete-form]").forEach((form) => {
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  form.addEventListener("submit", (event) => {
    const title = form.dataset.animeTitle || "这部番剧";
    if (!window.confirm(`确定删除“${title}”吗？删除后不可恢复。`)) {
      event.preventDefault();
    }
  });
});

if (searchInput && posterGrid && visibleCount && emptyState) {
  const cards = Array.from(posterGrid.querySelectorAll(".poster-card"));

  const updateFilter = () => {
    const keyword = searchInput.value.trim().toLowerCase();
    let visible = 0;

    cards.forEach((card) => {
      const matched = card.dataset.search?.includes(keyword) ?? false;
      card.hidden = !matched;
      if (matched) {
        visible += 1;
      }
    });

    visibleCount.textContent = String(visible);
    emptyState.hidden = visible !== 0;
  };

  searchInput.addEventListener("input", updateFilter);
  updateFilter();

  const prefetched = new Set();
  cards.forEach((card) => {
    const link = card.querySelector("a");
    if (!link) {
      return;
    }

    const prefetch = () => {
      if (prefetched.has(link.href)) {
        return;
      }

      const hint = document.createElement("link");
      hint.rel = "prefetch";
      hint.href = link.href;
      document.head.appendChild(hint);
      prefetched.add(link.href);
    };

    card.addEventListener("mouseenter", prefetch, { once: true });
    card.addEventListener("focusin", prefetch, { once: true });
  });
}

const playbackForm = document.querySelector("[data-playback-form]");

if (playbackForm instanceof HTMLFormElement) {
  const playbackInput = playbackForm.querySelector("[data-playback-input]");
  const editToggle = playbackForm.querySelector("[data-edit-toggle]");
  const saveButton = playbackForm.querySelector("[data-save-button]");

  if (
    playbackInput instanceof HTMLInputElement &&
    editToggle instanceof HTMLButtonElement &&
    saveButton instanceof HTMLButtonElement
  ) {
    let editing = false;

    const syncEditingState = () => {
      playbackForm.dataset.editing = editing ? "true" : "false";
      playbackInput.readOnly = !editing;
      editToggle.setAttribute("aria-pressed", editing ? "true" : "false");
      editToggle.classList.toggle("is-active", editing);
      saveButton.disabled = !editing;

      if (editing) {
        playbackInput.focus();
        playbackInput.setSelectionRange(
          playbackInput.value.length,
          playbackInput.value.length,
        );
      } else {
        playbackInput.blur();
      }
    };

    const openPlaybackUrl = () => {
      const targetUrl = playbackInput.value.trim();
      const trackingUrl = playbackForm.dataset.playbackOpenUrl;
      if (!targetUrl || !trackingUrl) {
        return;
      }
      window.open(trackingUrl, "_blank", "noopener,noreferrer");
    };

    editToggle.addEventListener("click", () => {
      editing = !editing;
      syncEditingState();
    });

    playbackInput.addEventListener("click", (event) => {
      if (editing) {
        return;
      }
      event.preventDefault();
      openPlaybackUrl();
    });

    playbackInput.addEventListener("keydown", (event) => {
      if (editing) {
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPlaybackUrl();
      }
    });

    playbackForm.addEventListener("submit", () => {
      editing = false;
    });

    syncEditingState();
  }
}

const episodesPanel = document.querySelector("[data-episodes-panel]");

if (episodesPanel instanceof HTMLElement) {
  const configToggle = episodesPanel.querySelector("[data-episodes-config-toggle]");
  const configForm = episodesPanel.querySelector("[data-episodes-config-form]");

  if (
    configToggle instanceof HTMLButtonElement &&
    configForm instanceof HTMLFormElement
  ) {
    const syncConfigState = (open) => {
      configForm.hidden = !open;
      configToggle.setAttribute("aria-expanded", open ? "true" : "false");
      configToggle.classList.toggle("is-active", open);
    };

    syncConfigState(false);
    configToggle.addEventListener("click", () => {
      syncConfigState(configForm.hidden);
    });
  }
}

const supportedImageExtensions = new Set([
  "jpg",
  "jpeg",
  "png",
  "gif",
  "webp",
  "bmp",
  "svg",
  "avif",
]);

const imageUploads = document.querySelectorAll("[data-image-upload]");

imageUploads.forEach((upload) => {
  const dropzone = upload.querySelector("[data-upload-dropzone]");
  const input = upload.querySelector("[data-upload-input]");
  const fileStatus = upload.querySelector("[data-upload-file]");
  const preview = upload.querySelector("[data-upload-preview]");
  const previewImage = upload.querySelector("[data-upload-preview-image]");

  if (
    !(dropzone instanceof HTMLElement) ||
    !(input instanceof HTMLInputElement) ||
    !(fileStatus instanceof HTMLElement) ||
    !(preview instanceof HTMLElement) ||
    !(previewImage instanceof HTMLImageElement)
  ) {
    return;
  }

  let previewUrl = "";

  const revokePreview = () => {
    if (!previewUrl) {
      return;
    }
    URL.revokeObjectURL(previewUrl);
    previewUrl = "";
  };

  const clearPreview = () => {
    revokePreview();
    preview.hidden = true;
    previewImage.removeAttribute("src");
  };

  const isSupportedImage = (file) => {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    return supportedImageExtensions.has(extension);
  };

  const syncSelectedFile = (file) => {
    if (!file) {
      fileStatus.textContent = "未选择文件";
      dropzone.dataset.state = "idle";
      clearPreview();
      return;
    }

    if (!isSupportedImage(file)) {
      input.value = "";
      fileStatus.textContent = "文件格式不支持，请选择常见图片格式。";
      dropzone.dataset.state = "error";
      clearPreview();
      return;
    }

    fileStatus.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    dropzone.dataset.state = "selected";
    revokePreview();
    previewUrl = URL.createObjectURL(file);
    previewImage.src = previewUrl;
    preview.hidden = false;
  };

  const applyFiles = (fileList) => {
    const [file] = Array.from(fileList);
    if (!file) {
      syncSelectedFile(null);
      return;
    }

    if (typeof DataTransfer === "function") {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    }

    syncSelectedFile(file);
  };

  input.addEventListener("change", () => {
    applyFiles(input.files ?? []);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.dataset.dragging = "true";
    });
  });

  ["dragleave", "dragend", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, () => {
      dropzone.dataset.dragging = "false";
    });
  });

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    applyFiles(event.dataTransfer?.files ?? []);
  });

  window.addEventListener("beforeunload", revokePreview);
  syncSelectedFile(input.files?.[0] ?? null);
});


const syncResourceTypeControls = (form) => {
  const controls = Array.from(form.querySelectorAll("[data-resource-type]"));
  if (!controls.length) {
    return;
  }

  const sync = () => {
    const selected = controls.find((control) =>
      control instanceof HTMLInputElement && control.checked
    );
    const playlistSelected = selected instanceof HTMLInputElement && selected.value === "playlist";
    const urlListSelected = selected instanceof HTMLInputElement && selected.value === "url_list";
    form.querySelectorAll("[data-resource-link]").forEach((field) => {
      field.hidden = playlistSelected || urlListSelected;
    });
    form.querySelectorAll("[data-resource-playlist]").forEach((field) => {
      field.hidden = !playlistSelected;
    });
    form.querySelectorAll("[data-resource-url-list]").forEach((field) => {
      field.hidden = !urlListSelected;
    });
    form.querySelectorAll("[data-resource-import-offset]").forEach((field) => {
      field.hidden = !(playlistSelected || urlListSelected);
    });
  };

  controls.forEach((control) => control.addEventListener("change", sync));
  sync();
};

document.querySelectorAll("form").forEach((form) => syncResourceTypeControls(form));

document.querySelectorAll("[data-playlist-dropzone]").forEach((dropzone) => {
  const input = dropzone.querySelector("[data-playlist-input]");
  const status = dropzone.querySelector("[data-playlist-status]");
  if (!(input instanceof HTMLInputElement) || !(status instanceof HTMLElement)) {
    return;
  }

  const applyFile = (file) => {
    if (!file) {
      return;
    }
    if (!file.name.toLowerCase().endsWith(".m3u8")) {
      input.value = "";
      status.textContent = "文件格式不支持，请选择 .m3u8 文件。";
      dropzone.dataset.state = "error";
      return;
    }
    status.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
    dropzone.dataset.state = "selected";
  };

  input.addEventListener("change", () => applyFile(input.files?.[0]));
  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.dataset.dragging = "true";
    });
  });
  ["dragleave", "dragend", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, () => {
      dropzone.dataset.dragging = "false";
    });
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (!file) {
      return;
    }
    if (typeof DataTransfer === "function") {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    }
    applyFile(file);
  });
});


const syncPlaybackModeControls = (container) => {
  const modeControls = Array.from(container.querySelectorAll("[data-playback-mode]"));
  if (!modeControls.length) {
    return;
  }

  const getMode = () => {
    const checkedRadio = modeControls.find((control) => control instanceof HTMLInputElement && control.type === "radio" && control.checked);
    if (checkedRadio instanceof HTMLInputElement) {
      return checkedRadio.value;
    }
    const select = modeControls.find((control) => control instanceof HTMLSelectElement);
    if (select instanceof HTMLSelectElement) {
      return select.value;
    }
    return "online";
  };

  const sync = () => {
    const localMode = getMode() === "local";
    container.querySelectorAll("[data-online-config]").forEach((field) => {
      field.hidden = localMode;
    });
    container.querySelectorAll("[data-local-config]").forEach((field) => {
      field.hidden = !localMode;
    });
  };

  modeControls.forEach((control) => control.addEventListener("change", sync));
  sync();
};

document.querySelectorAll("form").forEach((form) => syncPlaybackModeControls(form));

const localPlayer = document.querySelector("[data-local-player]");

if (localPlayer instanceof HTMLElement) {
  const video = localPlayer.querySelector("[data-local-video]");
  const stage = localPlayer.querySelector("[data-local-player-stage]");
  const title = localPlayer.querySelector("[data-local-player-title]");
  const lastPlayedValue = document.querySelector("[data-last-played-value]");
  const episodeLinks = Array.from(document.querySelectorAll("[data-local-episode]"));
  const toggleButtons = Array.from(localPlayer.querySelectorAll("[data-player-toggle]"));
  const seekInput = localPlayer.querySelector("[data-player-seek]");
  const currentTimeText = localPlayer.querySelector("[data-player-current]");
  const durationText = localPlayer.querySelector("[data-player-duration]");
  const volumeInput = localPlayer.querySelector("[data-player-volume]");
  const volumeIcon = localPlayer.querySelector("[data-player-volume-icon]");
  const speedSelect = localPlayer.querySelector("[data-player-speed]");
  const fullscreenButton = localPlayer.querySelector("[data-player-fullscreen]");
  const prevButton = localPlayer.querySelector("[data-player-prev]");
  const nextButton = localPlayer.querySelector("[data-player-next]");
  const mpvLink = localPlayer.querySelector("[data-mpv-link]");

  if (video instanceof HTMLVideoElement) {
    const formatTime = (seconds) => {
      if (!Number.isFinite(seconds) || seconds <= 0) {
        return "00:00";
      }
      const wholeSeconds = Math.floor(seconds);
      const hours = Math.floor(wholeSeconds / 3600);
      const minutes = Math.floor((wholeSeconds % 3600) / 60);
      const secs = wholeSeconds % 60;
      const paddedMinutes = String(minutes).padStart(2, "0");
      const paddedSeconds = String(secs).padStart(2, "0");
      return hours > 0
        ? `${hours}:${paddedMinutes}:${paddedSeconds}`
        : `${paddedMinutes}:${paddedSeconds}`;
    };

    const setRangeProgress = (input, value) => {
      if (input instanceof HTMLInputElement) {
        input.style.setProperty("--progress", `${Math.max(0, Math.min(1, value)) * 100}%`);
      }
    };

    const activeEpisodeIndex = () => episodeLinks.findIndex((link) =>
      link.classList.contains("episode-card--active"),
    );

    const activeEpisodeLink = () => {
      const activeIndex = activeEpisodeIndex();
      const activeLink = episodeLinks[activeIndex];
      return activeLink instanceof HTMLAnchorElement ? activeLink : null;
    };

    const parseProgressNumber = (value) => {
      const number = Number(value);
      return Number.isFinite(number) && number > 0 ? number : 0;
    };

    const readLinkProgress = (link) => ({
      position: parseProgressNumber(link.dataset.progressPosition),
      duration: parseProgressNumber(link.dataset.progressDuration),
      completed: link.dataset.progressCompleted === "1",
    });

    const progressLabelFor = (position, completed) => {
      if (completed) {
        return "已看完";
      }
      if (position > 0) {
        return `看到 ${formatTime(position)}`;
      }
      return "";
    };

    const writeLinkProgress = (link, position, duration, completed) => {
      link.dataset.progressPosition = String(Math.max(0, position));
      link.dataset.progressDuration = String(Math.max(0, duration));
      link.dataset.progressCompleted = completed ? "1" : "0";
      const progressLabel = link.querySelector("[data-progress-label]");
      if (progressLabel instanceof HTMLElement) {
        const labelText = progressLabelFor(position, completed);
        progressLabel.textContent = labelText;
        progressLabel.hidden = !labelText;
      }
    };

    const syncEpisodeButtons = () => {
      const activeIndex = activeEpisodeIndex();
      if (prevButton instanceof HTMLButtonElement) {
        prevButton.disabled = activeIndex <= 0;
      }
      if (nextButton instanceof HTMLButtonElement) {
        nextButton.disabled = episodeLinks.length === 0 || activeIndex >= episodeLinks.length - 1;
      }
    };

    const syncPlaybackButtons = () => {
      const playing = !video.paused && !video.ended;
      toggleButtons.forEach((button) => {
        if (!(button instanceof HTMLButtonElement)) {
          return;
        }
        button.textContent = playing ? "暂停" : "▶";
        button.setAttribute("aria-label", playing ? "暂停" : "播放");
      });
      localPlayer.dataset.playing = playing ? "true" : "false";
      showPlayerControls({ persistent: !playing });
    };

    const syncTime = () => {
      const duration = Number.isFinite(video.duration) ? video.duration : 0;
      const progress = duration > 0 ? video.currentTime / duration : 0;
      if (currentTimeText instanceof HTMLElement) {
        currentTimeText.textContent = formatTime(video.currentTime);
      }
      if (durationText instanceof HTMLElement) {
        durationText.textContent = formatTime(duration);
      }
      if (seekInput instanceof HTMLInputElement) {
        seekInput.value = String(Math.round(progress * Number(seekInput.max || 1000)));
        setRangeProgress(seekInput, progress);
      }
    };

    const syncVolume = () => {
      const volume = video.muted ? 0 : video.volume;
      if (volumeInput instanceof HTMLInputElement) {
        volumeInput.value = String(volume);
        setRangeProgress(volumeInput, volume);
      }
      if (volumeIcon instanceof HTMLElement) {
        volumeIcon.textContent = volume === 0 ? "静音" : "音量";
      }
    };

    let controlsHideTimer = 0;

    const setControlsVisible = (visible) => {
      localPlayer.dataset.controlsVisible = visible ? "true" : "false";
    };

    const queueControlsHide = () => {
      window.clearTimeout(controlsHideTimer);
      if (video.paused || video.ended) {
        setControlsVisible(true);
        return;
      }
      controlsHideTimer = window.setTimeout(() => {
        setControlsVisible(false);
      }, 2200);
    };

    const showPlayerControls = ({ persistent = false } = {}) => {
      window.clearTimeout(controlsHideTimer);
      setControlsVisible(true);
      if (!persistent) {
        queueControlsHide();
      }
    };

    const progressUrl = localPlayer.dataset.progressUrl || "";
    let pendingResumeTime = null;
    let saveProgressTimer = 0;
    let lastSavedAt = 0;
    let currentEpisodeLoaded = false;
    let watchedSeconds = 0;
    let lastPlaybackSample = null;

    const normalizedProgress = (completed = false) => {
      const duration = Number.isFinite(video.duration) ? video.duration : 0;
      let position = Number.isFinite(video.currentTime) ? video.currentTime : 0;
      const finished = completed || (duration > 0 && position >= Math.max(0, duration - 2));
      if (finished && duration > 0) {
        position = duration;
      }
      return { position, duration, completed: finished };
    };

    const persistProgress = ({ completed = false, immediate = false } = {}) => {
      const link = activeEpisodeLink();
      if (!link || !progressUrl) {
        return;
      }
      if (!currentEpisodeLoaded && !completed) {
        return;
      }

      const episodeNumber = link.getAttribute("data-episode-number") || "";
      if (!episodeNumber) {
        return;
      }

      const progress = normalizedProgress(completed);
      writeLinkProgress(link, progress.position, progress.duration, progress.completed);
      window.clearTimeout(saveProgressTimer);

      const body = new URLSearchParams({
        episode_number: episodeNumber,
        position_seconds: progress.position.toFixed(3),
        duration_seconds: progress.duration.toFixed(3),
        watched_seconds: watchedSeconds.toFixed(3),
        completed: progress.completed ? "1" : "0",
      });

      const send = () => {
        lastSavedAt = Date.now();
        fetch(progressUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body,
          keepalive: true,
        }).catch(() => {});
      };

      if (immediate) {
        send();
        return;
      }

      const elapsed = Date.now() - lastSavedAt;
      if (elapsed >= 5000) {
        send();
        return;
      }
      saveProgressTimer = window.setTimeout(send, Math.max(800, 5000 - elapsed));
    };

    const resumeTimeFor = (link) => {
      const progress = readLinkProgress(link);
      if (progress.completed) {
        return 0;
      }
      const duration = progress.duration || 0;
      if (duration > 0 && duration - progress.position <= 5) {
        return 0;
      }
      return progress.position > 3 ? progress.position : 0;
    };

    const applyPendingResume = () => {
      if (pendingResumeTime === null) {
        return;
      }
      const resumeTime = pendingResumeTime;
      pendingResumeTime = null;
      const duration = Number.isFinite(video.duration) ? video.duration : 0;
      if (resumeTime > 0 && duration > 0) {
        video.currentTime = Math.min(resumeTime, Math.max(0, duration - 2));
      }
      syncTime();
    };

    const playEpisode = (link, options = {}) => {
      persistProgress({ immediate: true });
      const episodeNumber = link.getAttribute("data-episode-number") || "";
      const episodeTitle = link.getAttribute("data-episode-title") || `第 ${episodeNumber} 集`;
      episodeLinks.forEach((item) => item.classList.remove("episode-card--active"));
      link.classList.add("episode-card--active");
      if (title instanceof HTMLElement) {
        title.textContent = episodeTitle;
      }
      if (lastPlayedValue instanceof HTMLElement) {
        lastPlayedValue.textContent = episodeNumber || "未播放";
      }
      if (mpvLink instanceof HTMLAnchorElement) {
        mpvLink.href = link.href.replace("/local-episode/", "/mpv-playlist/");
        mpvLink.hidden = false;
      }
      localPlayer.hidden = false;
      pendingResumeTime = options.resume === false ? null : resumeTimeFor(link);
      currentEpisodeLoaded = false;
      lastPlaybackSample = null;
      video.src = link.href;
      video.load();
      syncEpisodeButtons();
      syncTime();
      showPlayerControls();
      video.play().catch(() => {});
      if (stage instanceof HTMLElement) {
        stage.focus({ preventScroll: true });
      }
      if (options.scroll !== false) {
        localPlayer.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    };

    const togglePlayback = () => {
      if (!video.currentSrc && episodeLinks[0] instanceof HTMLAnchorElement) {
        playEpisode(episodeLinks[0]);
        return;
      }
      if (video.paused || video.ended) {
        video.play().catch(() => {});
      } else {
        video.pause();
      }
    };

    const playRelativeEpisode = (offset) => {
      const activeIndex = activeEpisodeIndex();
      const targetIndex = activeIndex === -1 && offset > 0 ? 0 : activeIndex + offset;
      const targetLink = episodeLinks[targetIndex];
      if (targetLink instanceof HTMLAnchorElement) {
        playEpisode(targetLink, { scroll: false });
      }
    };

    episodeLinks.forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        playEpisode(link);
      });
    });

    toggleButtons.forEach((button) => {
      button.addEventListener("click", togglePlayback);
    });

    video.addEventListener("click", togglePlayback);

    if (mpvLink instanceof HTMLAnchorElement) {
      mpvLink.addEventListener("click", (event) => {
        if (mpvLink.hidden || mpvLink.getAttribute("href") === "#") {
          event.preventDefault();
        }
      });
    }

    if (seekInput instanceof HTMLInputElement) {
      seekInput.addEventListener("input", () => {
        const duration = Number.isFinite(video.duration) ? video.duration : 0;
        const max = Number(seekInput.max || 1000);
        const ratio = max > 0 ? Number(seekInput.value) / max : 0;
        if (duration > 0) {
          video.currentTime = ratio * duration;
        }
        setRangeProgress(seekInput, ratio);
      });
    }

    if (volumeInput instanceof HTMLInputElement) {
      volumeInput.addEventListener("input", () => {
        const volume = Number(volumeInput.value);
        video.volume = Math.max(0, Math.min(1, volume));
        video.muted = video.volume === 0;
        syncVolume();
      });
    }

    if (speedSelect instanceof HTMLSelectElement) {
      speedSelect.addEventListener("change", () => {
        video.playbackRate = Number(speedSelect.value) || 1;
      });
    }

    if (prevButton instanceof HTMLButtonElement) {
      prevButton.addEventListener("click", () => playRelativeEpisode(-1));
    }

    if (nextButton instanceof HTMLButtonElement) {
      nextButton.addEventListener("click", () => playRelativeEpisode(1));
    }

    if (fullscreenButton instanceof HTMLButtonElement && stage instanceof HTMLElement) {
      fullscreenButton.addEventListener("click", () => {
        if (document.fullscreenElement) {
          document.exitFullscreen?.();
          return;
        }
        if (stage.requestFullscreen) {
          stage.requestFullscreen().catch(() => {});
        } else if (typeof video.webkitEnterFullscreen === "function") {
          video.webkitEnterFullscreen();
        }
      });
    }

    if (stage instanceof HTMLElement) {
      ["mousemove", "pointermove", "focusin"].forEach((eventName) => {
        stage.addEventListener(eventName, () => showPlayerControls());
      });
      stage.addEventListener("touchstart", () => showPlayerControls(), { passive: true });
      stage.addEventListener("mouseleave", () => queueControlsHide());
      stage.addEventListener("keydown", (event) => {
        const activeElement = document.activeElement;
        if (activeElement instanceof HTMLInputElement || activeElement instanceof HTMLSelectElement) {
          return;
        }
        showPlayerControls();
        if (event.key === " " || event.key.toLowerCase() === "k") {
          event.preventDefault();
          togglePlayback();
        } else if (event.key === "ArrowLeft") {
          event.preventDefault();
          video.currentTime = Math.max(0, video.currentTime - 5);
          persistProgress();
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          video.currentTime = Math.min(video.duration || video.currentTime + 5, video.currentTime + 5);
          persistProgress();
        } else if (event.key.toLowerCase() === "f") {
          event.preventDefault();
          fullscreenButton?.click();
        } else if (event.key.toLowerCase() === "m") {
          event.preventDefault();
          video.muted = !video.muted;
          syncVolume();
        }
      });
    }

    video.addEventListener("loadedmetadata", () => {
      currentEpisodeLoaded = true;
      applyPendingResume();
      syncTime();
    });
    video.addEventListener("timeupdate", () => {
      if (!video.paused && !video.seeking && Number.isFinite(video.currentTime)) {
        if (lastPlaybackSample !== null) {
          const delta = video.currentTime - lastPlaybackSample;
          if (delta > 0 && delta <= 4) {
            watchedSeconds += delta;
          }
        }
        lastPlaybackSample = video.currentTime;
      }
      syncTime();
      persistProgress();
    });
    video.addEventListener("durationchange", syncTime);
    video.addEventListener("play", () => {
      lastPlaybackSample = Number.isFinite(video.currentTime) ? video.currentTime : null;
      syncPlaybackButtons();
    });
    video.addEventListener("pause", () => {
      lastPlaybackSample = null;
      syncPlaybackButtons();
      persistProgress({ immediate: true });
    });
    video.addEventListener("seeking", () => {
      lastPlaybackSample = null;
    });
    video.addEventListener("seeked", () => {
      lastPlaybackSample = Number.isFinite(video.currentTime) ? video.currentTime : null;
      persistProgress({ immediate: true });
    });
    video.addEventListener("volumechange", syncVolume);
    video.addEventListener("ratechange", () => {
      if (speedSelect instanceof HTMLSelectElement) {
        speedSelect.value = String(video.playbackRate);
      }
    });

    video.addEventListener("ended", () => {
      persistProgress({ completed: true, immediate: true });
      const activeIndex = activeEpisodeIndex();
      const nextLink = episodeLinks[activeIndex + 1];
      if (nextLink instanceof HTMLAnchorElement) {
        playEpisode(nextLink, { scroll: false });
      } else {
        syncPlaybackButtons();
      }
    });

    window.addEventListener("beforeunload", () => {
      persistProgress({ immediate: true });
    });

    const initialLink = activeEpisodeLink();
    if (initialLink) {
      pendingResumeTime = resumeTimeFor(initialLink);
      if (video.readyState >= 1) {
        currentEpisodeLoaded = true;
        applyPendingResume();
      }
    }

    syncEpisodeButtons();
    syncPlaybackButtons();
    syncTime();
    syncVolume();
  }
}
