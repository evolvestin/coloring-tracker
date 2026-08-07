<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  file: { type: Object, required: true },
  title: { type: String, default: 'Редактор изображения' },
})
const emit = defineEmits(['cancel', 'save'])

const stage = ref(null)
const canvas = ref(null)
const image = new Image()
const imageSrc = URL.createObjectURL(props.file)
const loaded = ref(false)
const rotation = ref(0)
const crop = ref({ x: 0, y: 0, width: 0, height: 0 })
const display = ref({ left: 0, top: 0, width: 0, height: 0, scale: 1 })
const stageSize = ref({ width: 0, height: 0 })
const saving = ref(false)
const drag = ref(null)
let resizeObserver
let interactiveAfter = 0

function rotatedSize() {
  const quarterTurn = rotation.value % 180 !== 0
  return quarterTurn
    ? { width: image.naturalHeight, height: image.naturalWidth }
    : { width: image.naturalWidth, height: image.naturalHeight }
}

function resetCrop() {
  const size = rotatedSize()
  const margin = 0.06
  crop.value = {
    x: size.width * margin,
    y: size.height * margin,
    width: size.width * (1 - margin * 2),
    height: size.height * (1 - margin * 2),
  }
}

function drawPreview() {
  if (!loaded.value || !stage.value || !canvas.value) return
  const size = rotatedSize()
  const bounds = stage.value.getBoundingClientRect()
  stageSize.value = { width: bounds.width, height: bounds.height }
  const scale = Math.min((bounds.width - 24) / size.width, (bounds.height - 24) / size.height)
  const width = size.width * scale
  const height = size.height * scale
  display.value = {
    left: (bounds.width - width) / 2,
    top: (bounds.height - height) / 2,
    width,
    height,
    scale,
  }
  const ratio = window.devicePixelRatio || 1
  canvas.value.width = Math.max(1, Math.round(width * ratio))
  canvas.value.height = Math.max(1, Math.round(height * ratio))
  const context = canvas.value.getContext('2d')
  context.setTransform(ratio * scale, 0, 0, ratio * scale, canvas.value.width / 2, canvas.value.height / 2)
  context.clearRect(-size.width, -size.height, size.width * 2, size.height * 2)
  context.rotate((rotation.value * Math.PI) / 180)
  context.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2)
}

function cropStyle() {
  const d = display.value
  const c = crop.value
  return {
    left: `${d.left + c.x * d.scale}px`,
    top: `${d.top + c.y * d.scale}px`,
    width: `${c.width * d.scale}px`,
    height: `${c.height * d.scale}px`,
  }
}

function clamp(value, min, max) { return Math.min(max, Math.max(min, value)) }

function imagePoint(event) {
  const rect = stage.value.getBoundingClientRect()
  const d = display.value
  return {
    x: clamp((event.clientX - rect.left - d.left) / d.scale, 0, rotatedSize().width),
    y: clamp((event.clientY - rect.top - d.top) / d.scale, 0, rotatedSize().height),
  }
}

function beginCrop(event) {
  if (
    !loaded.value
    || Date.now() < interactiveAfter
    || event.pointerType === 'mouse' && event.button !== 0
  ) return
  const point = imagePoint(event)
  const handle = event.target.closest?.('[data-handle]')?.dataset.handle
  const c = crop.value
  const outside = point.x < c.x || point.x > c.x + c.width || point.y < c.y || point.y > c.y + c.height
  if (!handle && outside) {
    crop.value = { x: point.x, y: point.y, width: 1, height: 1 }
  }
  drag.value = {
    mode: handle || (outside ? 'new' : 'move'),
    start: point,
    initial: { ...crop.value },
  }
  stage.value.setPointerCapture?.(event.pointerId)
}

