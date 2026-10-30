<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '../api'

const emit = defineEmits(['notify'])

const file = ref(null)
const chunkSize = ref(1024 * 1024)
const slowDemo = ref(true)
const fileId = ref('')
const uploadState = ref('idle')
const chunkStatuses = ref([])
const completedBytes = ref(0)
const currentLoaded = ref(0)
const paused = ref(false)
const logs = ref([])

const downloadName = ref('')
const downloadState = ref('idle')
const downloadedBytes = ref(0)
const downloadTotal = ref(0)
const downloadChunks = ref([])
const downloadBlobUrl = ref('')
const downloadController = ref(null)
const downloadPaused = ref(false)

const batchFiles = ref([])
const batchState = ref('idle')
const batchProgress = ref(0)
const batchResult = ref(null)

const totalChunks = computed(() =>
  file.value ? Math.ceil(file.value.size / chunkSize.value) : 0,
)
const uploadProgress = computed(() => {
  if (!file.value?.size) return 0
  const loaded = completedBytes.value + currentLoaded.value
  return Math.min(100, Math.round((loaded / file.value.size) * 100))
})
const downloadProgress = computed(() => {
  if (downloadState.value === 'done' && downloadTotal.value) return 100
  return downloadTotal.value
    ? Math.min(100, Math.round((downloadedBytes.value / downloadTotal.value) * 100))
    : 0
})
const uploadActionText = computed(() => {
  if (uploadState.value === 'uploading') return '暂停'
  if (uploadState.value === 'paused') return '继续上传'
  if (uploadState.value === 'merging') return '合并中…'
  if (uploadState.value === 'done') return '重新上传'
  return '开始上传'
})
const uploadActionDisabled = computed(
  () => !file.value || uploadState.value === 'merging',
)
const downloadActionText = computed(() => {
  if (downloadState.value === 'downloading') return '暂停下载'
  if (downloadState.value === 'paused') return '继续下载'
  if (downloadState.value === 'done') return '重新下载'
  return '开始下载'
})
const canSave = computed(() => downloadState.value === 'done' && downloadBlobUrl.value)
const batchTotalSize = computed(() =>
  batchFiles.value.reduce((sum, item) => sum + item.size, 0),
)
const batchDoneCount = computed(
  () => batchFiles.value.filter((item) => item.status === 'done').length,
)
const batchActionText = computed(() => {
  if (batchState.value === 'uploading') return '上传中…'
  if (batchState.value === 'done') return '重新批量上传'
  return '开始批量上传'
})
const doneChunks = computed(() => chunkStatuses.value.filter((s) => s === 'done').length)

