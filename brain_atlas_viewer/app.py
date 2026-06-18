#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import struct
import threading
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import nrrd
import numpy as np


DEFAULT_RUN_DIR = Path(
    "/Users/ddharmap/dataProcessing/brainMapping_registered/"
    "run_microns_fx_f01/_observed_channels_in_f01_DAPI/20260528_184357"
)
DEFAULT_REFERENCE_PATH = Path(
    "/Users/ddharmap/dataProcessing/20260525_brainMapping_preprocessed/session2/"
    "20260320_f01_cort_546_gad2_647_Stitch_preprocessed/"
    "20260320_f01_cort_546_gad2_647_Stitch_DAPI_740nm_preprocessed.nrrd"
)
MANIFEST_NAME = "observed_channel_transform_manifest.csv"
MARKER_PALETTE = [
    "#00c853",
    "#ffb000",
    "#ff2d55",
    "#00b8ff",
    "#d65cff",
    "#00d1c1",
    "#ff7a1a",
    "#c7f464",
    "#7f8cff",
    "#ff66c4",
    "#a6a000",
    "#00a676",
    "#ff4fd8",
    "#40e0ff",
    "#b388ff",
    "#ff5252",
    "#64dd17",
    "#ffcc80",
    "#18ffff",
    "#ff80ab",
    "#b2ff59",
    "#82b1ff",
    "#ffd740",
    "#ea80fc",
]

PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Brain Mapping Registered Atlas Viewer</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #171b22;
      color: #f3f6fb;
    }
    * { box-sizing: border-box; }
    html, body, #app { width: 100%; height: 100%; margin: 0; }
    body { overflow: hidden; background: #171b22; }
    button, input {
      font: inherit;
    }
    button {
      border: 1px solid #3e4c66;
      background: #263047;
      color: #eef4ff;
      border-radius: 7px;
      min-height: 34px;
      padding: 6px 11px;
      cursor: pointer;
    }
    button:hover { background: #313d5b; border-color: #5b78aa; }
    button:focus, input:focus { outline: 2px solid #6aa9ff; outline-offset: 1px; }
    input[type="range"] { width: 100%; accent-color: #69a9ff; }
    input[type="search"], input[type="number"], input[type="color"] {
      border: 1px solid #35435e;
      background: #171d2a;
      color: #f3f6fb;
      border-radius: 7px;
      min-height: 32px;
      padding: 4px 8px;
    }
    #app-root {
      height: 100%;
      display: flex;
      flex-direction: column;
    }
    #main {
      min-height: 0;
      height: calc(100vh - 38px);
      display: grid;
      grid-template-columns: minmax(290px, 340px) 1fr;
      background: #1d222b;
    }
    #menu {
      border-right: 1px solid #2f3850;
      background: #202633;
      overflow-y: auto;
      padding: 16px 10px 12px;
      box-shadow: 2px 0 14px rgba(0, 0, 0, .35);
    }
    h1 {
      font-size: 1.12rem;
      line-height: 1.25;
      margin: 0 6px 16px;
      font-weight: 800;
      font-style: italic;
    }
    details {
      margin: 0 0 10px;
      border: 1px solid #303b55;
      background: #242b3b;
      border-radius: 8px;
      overflow: hidden;
    }
    summary {
      cursor: pointer;
      padding: 10px 12px;
      font-size: 1.02rem;
      font-weight: 800;
      list-style: none;
      border-bottom: 1px solid #303b55;
    }
    details:not([open]) summary { border-bottom: 0; }
    summary::-webkit-details-marker { display: none; }
    summary::before {
      content: "▶";
      color: #76adff;
      display: inline-block;
      width: 1.25em;
    }
    details[open] summary::before { content: "▼"; }
    .panel {
      padding: 12px;
    }
    .control-row {
      display: grid;
      grid-template-columns: 96px 1fr;
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
    }
    .button-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
    }
    .search-box { width: 100%; margin-bottom: 10px; }
    #layer-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
      max-height: 58vh;
      overflow-y: auto;
      padding-right: 2px;
    }
    .layer-row {
      display: grid;
      grid-template-columns: 22px 16px 1fr auto;
      gap: 8px;
      align-items: center;
      min-height: 40px;
      padding: 5px 6px;
      border-radius: 7px;
      color: #aeb9cd;
      cursor: pointer;
      border: 1px solid transparent;
    }
    .layer-row.active {
      color: #fff;
      background: #2a3349;
      border-color: #405176;
    }
    .layer-row.selected {
      border-color: #79adff;
      box-shadow: inset 0 0 0 1px rgba(121, 173, 255, .55);
    }
    .layer-visible {
      width: 16px;
      height: 16px;
      accent-color: #69a9ff;
      cursor: pointer;
    }
    .swatch {
      width: 11px;
      height: 11px;
      border-radius: 50%;
      border: 1px solid rgba(255,255,255,.45);
    }
    .layer-name {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-weight: 700;
    }
    .layer-subject {
      grid-column: 3 / 5;
      color: #8895ad;
      font-size: .78rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .pill {
      color: #c8d8f4;
      font-size: .78rem;
      border: 1px solid #394864;
      border-radius: 999px;
      padding: 1px 7px;
      background: #1b2230;
    }
    #layer-settings {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #303b55;
    }
    #layer-settings .layer-title {
      font-weight: 800;
      margin-bottom: 3px;
    }
    #layer-settings .layer-range-readout {
      text-align: right;
      color: #dbe8ff;
      font-variant-numeric: tabular-nums;
    }
    #slices {
      min-width: 0;
      min-height: 0;
      background: #1e232c;
      padding: 6px;
      overflow: auto;
    }
    #slice-grid {
      display: inline-grid;
      grid-template-columns: auto auto;
      grid-template-rows: auto auto;
      gap: 6px;
      align-items: start;
      justify-items: start;
      transform-origin: top left;
    }
    .viewport {
      position: relative;
      background: #030407;
      border: 1px solid #3d4659;
      min-width: 80px;
      min-height: 80px;
    }
    .viewport.focused { border-color: #79adff; box-shadow: 0 0 0 1px #79adff; }
    .viewport-title {
      position: absolute;
      top: 5px;
      left: 7px;
      z-index: 2;
      font-size: .74rem;
      color: #d7e6ff;
      background: rgba(10, 14, 20, .6);
      border: 1px solid rgba(255,255,255,.18);
      border-radius: 5px;
      padding: 1px 5px;
      pointer-events: none;
    }
    canvas {
      display: block;
      image-rendering: auto;
      background: #030407;
      cursor: crosshair;
    }
    #axial-wrap { grid-column: 1 / 2; }
    #status {
      height: 38px;
      display: flex;
      align-items: center;
      gap: 22px;
      padding: 0 14px;
      border-top: 1px solid #31406a;
      background: #181e28;
      color: #e6efff;
      white-space: nowrap;
      box-shadow: 0 -2px 10px rgba(0,0,0,.35);
    }
    #status .muted { color: #96a4bc; }
    #status .grow {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .meta {
      color: #a9b7cf;
      font-size: .86rem;
      line-height: 1.35;
    }
    .error {
      color: #ffd2d2;
      background: #4a1f28;
      border: 1px solid #82424f;
      padding: 8px;
      border-radius: 7px;
      margin: 10px 0;
      display: none;
    }
  </style>