function updateCrop(event) {
  if (!drag.value) return
  const point = imagePoint(event)
  const start = drag.value.start
  const initial = drag.value.initial
  const size = rotatedSize()
  if (drag.value.mode === 'move') {
    const dx = point.x - start.x
    const dy = point.y - start.y
    crop.value = {
      ...initial,
      x: clamp(initial.x + dx, 0, size.width - initial.width),
      y: clamp(initial.y + dy, 0, size.height - initial.height),
    }
  } else if (drag.value.mode === 'new') {
    const x = Math.min(start.x, point.x), y = Math.min(start.y, point.y)
    crop.value = { x, y, width: Math.max(20, Math.abs(point.x - start.x)), height: Math.max(20, Math.abs(point.y - start.y)) }
    crop.value.width = Math.min(crop.value.width, size.width - x)
    crop.value.height = Math.min(crop.value.height, size.height - y)
  } else {
    let left = initial.x, top = initial.y
    let right = initial.x + initial.width, bottom = initial.y + initial.height
    if (drag.value.mode.includes('w')) left = clamp(point.x, 0, right - 20)
    if (drag.value.mode.includes('e')) right = clamp(point.x, left + 20, size.width)
    if (drag.value.mode.includes('n')) top = clamp(point.y, 0, bottom - 20)
    if (drag.value.mode.includes('s')) bottom = clamp(point.y, top + 20, size.height)
    crop.value = { x: left, y: top, width: right - left, height: bottom - top }
  }
  drawPreview()
}

function endCrop() { drag.value = null }

function rotate() {
  rotation.value = (rotation.value + 90) % 360
  resetCrop()
  nextTick(drawPreview)
}

function reset() { rotation.value = 0; resetCrop(); nextTick(drawPreview) }

function save() {
  if (saving.value || !loaded.value) return
  saving.value = true
  const size = rotatedSize()
  const rotated = document.createElement('canvas')
  rotated.width = size.width
  rotated.height = size.height
  const rotatedContext = rotated.getContext('2d')
  rotatedContext.translate(size.width / 2, size.height / 2)
  rotatedContext.rotate((rotation.value * Math.PI) / 180)
  rotatedContext.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2)
  const output = document.createElement('canvas')
  output.width = Math.max(1, Math.round(crop.value.width))
  output.height = Math.max(1, Math.round(crop.value.height))
  output.getContext('2d').drawImage(
    rotated,
    Math.round(crop.value.x), Math.round(crop.value.y), output.width, output.height,
    0, 0, output.width, output.height,
  )
  const mime = props.file.type === 'image/png' ? 'image/png' : 'image/jpeg'
  output.toBlob((blob) => {
    saving.value = false
    if (blob) emit('save', blob)
  }, mime, 0.92)
}

function onImageLoad() {
  loaded.value = true
  resetCrop()
  nextTick(drawPreview)
}

image.onload = onImageLoad
image.src = imageSrc
onMounted(() => {
  interactiveAfter = Date.now() + 350
  resizeObserver = new ResizeObserver(drawPreview)
  resizeObserver.observe(stage.value)
})
watch(rotation, drawPreview)
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  URL.revokeObjectURL(imageSrc)
})
</script>

<template>
  <div class="modal-backdrop image-editor-backdrop" @click.self="emit('cancel')">
    <section class="image-editor-modal" role="dialog" aria-modal="true" :aria-label="title">
      <header class="image-editor-header">
        <div><p class="eyebrow">ПОДГОТОВКА ФОТО</p><h2>{{ title }}</h2></div>
        <button class="modal-close" aria-label="Закрыть редактор" @click="emit('cancel')">×</button>
      </header>
      <p class="image-editor-hint">Выделите нужную область и поверните снимок по часовой стрелке. Результат сохранится сразу.</p>
      <div ref="stage" class="image-editor-stage" @pointerdown="beginCrop" @pointermove="updateCrop" @pointerup="endCrop" @pointercancel="endCrop">
        <canvas ref="canvas" class="image-editor-canvas" :style="{ left: `${display.left}px`, top: `${display.top}px`, width: `${display.width}px`, height: `${display.height}px` }"></canvas>
        <div v-if="loaded" class="crop-selection" :style="cropStyle()" @pointerdown.stop="beginCrop">
          <i v-for="handle in ['nw', 'ne', 'sw', 'se']" :key="handle" :data-handle="handle" :class="['crop-handle', `crop-handle-${handle}`]"></i>
        </div>
      </div>
      <div class="image-editor-actions">
        <button class="secondary" type="button" @click="rotate">↻ Повернуть</button>
        <button class="secondary" type="button" @click="reset">Сбросить</button>
        <button class="primary" type="button" :disabled="!loaded || saving" @click="save">{{ saving ? 'Готовим…' : 'Готово' }}</button>
      </div>
    </section>
  </div>
</template>