function batchStatusLabel(status) {
  return { pending: '待上传', uploading: '上传中', done: '完成', error: '失败' }[status] || status
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

function log(message, type = 'info') {
  logs.value.unshift({
    time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    message,
    type,
  })
  logs.value = logs.value.slice(0, 8)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function makeUuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `upload-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function applyFile(selected) {
  if (!selected) return
  if (uploadState.value === 'uploading') paused.value = true
  file.value = selected
  const fingerprint = `upload:${selected.name}:${selected.size}:${selected.lastModified}`
  let id = localStorage.getItem(fingerprint)
  if (!id) {
    id = makeUuid()
    localStorage.setItem(fingerprint, id)
  }
  fileId.value = id
  chunkStatuses.value = Array(Math.ceil(selected.size / chunkSize.value)).fill('pending')
  completedBytes.value = 0
  currentLoaded.value = 0
  uploadState.value = 'idle'
  paused.value = false
  downloadName.value = ''
  resetDownload()
  log(`选择文件：${selected.name}（${formatBytes(selected.size)}），切 ${chunkStatuses.value.length} 片`)
}

function onFileChange(event) {
  applyFile(event.target.files?.[0])
  event.target.value = ''
}

function useDemoFile() {
  const size = 20 * 1024 * 1024
  const blob = new Blob([new Uint8Array(size)])
  const demo = new File([blob], 'demo-20mb.bin', {
    type: 'application/octet-stream',
    lastModified: 1700000000000,
  })
  applyFile(demo)
  emit('notify', '已生成 20MB 演示文件，点击「开始上传」即可')
}

function changeChunkSize() {
  if (file.value) applyFile(file.value)
}

function chunkLength(index) {
  return Math.min(chunkSize.value, file.value.size - index * chunkSize.value)
}

function uploadChunk(index, blob, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/upload/chunk')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
        return
      }
      let message = `分片上传失败（HTTP ${xhr.status}）`
      try {
        message = JSON.parse(xhr.responseText).message || message
      } catch {
        /* ignore */
      }
      reject(new Error(message))
    }
    xhr.onerror = () => reject(new Error('网络错误，分片上传失败'))

    const form = new FormData()
    form.append('file_id', fileId.value)
    form.append('chunk_index', String(index))
    form.append('file', blob, `chunk-${index}`)
    xhr.send(form)
  })
}

async function handleUploadAction() {
  if (uploadState.value === 'uploading') {
    pauseUpload()
    return
  }
  if (uploadState.value === 'paused') {
    await resumeUpload()
    return
  }
  if (uploadState.value === 'done') {
    resetUpload()
  }
  await startUpload()
}

async function startUpload() {
  if (!file.value || !fileId.value) {
    emit('notify', '先选择一个文件，或点击「使用 20MB 演示文件」', 'error')
    return
  }
  chunkStatuses.value = Array(totalChunks.value).fill('pending')
  completedBytes.value = 0
  currentLoaded.value = 0
  paused.value = false
  uploadState.value = 'uploading'
  log('开始上传：先询问服务端已收到哪些分片')
  await uploadMissingChunks()
}

function pauseUpload() {
  paused.value = true
  log('已请求暂停：当前分片完成后停止，可随时继续', 'warn')
}

async function resumeUpload() {
  paused.value = false
  uploadState.value = 'uploading'
  log('继续上传：服务端已保存的分片不会重传', 'info')
  await uploadMissingChunks()
}

async function uploadMissingChunks() {
  try {
    const status = await api.uploadStatus(fileId.value, totalChunks.value)
    const uploaded = new Set(status.uploaded)
    let bytes = 0
    for (let index = 0; index < totalChunks.value; index += 1) {
      if (uploaded.has(index)) {
        chunkStatuses.value[index] = 'done'
        bytes += chunkLength(index)
      } else {
        chunkStatuses.value[index] = 'pending'
      }
    }
    completedBytes.value = bytes
    currentLoaded.value = 0
    log(
      `服务端已有 ${status.uploaded.length} 片，缺 ${status.missing.length} 片；只补缺失部分`,
      'info',
    )

    for (let index = 0; index < totalChunks.value; index += 1) {
      if (paused.value) {
        uploadState.value = 'paused'
        log('已暂停：分片留在服务端，继续时从这里接着传', 'warn')
        return
      }
      if (chunkStatuses.value[index] === 'done') continue

      chunkStatuses.value[index] = 'uploading'
      const start = index * chunkSize.value
      const end = Math.min(file.value.size, start + chunkSize.value)
      const blob = file.value.slice(start, end)
      currentLoaded.value = 0

      await uploadChunk(index, blob, (loaded) => {
        currentLoaded.value = loaded
      })

      chunkStatuses.value[index] = 'done'
      completedBytes.value += blob.size
      currentLoaded.value = 0
      log(`分片 ${index + 1}/${totalChunks.value} 完成（${formatBytes(blob.size)}）`)

      if (slowDemo.value) await sleep(250)
    }

    if (paused.value) {
      uploadState.value = 'paused'
      return
    }

    uploadState.value = 'merging'
    log('全部分片到达，请求服务端按 0..N 顺序合并…')
    const result = await api.completeUpload(fileId.value, totalChunks.value, file.value.name)
    downloadName.value = result.filename
    downloadTotal.value = result.size
    downloadState.value = 'idle'
    downloadChunks.value = []
    if (downloadBlobUrl.value) URL.revokeObjectURL(downloadBlobUrl.value)
    downloadBlobUrl.value = ''
    uploadedBytesReset()
    uploadState.value = 'done'
    localStorage.removeItem(`upload:${file.value.name}:${file.value.size}:${file.value.lastModified}`)
    log(`合并完成：${result.filename}（${formatBytes(result.size)}）`, 'success')
    emit('notify', '上传完成，右侧可以测试下载断点续传')
  } catch (error) {
    uploadState.value = 'error'
    log(error.message, 'error')
    emit('notify', error.message, 'error')
  }
}

function uploadedBytesReset() {
  completedBytes.value = file.value?.size || 0
  currentLoaded.value = 0
}

function resetUpload() {
  paused.value = true
  if (file.value) {
    localStorage.removeItem(`upload:${file.value.name}:${file.value.size}:${file.value.lastModified}`)
    fileId.value = makeUuid()
  }
  uploadState.value = 'idle'
  chunkStatuses.value = file.value
    ? Array(Math.ceil(file.value.size / chunkSize.value)).fill('pending')
    : []
  completedBytes.value = 0
  currentLoaded.value = 0
  log('已重置上传进度并生成新的 file_id；旧临时分片不会再被引用')
}

async function handleDownloadAction() {
  if (downloadState.value === 'downloading') {
    pauseDownload()
    return
  }
  if (downloadState.value === 'paused') {
    await startDownload(true)
    return
  }
  if (downloadState.value === 'done') {
    resetDownload()
  }
  await startDownload()
}

async function startDownload(isResume = false) {
  if (!downloadName.value) {
    emit('notify', '先上传文件，或在下载框里填入服务器上已有的文件名', 'error')
    return
  }
  if (!isResume) {
    downloadedBytes.value = 0
    downloadChunks.value = []
    downloadTotal.value = 0
    if (downloadBlobUrl.value) URL.revokeObjectURL(downloadBlobUrl.value)
    downloadBlobUrl.value = ''
  }
  downloadPaused.value = false
  downloadState.value = 'downloading'
  const controller = new AbortController()
  downloadController.value = controller
  const headers = {}
  if (downloadedBytes.value > 0) {
    headers.Range = `bytes=${downloadedBytes.value}-`
    log(`继续下载：发送 Range: bytes=${downloadedBytes.value}-`, 'info')
  } else {
    log('开始下载：服务端支持 Range，暂停后可从已下载字节继续')
  }

  try {
    const response = await fetch(api.uploadDownloadUrl(downloadName.value), {
      headers,
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`)

    // 如果代理/服务器忽略了 Range 并返回完整 200，不能把完整文件追加到已有分片后面
    if (downloadedBytes.value > 0 && response.status === 200) {
      downloadedBytes.value = 0
      downloadChunks.value = []
      downloadTotal.value = 0
      log('服务端未返回 206，说明 Range 未被接受；已改为从 0 完整下载', 'warn')
    }

    const contentRange = response.headers.get('content-range')
    const contentLength = response.headers.get('content-length')
    if (contentRange) {
      const match = contentRange.match(/\/(\d+)$/)
      if (match) downloadTotal.value = Number(match[1])
    } else if (contentLength) {
      downloadTotal.value = downloadedBytes.value + Number(contentLength)
    }

    const reader = response.body.getReader()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      downloadChunks.value.push(value)
      downloadedBytes.value += value.length
      if (slowDemo.value) await sleep(20)
    }

    downloadState.value = 'done'
    const blob = new Blob(downloadChunks.value, { type: 'application/octet-stream' })
    downloadBlobUrl.value = URL.createObjectURL(blob)
    log(`下载完成：${formatBytes(downloadedBytes.value)}`, 'success')
    emit('notify', '下载完成，点击「保存文件」即可')
  } catch (error) {
    if (error.name === 'AbortError' || downloadPaused.value) {
      downloadState.value = 'paused'
      log(
        `下载已暂停：已收到 ${formatBytes(downloadedBytes.value)}，继续时从该字节发 Range`,
        'warn',
      )
      return
    }
    downloadState.value = 'error'
    log(error.message, 'error')
    emit('notify', error.message, 'error')
  }
}