</head>
<body>
<div id="app">Loading...</div>
<script>
const state = {
  metadata: null,
  active: new Set(),
  selectedLayer: null,
  gains: {},
  coord: {x: 0, y: 0, z: 0},
  brightness: 100,
  contrast: 100,
  opacity: 75,
  mip: false,
  crosshair: true,
  crosshairColor: "#ff314f",
  scale: 1,
  userScaled: false,
  focusedPlane: "sagittal",
  query: ""
};

const planeAxis = { sagittal: "x", coronal: "y", axial: "z" };
const planes = ["sagittal", "coronal", "axial"];

function qs(name, fallback) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name) ?? fallback;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function activeIds() {
  return Array.from(state.active);
}

function layerById(id) {
  return state.metadata.layers.find(layer => layer.id === id);
}

function activeLabels() {
  return activeIds().map(id => {
    const layer = layerById(id);
    return layer ? `${layer.marker} ${layer.wavelength}` : id;
  });
}

function layerGain(id) {
  return Number(state.gains[id] ?? 1);
}

function gainParam() {
  return Object.entries(state.gains)
    .filter(([, gain]) => Math.abs(Number(gain) - 1) > 0.0001)
    .map(([id, gain]) => `${id}:${Number(gain).toFixed(2)}`)
    .join(",");
}

function parseGainParam(value) {
  const gains = {};
  for (const item of String(value || "").split(",")) {
    const [id, rawGain] = item.split(":");
    if (!id || rawGain === undefined) continue;
    const gain = clamp(Number(rawGain), 0, 5);
    if (Number.isFinite(gain)) gains[id] = gain;
  }
  return gains;
}

function planeIndex(plane) {
  if (state.mip) return "mip";
  return state.coord[planeAxis[plane]];
}

function imageUrl(plane) {
  const params = new URLSearchParams({
    plane,
    index: String(planeIndex(plane)),
    layers: activeIds().join(","),
    brightness: String(state.brightness),
    contrast: String(state.contrast),
    opacity: String(state.opacity / 100),
    gains: gainParam(),
    mip: state.mip ? "1" : "0",
    ref: "fixed-dapi-v1"
  });
  return `/api/composite?${params.toString()}`;
}