function pauseDownload() {
  downloadPaused.value = true
  downloadController.value?.abort()
}

function resetDownload() {
  downloadController.value?.abort()
  downloadPaused.value = false
  downloadState.value = 'idle'
  downloadedBytes.value = 0
  downloadTotal.value = 0
  downloadChunks.value = []
  if (downloadBlobUrl.value) URL.revokeObjectURL(downloadBlobUrl.value)
  downloadBlobUrl.value = ''
}

function onBatchChange(event) {
  const list = Array.from(event.target.files || [])
  batchFiles.value = list.map((file) => ({
    file,
    name: file.name,
    size: file.size,
    status: 'pending',
  }))
  batchState.value = 'idle'
  batchProgress.value = 0
  batchResult.value = null
  event.target.value = ''
  log(`选择了 ${list.length} 个小文件，共 ${formatBytes(batchTotalSize.value)}`)
}

function useDemoBatch() {
  const files = []
  for (let index = 1; index <= 5; index += 1) {
    const size = 180 * 1024 + index * 1024
    const name = `small-demo-${index}.txt`
    const blob = new Blob([new Uint8Array(size)])
    files.push({
      file: new File([blob], name, {
        type: 'text/plain',
        lastModified: 1700000000000 + index,
      }),
      name,
      size,
      status: 'pending',
    })
  }
  batchFiles.value = files
  batchState.value = 'idle'
  batchProgress.value = 0
  batchResult.value = null
  log('已生成 5 个约 180KB 的小文件，准备一次请求批量上传')
  emit('notify', '已生成 5 个小文件，点击「开始批量上传」')
}