function appHtml() {
  return `
    <div id="app-root">
      <div id="main">
        <aside id="menu">
          <h1>Brain mapping registered atlas viewer</h1>
          <div id="error-box" class="error"></div>
          <details open>
            <summary>Controls</summary>
            <div class="panel">
              <div class="control-row"><label>Brightness</label><input id="brightness" type="range" min="0" max="250" value="${state.brightness}"></div>
              <div class="control-row"><label>Contrast</label><input id="contrast" type="range" min="1" max="250" value="${state.contrast}"></div>
              <div class="control-row"><label>Opacity</label><input id="opacity" type="range" min="0" max="100" value="${state.opacity}"></div>
              <div class="control-row"><label>Crosshair</label><input id="crosshair-color" type="color" value="${state.crosshairColor}"></div>
              <div class="button-grid">
                <button id="mip-toggle">Show as MIP</button>
                <button id="crosshair-toggle">Hide Crosshair</button>
                <button id="zoom-out">Zoom -</button>
                <button id="zoom-in">Zoom +</button>
                <button id="reset-view">Reset View</button>
                <button id="share-view">Share View</button>
              </div>
            </div>
          </details>
          <details open>
            <summary>Registered Channels</summary>
            <div class="panel">
              <input id="layer-search" class="search-box" type="search" placeholder="Search marker or subject..." value="${state.query}">
              <div id="layer-list"></div>
              <div id="layer-settings"></div>
            </div>
          </details>
          <details>
            <summary>Run</summary>
            <div class="panel meta" id="run-meta"></div>
          </details>
        </aside>
        <main id="slices">
          <div id="slice-grid">
            ${planes.map(plane => `
              <div class="viewport" id="${plane}-wrap">
                <div class="viewport-title">${plane}</div>
                <canvas id="canvas-${plane}" data-plane="${plane}"></canvas>
              </div>
            `).join("")}
          </div>
        </main>
      </div>
      <footer id="status">
        <span id="coord-status"></span>
        <span id="focused-status" class="muted"></span>
        <span id="layer-status" class="grow"></span>
      </footer>
    </div>`;
}

function bindControls() {
  for (const id of ["brightness", "contrast", "opacity"]) {
    document.getElementById(id).addEventListener("input", event => {
      state[id] = Number(event.target.value);
      renderImages();
      updateStatus();
    });
  }
  document.getElementById("crosshair-color").addEventListener("input", event => {
    state.crosshairColor = event.target.value;
    redrawCrosshairs();
  });
  document.getElementById("mip-toggle").addEventListener("click", () => {
    state.mip = !state.mip;
    document.getElementById("mip-toggle").textContent = state.mip ? "Show Slices" : "Show as MIP";
    renderImages();
    updateStatus();
  });
  document.getElementById("crosshair-toggle").addEventListener("click", () => {
    state.crosshair = !state.crosshair;
    document.getElementById("crosshair-toggle").textContent = state.crosshair ? "Hide Crosshair" : "Show Crosshair";
    redrawCrosshairs();
  });
  document.getElementById("zoom-in").addEventListener("click", () => {
    state.userScaled = true;
    setScale(state.scale * 1.15);
  });
  document.getElementById("zoom-out").addEventListener("click", () => {
    state.userScaled = true;
    setScale(state.scale / 1.15);
  });
  document.getElementById("reset-view").addEventListener("click", resetView);
  document.getElementById("share-view").addEventListener("click", shareView);
  document.getElementById("layer-search").addEventListener("input", event => {
    state.query = event.target.value;
    renderLayerList();
  });
  for (const plane of planes) {
    const canvas = document.getElementById(`canvas-${plane}`);
    canvas.addEventListener("mousedown", event => handleCanvasPointer(plane, event));
    canvas.addEventListener("mousemove", event => {
      if (event.buttons === 1) handleCanvasPointer(plane, event);
    });
    canvas.addEventListener("wheel", event => handleWheel(plane, event), {passive: false});
  }
  window.addEventListener("keydown", event => {
    if (event.target && ["INPUT", "TEXTAREA"].includes(event.target.tagName)) return;
    if (event.key === "+" || event.key === "=") {
      state.userScaled = true;
      setScale(state.scale * 1.12);
    }
    if (event.key === "-" || event.key === "_") {
      state.userScaled = true;
      setScale(state.scale / 1.12);
    }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      const delta = event.key === "ArrowUp" ? 1 : -1;
      stepPlane(state.focusedPlane, delta);
    }
  });
}

function renderLayerList() {
  const list = document.getElementById("layer-list");
  const query = state.query.trim().toLowerCase();
  const layers = state.metadata.layers.filter(layer => {
    if (!query) return true;
    return [layer.marker, layer.wavelength, layer.subject, layer.registered_subject]
      .join(" ").toLowerCase().includes(query);
  });
  list.innerHTML = layers.map(layer => `
    <div class="layer-row ${state.active.has(layer.id) ? "active" : ""} ${state.selectedLayer === layer.id ? "selected" : ""}" data-id="${layer.id}" title="${escapeHtml(layer.registered_subject)}">
      <input class="layer-visible" type="checkbox" ${state.active.has(layer.id) ? "checked" : ""} aria-label="Toggle ${escapeHtml(layer.marker)} visibility">
      <span class="swatch" style="background:${layer.color}"></span>
      <span class="layer-name">${escapeHtml(layer.marker)}</span>
      <span class="pill">${escapeHtml(layer.wavelength)}</span>
      <span class="layer-subject">${escapeHtml(layer.registered_subject)}</span>
    </div>
  `).join("");
  for (const row of list.querySelectorAll(".layer-row")) {
    row.addEventListener("click", () => {
      state.selectedLayer = row.dataset.id;
      renderLayerList();
      updateStatus();
    });
    row.querySelector(".layer-visible").addEventListener("click", event => {
      event.stopPropagation();
    });
    row.querySelector(".layer-visible").addEventListener("change", event => {
      const id = row.dataset.id;
      state.selectedLayer = id;
      if (event.target.checked) state.active.add(id);
      else state.active.delete(id);
      renderLayerList();
      renderImages();
      updateStatus();
    });
  }
  renderLayerSettings();
}

function renderLayerSettings() {
  const panel = document.getElementById("layer-settings");
  const layer = state.selectedLayer ? layerById(state.selectedLayer) : null;
  if (!layer) {
    panel.innerHTML = `<div class="meta">Select a layer to adjust its gain.</div>`;
    return;
  }
  const gain = layerGain(layer.id);
  panel.innerHTML = `
    <div class="layer-title">${escapeHtml(layer.marker)} ${escapeHtml(layer.wavelength)}</div>
    <div class="meta">${escapeHtml(layer.registered_subject)}</div>
    <div class="meta">Clip: stack p1-p99.5; Gain: <span id="layer-gain-value">${gain.toFixed(2)}x</span></div>
    <div class="control-row">
      <label>Layer gain</label>
      <input id="layer-gain" type="range" min="0" max="5" step="0.05" value="${gain}">
    </div>
  `;
  document.getElementById("layer-gain").addEventListener("input", event => {
    const nextGain = clamp(Number(event.target.value), 0, 5);
    state.gains[layer.id] = nextGain;
    document.getElementById("layer-gain-value").textContent = `${nextGain.toFixed(2)}x`;
    renderImages();
    updateStatus();
  });
}

function renderRunMeta() {
  const meta = state.metadata;
  document.getElementById("run-meta").innerHTML = `
    <div><strong>${escapeHtml(meta.run_name)}</strong></div>
    <div>${meta.layer_count} channels, ${meta.subject_count} registered subjects</div>
    <div>Volume: ${meta.dimensions.x} x ${meta.dimensions.y} x ${meta.dimensions.z} voxels</div>
    <div>Spacing: ${meta.spacing.x.toFixed(3)}, ${meta.spacing.y.toFixed(3)}, ${meta.spacing.z.toFixed(3)} um</div>
    <div>Reference: ${escapeHtml(meta.reference.name)}</div>
    <div>Source: ${escapeHtml(meta.run_dir)}</div>
  `;
}

function renderImages() {
  for (const plane of planes) loadPlane(plane);
}

function loadPlane(plane) {
  const canvas = document.getElementById(`canvas-${plane}`);
  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.onload = () => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    drawCrosshair(canvas, plane);
    if (!state.userScaled) setScale(fitScale());
  };
  img.onerror = () => showError(`Could not load ${plane} image.`);
  img.src = imageUrl(plane);
}

function redrawCrosshairs() {
  renderImages();
}

function drawCrosshair(canvas, plane) {
  if (!state.crosshair || state.mip) return;
  const ctx = canvas.getContext("2d");
  const dims = state.metadata.dimensions;
  let x;
  let y;
  if (plane === "axial") {
    x = state.coord.x;
    y = state.coord.y;
  } else if (plane === "sagittal") {
    x = state.coord.y;
    y = state.coord.z;
  } else {
    x = state.coord.x;
    y = state.coord.z;
  }
  x = clamp(x, 0, canvas.width - 1);
  y = clamp(y, 0, canvas.height - 1);
  ctx.save();
  ctx.strokeStyle = state.crosshairColor;
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.95;
  ctx.beginPath();
  ctx.moveTo(x + 0.5, 0);
  ctx.lineTo(x + 0.5, canvas.height);
  ctx.moveTo(0, y + 0.5);
  ctx.lineTo(canvas.width, y + 0.5);
  ctx.stroke();
  const scalePx = Math.max(12, Math.round(100 / state.metadata.spacing.x));
  ctx.strokeStyle = "#f5f8ff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(canvas.width - scalePx - 10, canvas.height - 10);
  ctx.lineTo(canvas.width - 10, canvas.height - 10);
  ctx.stroke();
  ctx.restore();
}