function uploadBatch() {
  if (!batchFiles.value.length) {
    emit('notify', '先选择多个小文件，或点击「使用 5 个小文件演示」', 'error')
    return
  }
  batchState.value = 'uploading'
  batchProgress.value = 0
  batchResult.value = null
  batchFiles.value.forEach((item) => {
    item.status = 'uploading'
    item.server = null
  })

  const form = new FormData()
  batchFiles.value.forEach((item) => form.append('files', item.file, item.name))

  const xhr = new XMLHttpRequest()
  xhr.open('POST', '/api/upload/batch')
  xhr.upload.onprogress = (event) => {
    if (event.lengthComputable) {
      batchProgress.value = Math.round((event.loaded / event.total) * 100)
    }
  }
  xhr.onload = () => {
    try {
      const payload = JSON.parse(xhr.responseText)
      if (xhr.status < 200 || xhr.status >= 300 || payload.code !== 0) {
        throw new Error(payload.message || `批量上传失败（HTTP ${xhr.status}）`)
      }
      batchResult.value = payload.data
      batchFiles.value.forEach((item, index) => {
        item.status = 'done'
        item.server = payload.data.files[index] || null
      })
      batchState.value = 'done'
      batchProgress.value = 100
      log(
        `批量上传完成：${payload.data.count} 个文件，共 ${formatBytes(payload.data.total_size)}`,
        'success',
      )
      emit('notify', `批量上传完成：${payload.data.count} 个小文件`)
    } catch (error) {
      batchState.value = 'error'
      batchFiles.value.forEach((item) => {
        item.status = 'error'
      })
      log(error.message, 'error')
      emit('notify', error.message, 'error')
    }
  }
  xhr.onerror = () => {
    batchState.value = 'error'
    batchFiles.value.forEach((item) => {
      item.status = 'error'
    })
    log('网络错误，批量上传失败', 'error')
    emit('notify', '网络错误，批量上传失败', 'error')
  }
  xhr.send(form)
}