function handleCanvasPointer(plane, event) {
  state.focusedPlane = plane;
  for (const wrap of document.querySelectorAll(".viewport")) wrap.classList.remove("focused");
  document.getElementById(`${plane}-wrap`).classList.add("focused");
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const px = clamp(Math.round((event.clientX - rect.left) * canvas.width / rect.width), 0, canvas.width - 1);
  const py = clamp(Math.round((event.clientY - rect.top) * canvas.height / rect.height), 0, canvas.height - 1);
  const dims = state.metadata.dimensions;
  if (plane === "axial") {
    state.coord.x = clamp(px, 0, dims.x - 1);
    state.coord.y = clamp(py, 0, dims.y - 1);
  } else if (plane === "sagittal") {
    state.coord.y = clamp(px, 0, dims.y - 1);
    state.coord.z = clamp(py, 0, dims.z - 1);
  } else {
    state.coord.x = clamp(px, 0, dims.x - 1);
    state.coord.z = clamp(py, 0, dims.z - 1);
  }
  renderImages();
  updateStatus();
}

function handleWheel(plane, event) {
  event.preventDefault();
  if (event.ctrlKey || event.metaKey) {
    state.userScaled = true;
    setScale(state.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12));
    return;
  }
  stepPlane(plane, event.deltaY < 0 ? 1 : -1);
}

function stepPlane(plane, delta) {
  const axis = planeAxis[plane];
  const dims = state.metadata.dimensions;
  state.focusedPlane = plane;
  state.coord[axis] = clamp(state.coord[axis] + delta, 0, dims[axis] - 1);
  renderImages();
  updateStatus();
}

function setScale(scale) {
  state.scale = clamp(scale, 0.35, 6);
  document.getElementById("slice-grid").style.transform = `scale(${state.scale})`;
  updateStatus();
}

function fitScale() {
  const slices = document.getElementById("slices");
  const grid = document.getElementById("slice-grid");
  const rect = slices.getBoundingClientRect();
  const width = grid.offsetWidth || 1;
  const height = grid.offsetHeight || 1;
  const fit = Math.min((rect.width - 12) / width, (rect.height - 12) / height);
  return clamp(Math.min(1, fit), 0.18, 1);
}

function resetView() {
  const dims = state.metadata.dimensions;
  state.coord = {
    x: Math.floor(dims.x / 2),
    y: Math.floor(dims.y / 2),
    z: Math.floor(dims.z / 2)
  };
  state.brightness = 100;
  state.contrast = 100;
  state.opacity = 75;
  state.gains = {};
  state.mip = false;
  state.userScaled = false;
  document.getElementById("brightness").value = state.brightness;
  document.getElementById("contrast").value = state.contrast;
  document.getElementById("opacity").value = state.opacity;
  document.getElementById("mip-toggle").textContent = "Show as MIP";
  renderImages();
  renderLayerSettings();
  updateStatus();
}

function shareView() {
  const params = new URLSearchParams({
    x: String(state.coord.x),
    y: String(state.coord.y),
    z: String(state.coord.z),
    layers: activeIds().join(","),
    brightness: String(state.brightness),
    contrast: String(state.contrast),
    opacity: String(state.opacity),
    gains: gainParam(),
    mip: state.mip ? "1" : "0"
  });
  const url = `${window.location.origin}${window.location.pathname}?${params.toString()}`;
  navigator.clipboard.writeText(url).catch(() => {});
  history.replaceState(null, "", `?${params.toString()}`);
}

function updateStatus() {
  const mode = state.mip ? "MIP" : `focused: ${state.focusedPlane}`;
  const activeCount = activeIds().length;
  const cap = state.metadata.max_layers_per_view;
  const capText = activeCount > cap ? `; displaying first ${cap} of ${activeCount} selected` : "";
  document.getElementById("coord-status").textContent =
    `X: ${state.coord.x}, Y: ${state.coord.y}, Z: ${state.coord.z}`;
  document.getElementById("focused-status").textContent =
    `${mode}; zoom ${state.scale.toFixed(2)}x`;
  const labels = activeLabels();
  document.getElementById("layer-status").textContent =
    labels.length ? `Reference: fixed DAPI; Layers: ${labels.join(", ")}${capText}` : "Reference: fixed DAPI";
}

function showError(message) {
  const box = document.getElementById("error-box");
  if (!box) return;
  box.textContent = message;
  box.style.display = "block";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[ch]));
}

async function boot() {
  const response = await fetch("/api/metadata");
  state.metadata = await response.json();
  const dims = state.metadata.dimensions;
  state.coord = {
    x: clamp(Number(qs("x", Math.floor(dims.x / 2))), 0, dims.x - 1),
    y: clamp(Number(qs("y", Math.floor(dims.y / 2))), 0, dims.y - 1),
    z: clamp(Number(qs("z", Math.floor(dims.z / 2))), 0, dims.z - 1)
  };
  state.brightness = Number(qs("brightness", state.brightness));
  state.contrast = Number(qs("contrast", state.contrast));
  state.opacity = Number(qs("opacity", state.opacity));
  state.gains = parseGainParam(qs("gains", ""));
  state.mip = qs("mip", "0") === "1";
  const params = new URLSearchParams(window.location.search);
  const hasLayerParam = params.has("layers");
  const requested = qs("layers", "");
  const initial = hasLayerParam ? requested.split(",") : state.metadata.default_layers;
  state.active = new Set(initial.filter(id => state.metadata.layers.some(layer => layer.id === id)));
  if (!state.active.size && !hasLayerParam && state.metadata.layers.length) state.active.add(state.metadata.layers[0].id);
  state.selectedLayer = state.active.values().next().value ?? (state.metadata.layers[0]?.id ?? null);

  document.getElementById("app").innerHTML = appHtml();
  bindControls();
  renderRunMeta();
  renderLayerList();
  setScale(fitScale());
  document.getElementById("mip-toggle").textContent = state.mip ? "Show Slices" : "Show as MIP";
  renderImages();
  updateStatus();
}