function resetBatch() {
  batchFiles.value = []
  batchState.value = 'idle'
  batchProgress.value = 0
  batchResult.value = null
  log('已重置批量上传列表')
}

onBeforeUnmount(() => {
  downloadController.value?.abort()
  if (downloadBlobUrl.value) URL.revokeObjectURL(downloadBlobUrl.value)
})
</script>

<template>
  <div class="page">
    <section class="card">
      <div class="card-head">
        <div>
          <span class="tag amber">录屏演示</span>
          <h2 class="card-title" style="margin-top: 8px">文件传输实验台</h2>
          <p class="card-sub">
            分片上传 · 服务端断点状态 · 上传/下载进度条 · HTTP Range 下载
          </p>
        </div>
        <span class="tag green">实时可操作</span>
      </div>
      <div class="grid grid-3">
        <div class="dim-item">
          <div class="dim-name">① 切分</div>
          <div class="dim-value">按 1MB 切成 N 片，每片带 file_id + chunk_index。</div>
        </div>
        <div class="dim-item">
          <div class="dim-name">② 续传</div>
          <div class="dim-value">暂停后查询服务端已收到的分片，只补缺失片。</div>
        </div>
        <div class="dim-item">
          <div class="dim-name">③ Range</div>
          <div class="dim-value">下载暂停后发 Range: bytes=已下载-，服务端返回 206。</div>
        </div>
      </div>
    </section>

    <section class="grid grid-2 mt-20" style="grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr)">
      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">1. 分片上传 + 断点续传</h2>
            <p class="card-sub">暂停时已完成的分片会留在服务端，继续时不会重传</p>
          </div>
          <span class="tag blue">{{ doneChunks }}/{{ totalChunks || 0 }} 片</span>
        </div>

        <label class="upload-dropzone">
          <input type="file" hidden @change="onFileChange" />
          <strong>{{ file ? file.name : '点击选择文件' }}</strong>
          <span v-if="file">
            {{ formatBytes(file.size) }} · {{ totalChunks }} 片 · file_id={{ fileId.slice(0, 8) }}…
          </span>
          <span v-else>也可以直接点击下方「使用 20MB 演示文件」</span>
        </label>

        <div class="transfer-toolbar mt-14">
          <button class="btn btn-accent btn-small" @click="useDemoFile">使用 20MB 演示文件</button>
          <label class="small muted">
            分片大小
            <select v-model.number="chunkSize" class="select" style="width: 110px; display: inline-block; margin-left: 6px" @change="changeChunkSize">
              <option :value="512 * 1024">512 KB</option>
              <option :value="1024 * 1024">1 MB</option>
              <option :value="2048 * 1024">2 MB</option>
            </select>
          </label>
          <label class="small muted transfer-check">
            <input v-model="slowDemo" type="checkbox" />
            演示限速（每片 250ms）
          </label>
        </div>

        <div class="progress-track mt-14">
          <i :style="{ width: `${uploadProgress}%` }"></i>
        </div>
        <div class="progress-meta">
          <strong>{{ uploadProgress }}%</strong>
          <span>
            {{ formatBytes(completedBytes + currentLoaded) }} / {{ formatBytes(file?.size || 0) }}
            · 已完成 {{ doneChunks }}/{{ totalChunks || 0 }} 片
          </span>
        </div>

        <div class="transfer-actions mt-14">
          <button class="btn btn-primary" :disabled="uploadActionDisabled" @click="handleUploadAction">
            <span v-if="uploadState === 'uploading' || uploadState === 'merging'" class="spinner"></span>
            {{ uploadActionText }}
          </button>
          <button class="btn btn-ghost btn-small" @click="resetUpload">重置</button>
          <span class="small muted">
            {{ uploadState === 'paused' ? '已暂停：分片在服务端，点「继续上传」只补缺失片' : '暂停后再继续，可观察服务端断点状态' }}
          </span>
        </div>

        <div class="chunk-grid mt-14">
          <span
            v-for="(status, index) in chunkStatuses"
            :key="index"
            class="chunk"
            :class="status"
            :title="`分片 ${index}：${status}`"
          >
            {{ String(index + 1).padStart(2, '0') }}
          </span>
        </div>
        <div class="chunk-legend small muted mt-8">
          <span><i class="legend-dot pending"></i>待上传</span>
          <span><i class="legend-dot uploading"></i>上传中</span>
          <span><i class="legend-dot done"></i>已完成</span>
        </div>

        <div class="lab-note mt-14">
          <strong>断点续传的关键：</strong>
          暂停时前端停止发送下一片，但服务端已经落盘的分片不会丢；继续时先调用
          <code>GET /api/upload/status/{file_id}</code>，只上传 <code>missing</code> 里的分片，
          最后 <code>POST /api/upload/complete</code> 按序号拼接。
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">2. 下载 + Range 断点续传</h2>
            <p class="card-sub">暂停时中断连接，继续时从已下载字节发 Range</p>
          </div>
          <span class="tag" :class="downloadState === 'done' ? 'green' : 'blue'">
            {{ downloadState === 'done' ? '完成' : '206 支持' }}
          </span>
        </div>

        <div class="field">
          <label>服务器文件名</label>
          <input v-model="downloadName" class="input" placeholder="上传完成后自动填入，例如 demo-20mb.bin" />
        </div>

        <div class="progress-track">
          <i :style="{ width: `${downloadProgress}%` }" style="background: linear-gradient(90deg, var(--teal), #5cb3a9)"></i>
        </div>
        <div class="progress-meta">
          <strong>{{ downloadProgress }}%</strong>
          <span>
            {{ formatBytes(downloadedBytes) }} / {{ downloadTotal ? formatBytes(downloadTotal) : '未知大小' }}
          </span>
        </div>

        <div class="transfer-actions mt-14">
          <button class="btn btn-primary" :disabled="!downloadName" @click="handleDownloadAction">
            <span v-if="downloadState === 'downloading'" class="spinner"></span>
            {{ downloadActionText }}
          </button>
          <button class="btn btn-ghost btn-small" @click="resetDownload">重置</button>
          <a v-if="canSave" class="btn btn-accent btn-small" :href="downloadBlobUrl" :download="downloadName">
            保存文件
          </a>
        </div>

        <div class="lab-note mt-14">
          <strong>下载进度条：</strong>
          <code>fetch</code> 拿到 <code>ReadableStream</code>，每读到一块就累加
          <code>downloadedBytes</code>；暂停用 <code>AbortController</code> 中断，继续时发
          <code>Range: bytes=已下载-</code>，服务端返回 <code>206 Partial Content</code>，
          只传剩余部分。
        </div>

        <div class="download-facts mt-14">
          <div><span>已收到</span><strong>{{ formatBytes(downloadedBytes) }}</strong></div>
          <div><span>总大小</span><strong>{{ downloadTotal ? formatBytes(downloadTotal) : '—' }}</strong></div>
          <div><span>上次状态</span><strong>{{ downloadState }}</strong></div>
        </div>
      </div>
    </section>

    <section class="card mt-20">
      <div class="card-head">
        <div>
          <h2 class="card-title">3. 小文件批量上传</h2>
          <p class="card-sub">一次请求提交多个小文件，减少 HTTP 往返；单请求最多 100 个</p>
        </div>
        <span class="tag blue">{{ batchDoneCount }}/{{ batchFiles.length }} 个</span>
      </div>

      <div class="grid grid-2" style="grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr)">
        <div>
          <label class="upload-dropzone">
            <input type="file" multiple hidden @change="onBatchChange" />
            <strong>点击选择多个小文件</strong>
            <span>也可以直接使用下方 5 个演示文件</span>
          </label>

          <div class="transfer-toolbar mt-14">
            <button class="btn btn-accent btn-small" @click="useDemoBatch">使用 5 个小文件演示</button>
            <button
              class="btn btn-primary btn-small"
              :disabled="batchState === 'uploading' || !batchFiles.length"
              @click="uploadBatch"
            >
              <span v-if="batchState === 'uploading'" class="spinner"></span>
              {{ batchActionText }}
            </button>
            <button class="btn btn-ghost btn-small" @click="resetBatch">重置</button>
          </div>

          <div class="progress-track mt-14">
            <i :style="{ width: `${batchProgress}%` }"></i>
          </div>
          <div class="progress-meta">
            <strong>{{ batchProgress }}%</strong>
            <span>{{ formatBytes(batchTotalSize) }} · {{ batchDoneCount }}/{{ batchFiles.length }} 个完成</span>
          </div>

          <div class="lab-note mt-14">
            <strong>批量上传的关键：</strong>
            多个文件放进同一个 <code>FormData</code>，一次请求发给
            <code>POST /api/upload/batch</code>，后端循环落盘。小文件瓶颈是文件数量和元数据，不是带宽；
            超大文件仍然走上面的分片上传。
          </div>
        </div>

        <div>
          <div v-if="batchFiles.length" class="batch-list">
            <div v-for="item in batchFiles" :key="item.name" class="batch-item">
              <div>
                <strong>{{ item.name }}</strong>
                <span>{{ formatBytes(item.size) }}</span>
              </div>
              <span
                class="tag"
                :class="item.status === 'done' ? 'green' : item.status === 'error' ? 'coral' : item.status === 'uploading' ? 'amber' : ''"
              >
                {{ batchStatusLabel(item.status) }}
              </span>
              <a v-if="item.server" :href="item.server.url" target="_blank" class="small">下载</a>
            </div>
          </div>
          <div v-else class="empty" style="padding: 30px 10px">
            <div class="empty-mark">▤</div>
            <strong>还没有小文件</strong>
            <p>点「使用 5 个小文件演示」即可，或点上面的虚线框选择多个文件。</p>
          </div>
          <div v-if="batchResult" class="small muted mt-8">
            服务端返回：{{ batchResult.count }} 个文件，共 {{ formatBytes(batchResult.total_size) }}
          </div>
        </div>
      </div>
    </section>

    <section class="grid grid-2 mt-20" style="grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr)">
      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">核心代码位置</h2>
            <p class="card-sub">录屏时可直接切到这些文件讲实现</p>
          </div>
        </div>
        <div class="code-ref">
          <div><code>backend/routers/upload.py</code><span>upload_chunk / upload_status / complete_upload / download / upload_batch</span></div>
          <div><code>frontend/src/components/UploadLab.vue</code><span>uploadChunk / uploadMissingChunks / startDownload / uploadBatch</span></div>
          <div><code>backend/test_upload.py</code><span>命令行分片上传与 MD5 校验</span></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">运行日志</h2>
            <p class="card-sub">暂停、续传、合并、Range 的每一步</p>
          </div>
          <button class="btn btn-ghost btn-small" @click="logs = []">清空</button>
        </div>
        <div v-if="logs.length" class="lab-log">
          <div v-for="(item, index) in logs" :key="index" :class="item.type">
            <span>{{ item.time }}</span>{{ item.message }}
          </div>
        </div>
        <div v-else class="empty" style="padding: 26px 10px">
          <strong>还没有操作记录</strong>
          <p>选择演示文件并开始上传，这里会实时显示分片状态。</p>
        </div>
      </div>
    </section>
  </div>
</template>