boot().catch(error => {
  document.getElementById("app").textContent = `Viewer failed to start: ${error}`;
});
</script>
</body>
</html>
"""


@dataclass(frozen=True)
class Layer:
    id: str
    marker: str
    wavelength: str
    subject: str
    registered_subject: str
    output: Path
    color: str
    note: str

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "marker": self.marker,
            "wavelength": self.wavelength,
            "subject": self.subject,
            "registered_subject": self.registered_subject,
            "output": str(self.output),
            "color": self.color,
            "note": self.note,
        }


@dataclass(frozen=True)
class ClipStats:
    minimum: float
    maximum: float


@dataclass(frozen=True)
class CachedVolume:
    data: np.ndarray
    clip: ClipStats


@dataclass(frozen=True)
class CompositeLayer:
    volume: np.ndarray
    color: str
    clip: ClipStats
    gain: float = 1.0


class VolumeStore:
    def __init__(
        self,
        layers: list[Layer],
        reference_path: Path,
        max_volumes: int,
    ) -> None:
        self._layers = {layer.id: layer for layer in layers}
        self._reference_path = reference_path
        self._reference: np.ndarray | None = None
        self._max_volumes = max(1, max_volumes)
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, CachedVolume] = OrderedDict()

    def get_reference(self) -> np.ndarray:
        with self._lock:
            if self._reference is None:
                self._reference = self._read_volume(self._reference_path)
            return self._reference

    def get(self, layer_id: str) -> CachedVolume:
        with self._lock:
            cached = self._cache.get(layer_id)
            if cached is not None:
                self._cache.move_to_end(layer_id)
                return cached
            layer = self._layers[layer_id]
            data = self._read_volume(layer.output)
            cached = CachedVolume(data=data, clip=compute_clip_stats(data))
            self._cache[layer_id] = cached
            self._cache.move_to_end(layer_id)
            while len(self._cache) > self._max_volumes:
                self._cache.popitem(last=False)
            return cached

    @staticmethod
    def _read_volume(path: Path) -> np.ndarray:
        data, _header = nrrd.read(str(path), index_order="C")
        if data.ndim != 3:
            raise ValueError(f"Expected 3-D NRRD for {path}, got {data.shape}")
        return orient_volume_for_display(np.asarray(data, dtype=np.float32))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a Danionella-style orthogonal slice viewer for registered NRRD channels."
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--reference-path", type=Path, default=DEFAULT_REFERENCE_PATH)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-cached-volumes", type=int, default=3)
    parser.add_argument("--max-layers-per-view", type=int, default=len(MARKER_PALETTE))
    return parser.parse_args()


def load_layers(run_dir: Path) -> list[Layer]:
    manifest = run_dir / MANIFEST_NAME
    if not manifest.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest}")
    colors = marker_colors(manifest)
    layers: list[Layer] = []
    with manifest.open(newline="") as handle:
        for row_index, row in enumerate(csv.DictReader(handle)):
            if row.get("status") != "OK":
                continue
            output = Path(row["output"])
            if not output.exists():
                continue
            marker = row["marker"]
            layer_id = stable_layer_id(row_index, row)
            layers.append(
                Layer(
                    id=layer_id,
                    marker=marker,
                    wavelength=row["wavelength"],
                    subject=row["subject"],
                    registered_subject=row["registered_subject"],
                    output=output,
                    color=colors[marker],
                    note=row.get("note", ""),
                )
            )
    if not layers:
        raise ValueError(f"No usable OK rows with existing outputs in {manifest}")
    return layers


def marker_colors(manifest: Path) -> dict[str, str]:
    markers: list[str] = []
    with manifest.open(newline="") as handle:
        for row in csv.DictReader(handle):
            marker = row.get("marker")
            if row.get("status") == "OK" and marker and marker not in markers:
                markers.append(marker)
    return assign_marker_colors(markers)


def assign_marker_colors(markers: list[str]) -> dict[str, str]:
    colors: dict[str, str] = {}
    for index, marker in enumerate(sorted(markers)):
        colors[marker] = MARKER_PALETTE[index % len(MARKER_PALETTE)]
    return colors


def orient_volume_for_display(volume: np.ndarray) -> np.ndarray:
    return np.flip(volume, axis=0).copy()


def stable_layer_id(index: int, row: dict[str, str]) -> str:
    token = f"{row['registered_subject']}__{row['marker']}__{row['wavelength']}"
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", token).strip("_")
    return f"{index:03d}_{token}"


def read_volume_metadata(first_output: Path) -> tuple[dict[str, int], dict[str, float]]:
    header = nrrd.read_header(str(first_output))
    sizes = [int(value) for value in header["sizes"]]
    if len(sizes) != 3:
        raise ValueError(f"Expected 3-D NRRD sizes for {first_output}, got {sizes}")
    spacing = {"x": 1.0, "y": 1.0, "z": 1.0}
    directions = header.get("space directions")
    if directions is not None:
        for axis, direction in zip(["x", "y", "z"], directions, strict=False):
            values = np.asarray(direction, dtype=float)
            spacing[axis] = float(np.linalg.norm(values)) or 1.0
    return {"x": sizes[0], "y": sizes[1], "z": sizes[2]}, spacing


def default_layers(layers: list[Layer]) -> list[str]:
    agrp = [layer.id for layer in layers if layer.marker == "agrp"]
    pomca = [layer.id for layer in layers if layer.marker == "pomca"]
    if agrp and pomca:
        return [agrp[0], pomca[0]]
    return [layer.id for layer in layers[: min(2, len(layers))]]


def plane_slice(volume: np.ndarray, plane: str, index: int | str) -> np.ndarray:
    z_size, y_size, x_size = volume.shape
    if index == "mip":
        if plane == "axial":
            return np.max(volume, axis=0)
        if plane == "sagittal":
            return np.max(volume, axis=2)
        if plane == "coronal":
            return np.max(volume, axis=1)
    if plane == "axial":
        return volume[clamp_int(int(index), 0, z_size - 1), :, :]
    if plane == "sagittal":
        return volume[:, :, clamp_int(int(index), 0, x_size - 1)]
    if plane == "coronal":
        return volume[:, clamp_int(int(index), 0, y_size - 1), :]
    raise ValueError(f"Unknown plane: {plane}")


def compute_clip_stats(
    volume: np.ndarray,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.5,
) -> ClipStats:
    finite = np.asarray(volume, dtype=np.float32)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return ClipStats(0.0, 1.0)
    minimum, maximum = np.percentile(finite, [lower_percentile, upper_percentile])
    if maximum <= minimum:
        maximum = minimum + 1.0
    return ClipStats(float(minimum), float(maximum))


def normalize_plane(
    plane: np.ndarray,
    brightness: float,
    contrast: float,
    clip_min: float = 0.0,
    clip_max: float = 255.0,
) -> np.ndarray:
    if clip_max <= clip_min:
        clip_max = clip_min + 1.0
    values = (np.asarray(plane, dtype=np.float32) - clip_min) / (clip_max - clip_min)
    values = np.clip(values, 0.0, 1.0)
    values = (values - 0.5) * (contrast / 100.0) + 0.5
    values = values * (brightness / 100.0)
    return np.clip(values, 0.0, 1.0)


def composite_rgb(
    volumes: list[CompositeLayer],
    plane: str,
    index: int | str,
    brightness: float,
    contrast: float,
    opacity: float,
    reference_volume: np.ndarray | None = None,
    reference_opacity: float = 0.45,
) -> np.ndarray:
    first_volume = reference_volume if reference_volume is not None else volumes[0].volume
    first = plane_slice(first_volume, plane, index)
    if reference_volume is not None:
        reference = normalize_plane(plane_slice(reference_volume, plane, index), 100.0, 100.0)
        rgb = np.repeat((reference * reference_opacity)[..., None], 3, axis=2)
    else:
        rgb = np.zeros((first.shape[0], first.shape[1], 3), dtype=np.float32)
    alpha = max(0.0, min(1.0, opacity))
    for layer in volumes:
        norm = normalize_plane(
            plane_slice(layer.volume, plane, index),
            brightness,
            contrast,
            layer.clip.minimum,
            layer.clip.maximum,
        )
        norm = np.clip(norm * layer.gain, 0.0, 1.0)
        color_rgb = np.array(hex_to_rgb(layer.color), dtype=np.float32) / 255.0
        contribution = norm[..., None] * color_rgb * alpha
        rgb = 1.0 - (1.0 - rgb) * (1.0 - contribution)
    return np.asarray(np.clip(rgb * 255.0, 0, 255), dtype=np.uint8)


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.strip().lstrip("#")
    if len(color) != 6:
        return (255, 255, 255)
    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))


def encode_png_rgb(image: np.ndarray) -> bytes:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Expected HxWx3 RGB image, got {image.shape}")
    image = np.ascontiguousarray(image, dtype=np.uint8)
    height, width, _channels = image.shape
    raw = b"".join(b"\x00" + image[row].tobytes() for row in range(height))
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
    png.extend(png_chunk(b"IDAT", zlib.compress(raw, level=1)))
    png.extend(png_chunk(b"IEND", b""))
    return bytes(png)


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(payload, crc)
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", crc & 0xFFFFFFFF)
    )


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def parse_gain_overrides(raw_value: str) -> dict[str, float]:
    gains: dict[str, float] = {}
    for item in raw_value.split(","):
        if not item or ":" not in item:
            continue
        layer_id, raw_gain = item.rsplit(":", 1)
        try:
            gain = float(raw_gain)
        except ValueError:
            continue
        gains[layer_id] = max(0.0, min(5.0, gain))
    return gains


class ViewerHandler(BaseHTTPRequestHandler):
    layers: list[Layer]
    layer_by_id: dict[str, Layer]
    store: VolumeStore
    run_dir: Path
    reference_path: Path
    dimensions: dict[str, int]
    spacing: dict[str, float]
    max_layers_per_view: int

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self.send_bytes(PAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/api/metadata":
                self.send_json(self.metadata_payload())
            elif parsed.path == "/api/composite":
                self.handle_composite(parse_qs(parsed.query))
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "run_name": self.run_dir.name,
            "run_dir": str(self.run_dir),
            "layer_count": len(self.layers),
            "subject_count": len({layer.registered_subject for layer in self.layers}),
            "dimensions": self.dimensions,
            "spacing": self.spacing,
            "spacing_x": self.spacing["x"],
            "max_layers_per_view": self.max_layers_per_view,
            "reference": {
                "name": self.reference_path.name,
                "path": str(self.reference_path),
            },
            "default_layers": default_layers(self.layers),
            "layers": [layer.to_json() for layer in self.layers],
        }

    def handle_composite(self, query: dict[str, list[str]]) -> None:
        plane = query_value(query, "plane", "axial")
        raw_index = query_value(query, "index", "0")
        index: int | str = "mip" if query_value(query, "mip", "0") == "1" or raw_index == "mip" else int(raw_index)
        brightness = float(query_value(query, "brightness", "100"))
        contrast = float(query_value(query, "contrast", "100"))
        opacity = float(query_value(query, "opacity", "0.75"))
        gains = parse_gain_overrides(query_value(query, "gains", ""))
        layer_ids = [
            layer_id
            for layer_id in query_value(query, "layers", "").split(",")
            if layer_id in self.layer_by_id
        ]
        layer_ids = layer_ids[: self.max_layers_per_view]
        volumes = []
        for layer_id in layer_ids:
            cached = self.store.get(layer_id)
            layer = self.layer_by_id[layer_id]
            volumes.append(
                CompositeLayer(
                    volume=cached.data,
                    color=layer.color,
                    clip=cached.clip,
                    gain=gains.get(layer_id, 1.0),
                )
            )
        image = composite_rgb(
            volumes,
            plane,
            index,
            brightness,
            contrast,
            opacity,
            reference_volume=self.store.get_reference(),
        )
        self.send_bytes(encode_png_rgb(image), "image/png", cache=True)

    def send_json(self, payload: dict[str, Any]) -> None:
        self.send_bytes(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def send_bytes(self, payload: bytes, content_type: str, cache: bool = False) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if cache:
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def make_handler(
    run_dir: Path,
    reference_path: Path,
    layers: list[Layer],
    store: VolumeStore,
    max_layers_per_view: int,
) -> type[ViewerHandler]:
    dimensions, spacing = read_volume_metadata(reference_path)
    layer_by_id = {layer.id: layer for layer in layers}

    class ConfiguredViewerHandler(ViewerHandler):
        pass

    ConfiguredViewerHandler.run_dir = run_dir
    ConfiguredViewerHandler.reference_path = reference_path
    ConfiguredViewerHandler.layers = layers
    ConfiguredViewerHandler.layer_by_id = layer_by_id
    ConfiguredViewerHandler.store = store
    ConfiguredViewerHandler.dimensions = dimensions
    ConfiguredViewerHandler.spacing = spacing
    ConfiguredViewerHandler.max_layers_per_view = max_layers_per_view
    return ConfiguredViewerHandler


def main() -> None:
    args = parse_args()
    if not args.reference_path.exists():
        raise FileNotFoundError(f"Missing reference DAPI NRRD: {args.reference_path}")
    layers = load_layers(args.run_dir)
    store = VolumeStore(layers, args.reference_path, args.max_cached_volumes)
    handler = make_handler(
        args.run_dir,
        args.reference_path,
        layers,
        store,
        args.max_layers_per_view,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving registered atlas viewer at {url}")
    print(f"Run directory: {args.run_dir}")
    print(f"Reference DAPI: {args.reference_path}")
    print(f"Channels: {len(layers)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
